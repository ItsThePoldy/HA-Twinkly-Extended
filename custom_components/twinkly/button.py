"""The Twinkly play-all button."""

from typing import override

from aiohttp import ClientError
from ttls.client import TwinklyError

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import TwinklyConfigEntry, TwinklyCoordinator
from .entity import TwinklyEntity
from .movies import write_playlist


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TwinklyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the play-all button on devices that store movies."""
    if config_entry.runtime_data.supports_effects:
        async_add_entities([TwinklyPlayAllButton(config_entry.runtime_data)])


class TwinklyPlayAllButton(TwinklyEntity, ButtonEntity):
    """Play every movie on the device in turn, through the device's playlist."""

    _attr_translation_key = "play_all"

    def __init__(self, coordinator: TwinklyCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.device_info['mac']}_play_all"
        self.client = coordinator.client

    @override
    async def async_press(self) -> None:
        """Write a playlist of all movies and start it."""
        unique_ids = [
            str(movie["unique_id"])
            for movie in self.coordinator.data.movie_list
            if movie.get("unique_id")
        ]
        if not unique_ids:
            raise HomeAssistantError("There are no animations on the device")
        self.coordinator.end_pause()
        try:
            await write_playlist(self.client, unique_ids, self.coordinator.playlist_duration)
            await self.client.set_mode("playlist")
            self.client.default_mode = "playlist"
            if not self.coordinator.data.is_on:
                await self.client.turn_on()
        except (TwinklyError, TimeoutError, ClientError) as exception:
            raise HomeAssistantError(f"Cannot start the playlist: {exception}") from exception
        finally:
            await self.coordinator.async_refresh()
