"""Tests for the Animation select and the split between controls and configuration."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, call

import pytest

from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, ATTR_OPTION, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import setup_integration
from .test_light_predefined_effects import CURTAIN_NAMES, curtain  # noqa: F401

from pytest_homeassistant_custom_component.common import MockConfigEntry

ANIMATION = "select.tree_1_animation"
TRANSLATIONS = Path(__file__).parents[2] / "custom_components/twinkly/translations"


async def _choose(hass: HomeAssistant, option: str) -> None:
    await hass.services.async_call(
        SELECT_DOMAIN, "select_option", {ATTR_ENTITY_ID: ANIMATION, ATTR_OPTION: option}, blocking=True
    )


async def test_movies_come_first_and_a_name_clash_is_marked(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, curtain: AsyncMock  # noqa: F811
) -> None:
    """The movie "Rainbow" keeps its name; the predefined effect "Rainbow" is marked."""
    await setup_integration(hass, mock_config_entry)

    options = hass.states.get(ANIMATION).attributes["options"]
    assert options == ["Rainbow", "Flare", "Rainbow (effect)", *CURTAIN_NAMES[1:]]


async def test_two_movies_of_one_name_are_told_apart(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_twinkly_client: AsyncMock
) -> None:
    """Duplicate movie names get the start of their unique id."""
    saved = mock_twinkly_client.get_saved_movies.return_value
    saved["movies"][1]["name"] = "Rainbow"
    await setup_integration(hass, mock_config_entry)

    options = hass.states.get(ANIMATION).attributes["options"]
    assert options[:2] == ["Rainbow (11111111)", "Rainbow (22222222)"]


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("movie", "Rainbow"), ("effect", "Effect 2"), ("color", "unknown")],
)
async def test_the_select_shows_what_plays(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_twinkly_client: AsyncMock,
    mode: str,
    expected: str,
) -> None:
    """Movie mode shows the current movie, effect mode the running effect, other modes nothing."""
    mock_twinkly_client.get_mode.return_value = {"mode": mode}
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(ANIMATION).state == expected


async def test_choosing_a_movie_plays_it_and_turns_the_device_on(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_twinkly_client: AsyncMock
) -> None:
    """A movie is set by id, then movie mode; a device that is off is turned on."""
    mock_twinkly_client.is_on.return_value = False
    await setup_integration(hass, mock_config_entry)

    await _choose(hass, "Flare")

    mock_twinkly_client.set_current_movie.assert_awaited_once_with(2)
    assert mock_twinkly_client.set_mode.await_args_list == [call("movie")]
    mock_twinkly_client.set_current_predefined_effect.assert_not_awaited()
    mock_twinkly_client.turn_on.assert_awaited_once()


async def test_choosing_an_effect_plays_it_without_turning_on_again(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, curtain: AsyncMock  # noqa: F811
) -> None:
    """A predefined effect is set by index, then effect mode; a device that is on stays as it is."""
    await setup_integration(hass, mock_config_entry)

    await _choose(hass, "Fireworks")

    curtain.set_current_predefined_effect.assert_awaited_once_with(CURTAIN_NAMES.index("Fireworks"))
    assert curtain.set_mode.await_args_list == [call("effect")]
    curtain.set_current_movie.assert_not_awaited()
    curtain.turn_on.assert_not_awaited()


@pytest.mark.usefixtures("mock_twinkly_client")
async def test_controls_hold_what_plays_and_configuration_what_is_stored(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, entity_registry: er.EntityRegistry, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Steuerung: light, Animation, Mode, play all; Konfiguration: app mode, duration, library, delete."""
    from custom_components.twinkly import movies

    monkeypatch.setattr(movies, "LIBRARY_DIR", tmp_path)
    await setup_integration(hass, mock_config_entry)

    categories = {
        entry.translation_key or entry.domain: entry.entity_category
        for entry in er.async_entries_for_config_entry(entity_registry, mock_config_entry.entry_id)
    }
    assert categories == {
        "light": None,
        "animation": None,
        "mode": None,
        "play_all": None,
        "playlist_duration": EntityCategory.CONFIG,
        "library": EntityCategory.CONFIG,
        "delete_movie": EntityCategory.CONFIG,
        "app_mode": EntityCategory.CONFIG,
    }


def _keys(node: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in node.items():
        keys |= _keys(value, f"{prefix}{key}.") if isinstance(value, dict) else {prefix + key}
    return keys


def test_the_german_translation_covers_exactly_the_english_keys() -> None:
    """de.json is written by hand; it must name every entity en.json names, and no other."""
    english = _keys(json.loads((TRANSLATIONS / "en.json").read_text()))
    german = _keys(json.loads((TRANSLATIONS / "de.json").read_text()))
    assert "entity.select.animation.name" in english
    assert german == english
