"""Tests for the app proxy request file that app mode keeps."""

from pathlib import Path
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
import pytest

from custom_components.twinkly import coordinator
from custom_components.twinkly.coordinator import APP_MODE_DURATION
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant

from . import setup_integration
from .test_token_yield import _poll, _setup_with_first_login, _take_token_on_next_poll

from pytest_homeassistant_custom_component.common import MockConfigEntry

SWITCH = "switch.tree_1_app_mode"
LIGHT = "light.tree_1"
HOST = "192.168.0.123"


@pytest.fixture
def proxy_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Mount point of the proxy request directory."""
    monkeypatch.setattr(coordinator, "APP_PROXY_DIR", tmp_path)
    return tmp_path


async def _switch(hass: HomeAssistant, service: str) -> None:
    await hass.services.async_call(SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    # The request file is written by an executor job that is not awaited; called
    # from the test task it lands among the background tasks.
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_app_mode_writes_and_removes_the_request(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_twinkly_client: AsyncMock, proxy_dir: Path
) -> None:
    """The file exists exactly while app mode is on."""
    await setup_integration(hass, mock_config_entry)
    assert not (proxy_dir / HOST).exists()

    await _switch(hass, SERVICE_TURN_ON)
    assert (proxy_dir / HOST).is_file()

    await _switch(hass, SERVICE_TURN_OFF)
    assert not (proxy_dir / HOST).exists()


async def test_request_ends_with_app_mode_expiry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_twinkly_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    proxy_dir: Path,
) -> None:
    """When the app mode duration runs out, the request goes with it."""
    await setup_integration(hass, mock_config_entry)
    await _switch(hass, SERVICE_TURN_ON)
    assert (proxy_dir / HOST).is_file()
    freezer.tick(APP_MODE_DURATION)
    await _poll(hass, freezer)
    assert not (proxy_dir / HOST).exists()


async def test_light_command_removes_the_request(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_twinkly_client: AsyncMock, proxy_dir: Path
) -> None:
    """A command from Home Assistant ends app mode, and with it the proxy."""
    await setup_integration(hass, mock_config_entry)
    await _switch(hass, SERVICE_TURN_ON)
    assert (proxy_dir / HOST).is_file()
    await hass.services.async_call(LIGHT_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: LIGHT}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not (proxy_dir / HOST).exists()


async def test_yielding_to_another_client_requests_no_proxy(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_twinkly_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    proxy_dir: Path,
) -> None:
    """Only app mode starts the proxy; an automatic yield does not."""
    await _setup_with_first_login(hass, mock_config_entry, mock_twinkly_client)
    for _ in range(2):
        _take_token_on_next_poll(mock_twinkly_client)
        await _poll(hass, freezer)
    assert hass.states.get(SWITCH).attributes["reason"] == coordinator.PAUSE_OTHER_CLIENT
    assert list(proxy_dir.iterdir()) == []


async def test_setup_removes_a_stale_request(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_twinkly_client: AsyncMock, proxy_dir: Path
) -> None:
    """A request left from before a restart does not keep the proxy running."""
    (proxy_dir / HOST).touch()
    await setup_integration(hass, mock_config_entry)
    assert not (proxy_dir / HOST).exists()


async def test_without_the_directory_nothing_is_written(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_twinkly_client: AsyncMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No mount, no file: app mode works as before."""
    absent = tmp_path / "absent"
    monkeypatch.setattr(coordinator, "APP_PROXY_DIR", absent)
    await setup_integration(hass, mock_config_entry)
    await _switch(hass, SERVICE_TURN_ON)
    assert hass.states.get(SWITCH).state == "on"
    assert not absent.exists()
    assert list(tmp_path.iterdir()) == []
    assert "app proxy request" not in caplog.text
