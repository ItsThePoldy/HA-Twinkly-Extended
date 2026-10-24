"""Tests for predefined effects on the Twinkly light."""

from datetime import timedelta
from unittest.mock import AsyncMock

from aiohttp import ClientError
from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.components.light import (
    ATTR_EFFECT,
    ATTR_EFFECT_LIST,
    DOMAIN as LIGHT_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant

from . import setup_integration

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

ENTITY = "light.tree_1"
CURTAIN_NAMES = ["Rainbow", "Silver Shower", "Color Glow", "Fireworks", "Spring Glow"]


@pytest.fixture
def curtain(mock_twinkly_client: AsyncMock) -> AsyncMock:
    """Make the mocked device the measured Curtain 210 RGBW (fw 2.11.0)."""
    mock_twinkly_client.get_details.return_value |= {
        "product_code": "TWW210SPP2",
        "hardware_version": "308",
        "fw_family": "G",
        "led_profile": "RGBW",
    }
    mock_twinkly_client.get_firmware_version.return_value["version"] = "2.11.0"
    mock_twinkly_client.get_predefined_effects.return_value = {
        "effects_number": 5,
        "unique_ids": [f"00000000-0000-0000-0000-00000000000{n}" for n in range(1, 6)],
        "code": 1000,
    }
    return mock_twinkly_client


async def test_effect_list_appends_named_effects_to_movies(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, curtain: AsyncMock
) -> None:
    """Movies keep their "<id> <name>" entries; the rule's names follow them."""
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(ENTITY).attributes[ATTR_EFFECT_LIST] == [
        "1 Rainbow",
        "2 Flare",
        *CURTAIN_NAMES,
    ]


async def test_unknown_product_gets_fallback_names(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_twinkly_client: AsyncMock
) -> None:
    """A product without a rule lists its effects as "Effect <n>"."""
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(ENTITY).attributes[ATTR_EFFECT_LIST] == [
        "1 Rainbow",
        "2 Flare",
        "Effect 1",
        "Effect 2",
    ]


async def test_turn_on_with_predefined_effect(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, curtain: AsyncMock
) -> None:
    """Selecting a named effect sets it by index, then switches to effect mode."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        service_data={ATTR_ENTITY_ID: ENTITY, ATTR_EFFECT: "Fireworks"},
        blocking=True,
    )

    curtain.set_current_predefined_effect.assert_called_once_with(3)
    curtain.set_mode.assert_called_once_with("effect")
    assert curtain.default_mode == "effect"
    curtain.set_current_movie.assert_not_called()


async def test_turn_on_with_running_predefined_effect_is_a_no_op(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, curtain: AsyncMock
) -> None:
    """Re-selecting the effect that is already running sends nothing."""
    curtain.get_mode.return_value = {"mode": "effect"}
    curtain.get_current_predefined_effect.return_value = {"preset_id": 3, "code": 1000}
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        service_data={ATTR_ENTITY_ID: ENTITY, ATTR_EFFECT: "Fireworks"},
        blocking=True,
    )

    curtain.set_current_predefined_effect.assert_not_called()
    curtain.set_mode.assert_not_called()


async def test_movie_selection_still_uses_movie_path(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, curtain: AsyncMock
) -> None:
    """A "<id> <name>" movie entry is not mistaken for a predefined effect."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        service_data={ATTR_ENTITY_ID: ENTITY, ATTR_EFFECT: "2 Flare"},
        blocking=True,
    )

    curtain.set_current_movie.assert_called_once_with(2)
    curtain.set_mode.assert_called_once_with("movie")
    curtain.set_current_predefined_effect.assert_not_called()


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"preset_id": 3, "unique_id": "…0004", "code": 1000}, "Fireworks"),
        ({"effect_id": 1, "code": 1000}, "Silver Shower"),
        ({"code": 1000}, None),
    ],
    ids=["preset_id", "effect_id", "neither"],
)
async def test_current_effect_in_effect_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    curtain: AsyncMock,
    response: dict,
    expected: str | None,
) -> None:
    """In effect mode the running predefined effect is reported, not the movie."""
    curtain.get_mode.return_value = {"mode": "effect"}
    curtain.get_current_predefined_effect.return_value = response
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(ENTITY).attributes[ATTR_EFFECT] == expected


async def test_hidden_effect_reports_no_name(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, curtain: AsyncMock
) -> None:
    """A running effect hidden by its rule is reported as no effect."""
    curtain.get_predefined_effects.return_value["unique_ids"].append("hidden-by-null")
    curtain.get_mode.return_value = {"mode": "effect"}
    curtain.get_current_predefined_effect.return_value = {"preset_id": 9, "code": 1000}
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(ENTITY).attributes[ATTR_EFFECT] is None


async def test_current_effect_not_fetched_outside_effect_mode(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, curtain: AsyncMock
) -> None:
    """Outside effect mode the device is not asked for its predefined effect."""
    await setup_integration(hass, mock_config_entry)

    curtain.get_current_predefined_effect.assert_not_called()
    assert hass.states.get(ENTITY).attributes[ATTR_EFFECT] == "1 Rainbow"


async def test_api_v2_device_has_no_predefined_effects(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, curtain: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """ttls refuses predefined effects on API v2; that answer is not retried."""
    curtain.get_predefined_effects.side_effect = NotImplementedError
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(ENTITY).attributes[ATTR_EFFECT_LIST] == ["1 Rainbow", "2 Flare"]

    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert curtain.get_predefined_effects.call_count == 1


async def test_failed_effect_fetch_is_retried(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, curtain: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A transient error leaves the effects unknown and the next update asks again."""
    curtain.get_predefined_effects.side_effect = ClientError
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(ENTITY).attributes[ATTR_EFFECT_LIST] == ["1 Rainbow", "2 Flare"]

    curtain.get_predefined_effects.side_effect = None
    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY).attributes[ATTR_EFFECT_LIST] == [
        "1 Rainbow",
        "2 Flare",
        *CURTAIN_NAMES,
    ]
    calls_after_success = curtain.get_predefined_effects.call_count

    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert curtain.get_predefined_effects.call_count == calls_after_success, (
        "a known list is fetched again"
    )
