"""Shared fixtures for the custom-integration test suite."""

import pytest
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from syrupy.assertion import SnapshotAssertion


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load integrations from custom_components/."""
    return


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Read snapshots from tests/<suite>/snapshots/ in core's serialization format."""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)
