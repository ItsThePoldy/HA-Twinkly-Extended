"""Coordinator for Twinkly."""

from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any, override

from aiohttp import ClientError
from awesomeversion import AwesomeVersion
from ttls.client import Twinkly, TwinklyError
import yaml

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DEV_NAME, DOMAIN, MIN_EFFECT_VERSION
from .effect_names import EffectNameRule, load_rules, resolve_effect_names

_LOGGER = logging.getLogger(__name__)

type TwinklyConfigEntry = ConfigEntry[TwinklyCoordinator]

# A Twinkly device keeps one session token: a login by any client invalidates the
# previous one. The library logs in again on every 401, so while another client
# (the Twinkly app, a wall panel) uses the device, each poll takes the token back
# and throws that client out. The coordinator therefore yields: TAKEOVERS_TO_YIELD
# token takeovers within TAKEOVER_WINDOW pause polling, for YIELD_FIRST and twice
# as long each time the other client is still there afterwards (up to YIELD_MAX).
# A single takeover, as a panel causes with one command, does not pause anything.
TAKEOVER_WINDOW = timedelta(minutes=5)
TAKEOVERS_TO_YIELD = 2
YIELD_FIRST = timedelta(minutes=10)
YIELD_MAX = timedelta(minutes=60)
# How long the app mode switch pauses polling when turned on.
APP_MODE_DURATION = timedelta(minutes=30)
# A token lives 14400 s and the library renews it only once expired, so a login
# this soon after the previous one was forced by a 401: another client took it.
FORCED_LOGIN_WITHIN = timedelta(hours=3, minutes=50)

PAUSE_OTHER_CLIENT = "other_client"
PAUSE_APP_MODE = "app_mode"


@dataclass
class TwinklyData:
    """Class for Twinkly data."""

    device_info: dict[str, Any]
    brightness: int
    is_on: bool
    movies: dict[int, str]
    current_movie: int | None
    current_mode: str | None
    predefined_effects: dict[int, str]
    current_predefined_effect: int | None


