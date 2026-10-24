"""Configure tests for the Twinkly integration."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.twinkly import DOMAIN
from homeassistant.const import CONF_HOST, CONF_ID, CONF_MODEL, CONF_NAME

from .const import TEST_MAC, TEST_MODEL, TEST_NAME

from pytest_homeassistant_custom_component.common import MockConfigEntry, load_json_object_fixture


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Create Twinkly entry in Home Assistant."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Twinkly",
        unique_id=TEST_MAC,
        data={
            CONF_HOST: "192.168.0.123",
            CONF_ID: "497dcba3-ecbf-4587-a2dd-5eb0665e6880",
            CONF_NAME: TEST_NAME,
            CONF_MODEL: TEST_MODEL,
        },
        entry_id="01JFMME2P6RA38V5AMPCJ2JYYV",
        minor_version=2,
    )


@pytest.fixture
def mock_twinkly_client() -> Generator[AsyncMock]:
    """Mock the Twinkly client."""
    with (
        patch(
            "custom_components.twinkly.Twinkly",
            autospec=True,
        ) as mock_client,
        patch(
            "custom_components.twinkly.config_flow.Twinkly",
            new=mock_client,
        ),
    ):
        client = mock_client.return_value
        client.get_details.return_value = load_json_object_fixture(
            "get_details.json")
        client.get_firmware_version.return_value = load_json_object_fixture(
            "get_firmware_version.json")
        client.get_saved_movies.return_value = load_json_object_fixture(
            "get_saved_movies.json")
        client.get_current_movie.return_value = load_json_object_fixture(
            "get_current_movie.json")
        client.get_mode.return_value = load_json_object_fixture("get_mode.json")
        client.get_predefined_effects.return_value = load_json_object_fixture(
            "get_predefined_effects.json")
        client.get_current_predefined_effect.return_value = load_json_object_fixture(
            "get_current_predefined_effect.json")
        client.is_on.return_value = True
        client.get_brightness.return_value = {"mode": "enabled", "value": 10}
        client.host = "192.168.0.123"
        yield client


@pytest.fixture
def mock_setup_entry() -> Generator[None]:
    """Mock setting up a config entry."""
    with patch("custom_components.twinkly.async_setup_entry", return_value=True):
        yield
