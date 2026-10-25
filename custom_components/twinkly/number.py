"""The Twinkly playlist duration."""

from typing import override

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import TwinklyConfigEntry, TwinklyCoordinator
from .entity import TwinklyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TwinklyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the playlist duration on devices that store movies."""
    if config_entry.runtime_data.supports_effects:
        async_add_entities([TwinklyPlaylistDuration(config_entry.runtime_data)])


class TwinklyPlaylistDuration(TwinklyEntity, RestoreNumber):
    """Seconds each movie plays when the play-all button starts the playlist."""

    _attr_translation_key = "playlist_duration"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 5
    _attr_native_max_value = 600
    _attr_native_step = 5
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: TwinklyCoordinator) -> None:
        """Initialize the number."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.device_info['mac']}_playlist_duration"

    @property
    @override
    def available(self) -> bool:
        """Stay settable while polling is paused or the device is unreachable."""
        return True

    @override
    async def async_added_to_hass(self) -> None:
        """Take the value from before the restart, if there was one."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) and last.native_value is not None:
            self.coordinator.playlist_duration = int(last.native_value)

    @property
    @override
    def native_value(self) -> float:
        """Return the seconds per movie."""
        return self.coordinator.playlist_duration

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Store the seconds per movie; the device is not contacted."""
        self.coordinator.playlist_duration = int(value)
        self.async_write_ha_state()
