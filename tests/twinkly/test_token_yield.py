"""Tests for yielding the device's session token to another client."""

from datetime import timedelta
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
import pytest

from custom_components.twinkly.coordinator import (
    APP_MODE_DURATION,
    FORCED_LOGIN_WITHIN,
    PAUSE_APP_MODE,
    PAUSE_OTHER_CLIENT,
    YIELD_FIRST,
)
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import setup_integration

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

POLL = timedelta(seconds=30)
SWITCH = "switch.tree_1_app_mode"
LIGHT = "light.tree_1"


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(POLL)
    async_fire_time_changed(hass)
    # The coordinator polls in a background task, which a plain block_till_done
    # does not wait for once the poll awaits anything real (the library read).
    await hass.async_block_till_done(wait_background_tasks=True)


def _take_token_on_next_poll(client: AsyncMock) -> None:
    """Make the next poll log in again, as the library does after a 401."""

    async def forced_login(*_args, **_kwargs):
        client.get_mode.side_effect = None
        await client.refresh_token()
        return {"mode": "color", "code": 1000}

    client.get_mode.side_effect = forced_login


async def _setup_with_first_login(hass: HomeAssistant, entry: MockConfigEntry, client: AsyncMock) -> None:
    await setup_integration(hass, entry)
    # The first login of a session is never a takeover.
    await client.refresh_token()


async def test_single_takeover_does_not_pause(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_twinkly_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """One takeover, as one panel command causes, keeps polling going."""
    await _setup_with_first_login(hass, mock_config_entry, mock_twinkly_client)
    _take_token_on_next_poll(mock_twinkly_client)
    await _poll(hass, freezer)

    assert hass.states.get(SWITCH).state == STATE_OFF
    calls = mock_twinkly_client.get_details.call_count
    await _poll(hass, freezer)
    assert mock_twinkly_client.get_details.call_count == calls + 1


async def test_repeated_takeovers_pause_then_resume(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_twinkly_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Two takeovers within the window pause polling; it resumes afterwards."""
    await _setup_with_first_login(hass, mock_config_entry, mock_twinkly_client)
    _take_token_on_next_poll(mock_twinkly_client)
    await _poll(hass, freezer)
    _take_token_on_next_poll(mock_twinkly_client)
    await _poll(hass, freezer)

    state = hass.states.get(SWITCH)
    assert state.state == STATE_ON
    assert state.attributes["reason"] == PAUSE_OTHER_CLIENT

    calls = mock_twinkly_client.get_details.call_count
    for _ in range(int(YIELD_FIRST / POLL) - 1):
        await _poll(hass, freezer)
    assert mock_twinkly_client.get_details.call_count == calls

    await _poll(hass, freezer)
    await _poll(hass, freezer)
    assert mock_twinkly_client.get_details.call_count > calls
    assert hass.states.get(SWITCH).state == STATE_OFF


async def test_pause_doubles_while_the_other_client_stays(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_twinkly_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A client still there after a pause gets a pause twice as long."""
    await _setup_with_first_login(hass, mock_config_entry, mock_twinkly_client)
    coordinator = mock_config_entry.runtime_data
    for _ in range(2):
        _take_token_on_next_poll(mock_twinkly_client)
        await _poll(hass, freezer)
    first = coordinator.paused_until - dt_util.utcnow()

    freezer.tick(YIELD_FIRST)
    await _poll(hass, freezer)
    assert coordinator.paused_until is None
    for _ in range(2):
        _take_token_on_next_poll(mock_twinkly_client)
        await _poll(hass, freezer)
    second = coordinator.paused_until - dt_util.utcnow()

    assert first <= YIELD_FIRST
    assert second > YIELD_FIRST
    assert second <= 2 * YIELD_FIRST


async def test_expiry_login_is_not_a_takeover(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_twinkly_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Renewing an expired token does not count against other clients.

    The renewal and one real takeover fall within one window; only the takeover
    may count, so polling goes on.
    """
    await _setup_with_first_login(hass, mock_config_entry, mock_twinkly_client)
    freezer.tick(FORCED_LOGIN_WITHIN)
    _take_token_on_next_poll(mock_twinkly_client)
    await _poll(hass, freezer)
    _take_token_on_next_poll(mock_twinkly_client)
    await _poll(hass, freezer)

    assert hass.states.get(SWITCH).state == STATE_OFF


async def test_app_mode_switch(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_twinkly_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The switch pauses polling for the app mode duration and resumes on off."""
    await setup_integration(hass, mock_config_entry)
    await hass.services.async_call(SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: SWITCH}, blocking=True)

    state = hass.states.get(SWITCH)
    assert state.state == STATE_ON
    assert state.attributes["reason"] == PAUSE_APP_MODE

    calls = mock_twinkly_client.get_details.call_count
    for _ in range(int(APP_MODE_DURATION / POLL) - 1):
        await _poll(hass, freezer)
    assert mock_twinkly_client.get_details.call_count == calls

    await hass.services.async_call(SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    assert hass.states.get(SWITCH).state == STATE_OFF
    assert mock_twinkly_client.get_details.call_count > calls


@pytest.mark.parametrize("service", [SERVICE_TURN_ON, SERVICE_TURN_OFF])
async def test_light_command_ends_the_pause(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_twinkly_client: AsyncMock,
    service: str,
) -> None:
    """A command from Home Assistant takes the device back."""
    await setup_integration(hass, mock_config_entry)
    await hass.services.async_call(SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    assert hass.states.get(SWITCH).state == STATE_ON

    await hass.services.async_call(LIGHT_DOMAIN, service, {ATTR_ENTITY_ID: LIGHT}, blocking=True)

    assert hass.states.get(SWITCH).state == STATE_OFF
