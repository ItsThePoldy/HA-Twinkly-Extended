"""Diagnostics support for Twinkly."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import ATTR_SW_VERSION, CONF_HOST, CONF_IP_ADDRESS, CONF_MAC
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .coordinator import TwinklyConfigEntry

TO_REDACT = [CONF_HOST, CONF_IP_ADDRESS, CONF_MAC]


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TwinklyConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a Twinkly config entry."""
    attributes = None
    state = None
    entity_registry = er.async_get(hass)

    entity_id = entity_registry.async_get_entity_id(
        LIGHT_DOMAIN, DOMAIN, str(entry.unique_id)
    )
    if entity_id:
        state = hass.states.get(entity_id)
    if state:
        attributes = state.attributes
    return async_redact_data(
        {
            "entry": entry.as_dict(),
            "device_info": entry.runtime_data.data.device_info,
            ATTR_SW_VERSION: entry.runtime_data.software_version,
            # What a new effect_names.yaml rule needs: match fields are in
            # device_info, the ids here in device order.
            "predefined_effect_ids": entry.runtime_data.predefined_effect_ids,
            "predefined_effects": entry.runtime_data.data.predefined_effects,
            "attributes": attributes,
        },
        TO_REDACT,
    )
