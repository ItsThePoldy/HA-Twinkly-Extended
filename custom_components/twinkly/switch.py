"""The Twinkly app mode switch."""

from typing import Any, override

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import TwinklyConfigEntry, TwinklyCoordinator
from .entity import TwinklyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TwinklyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the app mode switch from a config entry."""
    async_add_entities([TwinklyAppModeSwitch(config_entry.runtime_data)])


class TwinklyAppModeSwitch(TwinklyEntity, SwitchEntity):
    """On while Home Assistant leaves the device's session token to another client.

    Turning it on pauses polling for the app mode duration, so the Twinkly app can
    stay connected. It also reads on while the coordinator yields on its own after
    another client kept taking the token; turning it off resumes polling at once.
    """

    _attr_translation_key = "app_mode"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: TwinklyCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.device_info['mac']}_app_mode"

    @property
    @override
    def available(self) -> bool:
        """Stay usable while polling is paused or the device is unreachable."""
        return True

    @property
    @override
    def is_on(self) -> bool:
        """Return whether polling is paused."""
        return self.coordinator.paused_until is not None

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return why and until when polling is paused."""
        return {
            "reason": self.coordinator.pause_reason,
            "until": self.coordinator.paused_until,
        }

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Pause polling for the app mode duration."""
        self.coordinator.pause_for_app()

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Resume polling and read the device now."""
        self.coordinator.end_pause()
        await self.coordinator.async_refresh()