class TwinklyCoordinator(DataUpdateCoordinator[TwinklyData]):
    """Class to manage fetching Twinkly data from API."""

    config_entry: TwinklyConfigEntry
    software_version: str
    supports_effects: bool
    device_name: str
    effect_name_rules: list[EffectNameRule]
    # Unique ids of the predefined effects in device order; None until the
    # device has answered once. The list only changes with the firmware.
    predefined_effect_ids: list[str] | None = None
    supports_predefined_effects: bool = False

    def __init__(
        self, hass: HomeAssistant, config_entry: TwinklyConfigEntry, client: Twinkly
    ) -> None:
        """Initialize global Twinkly data updater."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )
        self.client = client
        self.paused_until: datetime | None = None
        self.pause_reason: str | None = None
        self._takeovers: deque[datetime] = deque()
        self._last_takeover: datetime | None = None
        self._last_login: datetime | None = None
        self._yield_count = 0
        # Every login goes through refresh_token, both the one the library does on
        # expiry and the one it forces after a 401; observe it to count takeovers.
        self._refresh_token = client.refresh_token
        client.refresh_token = self._async_refresh_token  # type: ignore[method-assign]

    async def _async_refresh_token(self) -> None:
        """Log in through the library and count logins forced by another client."""
        now = dt_util.utcnow()
        if self._last_login is not None and now - self._last_login < FORCED_LOGIN_WITHIN:
            self._record_takeover(now)
        await self._refresh_token()
        self._last_login = now

    def _record_takeover(self, now: datetime) -> None:
        """Note that another client had taken the token; yield if it keeps doing so."""
        self._last_takeover = now
        self._takeovers.append(now)
        while self._takeovers and now - self._takeovers[0] > TAKEOVER_WINDOW:
            self._takeovers.popleft()
        if len(self._takeovers) < TAKEOVERS_TO_YIELD or self.paused_until is not None:
            return
        duration = min(YIELD_FIRST * 2**self._yield_count, YIELD_MAX)
        self._yield_count += 1
        self._takeovers.clear()
        _LOGGER.info(
            "Another client keeps taking the session token of %s; pausing polling for %s",
            self.client.host,
            duration,
        )
        self._pause(now + duration, PAUSE_OTHER_CLIENT)

    def _pause(self, until: datetime, reason: str) -> None:
        self.paused_until = until
        self.pause_reason = reason
        self.async_update_listeners()

    def pause_for_app(self) -> None:
        """Stop polling for APP_MODE_DURATION so another client can keep the token."""
        self._pause(dt_util.utcnow() + APP_MODE_DURATION, PAUSE_APP_MODE)

    def end_pause(self) -> None:
        """Resume polling now; a command from Home Assistant takes the device back."""
        if self.paused_until is None:
            return
        self.paused_until = None
        self.pause_reason = None
        self._takeovers.clear()
        self.async_update_listeners()

    @override
    async def _async_setup(self) -> None:
        """Set up the Twinkly data."""
        try:
            software_version = await self._request(self.client.get_firmware_version)
            self.device_name = (await self._request(self.client.get_details))[DEV_NAME]
        except (TimeoutError, ClientError) as exception:
            raise UpdateFailed from exception
        self.software_version = software_version["version"]
        self.supports_effects = AwesomeVersion(self.software_version) >= AwesomeVersion(
            MIN_EFFECT_VERSION
        )
        try:
            self.effect_name_rules = await self.hass.async_add_executor_job(load_rules)
        except (OSError, ValueError, yaml.YAMLError) as exception:
            # Names are cosmetic: every effect stays usable under "Effect <n>".
            _LOGGER.error("Effect names unavailable: %s", exception)
            self.effect_name_rules = []

    async def _request[_T](self, request: Callable[[], Awaitable[_T]]) -> _T:
        """Make a request, retrying it once if it times out.

        A device that stalls one request keeps answering others: it replies on
        a new connection within milliseconds while the first is still hanging.
        aiohttp closes a timed-out connection instead of returning it to the
        pool, so the retry gets a fresh one.
        """
        try:
            return await request()
        except TimeoutError:
            return await request()

    @override
    async def _async_update_data(self) -> TwinklyData:
        """Fetch data from Twinkly."""
        now = dt_util.utcnow()
        if self.paused_until is not None:
            if now < self.paused_until:
                # Not contacting the device is the point of the pause; the
                # entities keep showing the last state read.
                return self.data
            self.end_pause()
        elif self._last_takeover is None or now - self._last_takeover > YIELD_MAX:
            self._yield_count = 0
        movies: list[dict[str, Any]] = []
        current_movie: dict[str, Any] = {}
        try:
            device_info = await self._request(self.client.get_details)
            brightness = await self._request(self.client.get_brightness)
            is_on = await self._request(self.client.is_on)
            mode_data = await self._request(self.client.get_mode)
            current_mode = mode_data.get("mode")
            if self.supports_effects:
                movies = (await self._request(self.client.get_saved_movies))["movies"]
        except (TimeoutError, ClientError) as exception:
            raise UpdateFailed from exception
        if self.supports_effects:
            try:
                current_movie = await self._request(self.client.get_current_movie)
            except (TwinklyError, TimeoutError, ClientError) as exception:
                _LOGGER.debug("Error fetching current movie: %s", exception)
            await self._async_fetch_predefined_effect_ids()
        current_predefined_effect = None
        if self.supports_predefined_effects and current_mode == "effect":
            current_predefined_effect = await self._async_fetch_current_predefined()
        brightness = (
            int(brightness["value"]) if brightness["mode"] == "enabled" else 100
        )
        brightness = round(brightness * 2.55) if is_on else 0
        if self.device_name != device_info[DEV_NAME]:
            self._async_update_device_info(device_info[DEV_NAME])
        return TwinklyData(
            device_info,
            brightness,
            is_on,
            {movie["id"]: movie["name"] for movie in movies},
            current_movie.get("id"),
            current_mode,
            resolve_effect_names(
                self.effect_name_rules, device_info, self.predefined_effect_ids or []
            ),
            current_predefined_effect,
        )

    async def _async_fetch_predefined_effect_ids(self) -> None:
        """Read the device's predefined effects once it answers.

        A device on API v2 has no predefined-effect endpoint (ttls raises
        NotImplementedError); that answer is final. Any other failure leaves
        the ids unset so the next update asks again.
        """
        if self.predefined_effect_ids is not None:
            return
        try:
            response = await self._request(self.client.get_predefined_effects)
        except NotImplementedError:
            self.predefined_effect_ids = []
            return
        except (TwinklyError, TimeoutError, ClientError) as exception:
            _LOGGER.debug("Error fetching predefined effects: %s", exception)
            return
        self.predefined_effect_ids = [str(uid) for uid in response.get("unique_ids", [])]
        self.supports_predefined_effects = bool(self.predefined_effect_ids)

    async def _async_fetch_current_predefined(self) -> int | None:
        """Return the index of the running predefined effect.

        Firmware 2.11 reports it as preset_id although it is set as effect_id;
        effect_id is read as well for firmware that answers in that field.
        """
        try:
            response = await self._request(self.client.get_current_predefined_effect)
        except (NotImplementedError, TwinklyError, TimeoutError, ClientError) as exception:
            _LOGGER.debug("Error fetching current predefined effect: %s", exception)
            return None
        index = response.get("preset_id", response.get("effect_id"))
        return index if isinstance(index, int) else None

    def _async_update_device_info(self, name: str) -> None:
        """Update the device info."""
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device_by_identifier(
            (DOMAIN, self.data.device_info["mac"]), self.config_entry.entry_id
        )
        if device:
            device_registry.async_update_device(
                device.id,
                name=name,
            )
