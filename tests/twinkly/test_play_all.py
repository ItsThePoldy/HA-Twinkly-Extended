"""Tests for the play-all button and its duration."""

from typing import Any
from unittest.mock import AsyncMock, call

import pytest

from custom_components.twinkly import movies
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError

from . import setup_integration

from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_restore_cache_with_extra_data

BUTTON = "button.tree_1_play_all_animations_in_turn"
DURATION = "number.tree_1_duration_per_animation"
RAINBOW = "11111111-aaaa-4aaa-8aaa-111111111111"
FLARE = "22222222-bbbb-4bbb-8bbb-222222222222"


@pytest.fixture
def requests(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, Any]]:
    """Record the requests ttls has no call for."""
    calls: list[tuple[str, str, Any]] = []

    async def fake(client, method, endpoint, *, json_body=None, data=None):
        calls.append((method, endpoint, json_body))
        return {"code": 1000}

    monkeypatch.setattr(movies, "device_request", fake)
    return calls


async def _press(hass: HomeAssistant) -> None:
    await hass.services.async_call(BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: BUTTON}, blocking=True)


async def test_play_all_writes_every_movie_and_starts_the_playlist(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_twinkly_client: AsyncMock, requests: list
) -> None:
    """All movies in device order, each for the set duration; then playlist mode, device on."""
    mock_twinkly_client.is_on.return_value = False
    await setup_integration(hass, mock_config_entry)
    await hass.services.async_call(
        NUMBER_DOMAIN, SERVICE_SET_VALUE, {ATTR_ENTITY_ID: DURATION, ATTR_VALUE: 10}, blocking=True
    )

    await _press(hass)

    assert requests == [
        ("POST", "playlist", {"entries": [{"unique_id": RAINBOW, "duration": 10}, {"unique_id": FLARE, "duration": 10}]})
    ]
    assert mock_twinkly_client.set_mode.await_args_list == [call("playlist")]
    mock_twinkly_client.turn_on.assert_awaited_once()


async def test_a_device_that_is_on_is_not_turned_on_again(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_twinkly_client: AsyncMock, requests: list
) -> None:
    """Pressing the button on a lit device only starts the playlist."""
    await setup_integration(hass, mock_config_entry)
    await _press(hass)
    assert requests[0][2]["entries"][0]["duration"] == 30
    mock_twinkly_client.turn_on.assert_not_awaited()


async def test_without_movies_nothing_is_written(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_twinkly_client: AsyncMock, requests: list
) -> None:
    """An empty device gets no empty playlist and keeps its mode."""
    mock_twinkly_client.get_saved_movies.return_value = {"movies": [], "code": 1000}
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(HomeAssistantError, match="no animations"):
        await _press(hass)

    assert requests == []
    mock_twinkly_client.set_mode.assert_not_awaited()


async def test_the_duration_survives_a_restart(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_twinkly_client: AsyncMock, requests: list
) -> None:
    """The duration set before a restart is the one the button uses after it."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(DURATION, "45"),
                {
                    "native_value": 45,
                    "native_min_value": 5,
                    "native_max_value": 600,
                    "native_step": 5,
                    "native_unit_of_measurement": "s",
                },
            )
        ],
    )
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(DURATION).state == "45"
    await _press(hass)
    assert requests[0][2]["entries"][0]["duration"] == 45
