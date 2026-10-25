"""Tests for the movie library, uploads and deletes."""

import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, call

import pytest
from ttls.client import TwinklyError

from custom_components.twinkly import movies
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, ATTR_OPTION
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from . import setup_integration

from pytest_homeassistant_custom_component.common import MockConfigEntry

LIBRARY = "select.tree_1_library"
DELETE = "select.tree_1_delete_movie"
# The test device: TW2016, 100 LEDs, RGB.
DEVICE = {"product_code": "TW2016", "number_of_led": 100, "led_profile": "RGB"}
FLARE_UID = "22222222-bbbb-4bbb-8bbb-222222222222"


def _record(
    library: Path,
    unique_id: str,
    name: str,
    frames_number: int = 4,
    leds: int = 100,
    descriptor: str = "rgb_raw",
    bytes_per_led: int = 3,
    shelf: str = "TW2016-100",
) -> bytes:
    """Write a recording as the proxy does and return its frames."""
    frames = bytes(range(256)) * ((frames_number * leds * bytes_per_led) // 256 + 1)
    frames = frames[: frames_number * leds * bytes_per_led]
    entry = library / shelf / unique_id
    entry.mkdir(parents=True)
    (entry / "frames.bin").write_bytes(frames)
    upload = {
        "descriptor_type": descriptor,
        "fps": 12,
        "frames_number": frames_number,
        "id": 0,
        "leds_per_frame": leds,
        "name": name,
        "unique_id": unique_id,
    }
    record = {
        "upload": upload,
        "product_code": "TW2016",
        "bytes_per_led": bytes_per_led,
        "sha256": hashlib.sha256(frames).hexdigest(),
        "size": len(frames),
    }
    (entry / "movie.json").write_text(json.dumps(record))
    return frames


@pytest.fixture
def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Mount point of the movie library."""
    monkeypatch.setattr(movies, "LIBRARY_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def device_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, Any]]:
    """Record the requests ttls has no call for; movies/new answers id 7."""
    calls: list[tuple[str, str, Any]] = []

    async def fake(client, method, endpoint, *, json_body=None, data=None):
        calls.append((method, endpoint, json_body if data is None else data))
        return {"id": 7, "code": 1000} if endpoint == "movies/new" else {"code": 1000}

    monkeypatch.setattr(movies, "device_request", fake)
    return calls


async def _select(hass: HomeAssistant, entity: str, option: str) -> None:
    await hass.services.async_call(
        SELECT_DOMAIN, "select_option", {ATTR_ENTITY_ID: entity, ATTR_OPTION: option}, blocking=True
    )


def test_only_fitting_intact_recordings_are_listed(library: Path) -> None:
    """Every way a recording can be unusable keeps it off the list."""
    _record(library, "aaaaaaaa-0000-4000-8000-000000000001", "Good")
    # Both have the byte size of a fitting movie (75 x 4 = 100 x 3 per frame), so only
    # the LED count and the descriptor tell them apart.
    _record(library, "aaaaaaaa-0000-4000-8000-000000000002", "Other leds", leds=75, bytes_per_led=4)
    _record(library, "aaaaaaaa-0000-4000-8000-000000000003", "RGBW", descriptor="rgbw_raw", bytes_per_led=3)
    short = library / "TW2016-100" / "aaaaaaaa-0000-4000-8000-000000000004"
    _record(library, short.name, "Short")
    (short / "frames.bin").write_bytes(b"\0" * 10)
    broken = library / "TW2016-100" / "aaaaaaaa-0000-4000-8000-000000000005"
    _record(library, broken.name, "Broken json")
    (broken / "movie.json").write_text("{")
    moved = library / "TW2016-100" / "aaaaaaaa-0000-4000-8000-000000000006"
    _record(library, "aaaaaaaa-0000-4000-8000-000000000099", "Moved")
    (library / "TW2016-100" / "aaaaaaaa-0000-4000-8000-000000000099").rename(moved)
    _record(library, "aaaaaaaa-0000-4000-8000-000000000007", "Other shelf", shelf="TW2016-200")

    listed = movies.read_library(DEVICE)

    assert len(list((library / "TW2016-100").iterdir())) == 6
    assert listed is not None
    assert [movie.name for movie in listed] == ["Good"]


def test_no_library_is_not_an_empty_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the mount there is no library at all; with it, an empty one."""
    monkeypatch.setattr(movies, "LIBRARY_DIR", tmp_path / "absent")
    assert movies.read_library(DEVICE) is None
    monkeypatch.setattr(movies, "LIBRARY_DIR", tmp_path)
    assert movies.read_library(DEVICE) == []


def test_damaged_frames_are_refused(library: Path) -> None:
    """A recording whose frames changed after recording is not uploaded."""
    _record(library, "aaaaaaaa-0000-4000-8000-000000000001", "Good")
    (movie,) = movies.read_library(DEVICE) or []
    assert movies.read_frames(movie)
    frames = bytearray(movie.frames_path.read_bytes())
    frames[0] ^= 0xFF
    movie.frames_path.write_bytes(bytes(frames))
    with pytest.raises(ValueError, match="damaged"):
        movies.read_frames(movie)


def test_duplicate_names_are_told_apart() -> None:
    """Two movies of one name get the start of their unique id."""
    labels = movies.option_labels(
        [("Snow", "aaaaaaaa-1"), ("Snow", "bbbbbbbb-2"), ("Rain", "cccccccc-3")],
        lambda item: item[0],
        lambda item: item[1],
    )
    assert list(labels) == ["Snow (aaaaaaaa)", "Snow (bbbbbbbb)", "Rain"]


class _Response:
    def __init__(self, status: int, answer: Any) -> None:
        self.status = status
        self._answer = answer

    async def __aenter__(self) -> "_Response":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise TwinklyError(f"HTTP {self.status}")

    async def json(self, content_type: str | None = None) -> Any:
        return self._answer


class _Client:
    """The parts of ttls.Twinkly that device_request uses."""

    base = "http://twinkly/xled/v1"
    _timeout = 10

    def __init__(self, responses: list[_Response]) -> None:
        self._headers = {"X-Auth-Token": "old"}
        self.responses = responses
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.get_api_version = AsyncMock()
        self.ensure_token = AsyncMock()
        self.refresh_token = AsyncMock(side_effect=self._login)

    def _login(self) -> None:
        self._headers["X-Auth-Token"] = "new"

    def _get_session(self) -> "_Client":
        return self

    def request(self, method: str, url: str, *, headers: dict[str, str], **_: Any) -> _Response:
        self.requests.append((method, url, headers))
        return self.responses.pop(0)


async def test_a_401_logs_in_again_once_and_keeps_the_answer() -> None:
    """After a takeover the request is repeated with the new token."""
    client = _Client([_Response(401, None), _Response(200, {"id": 3, "code": 1000})])
    answer = await movies.device_request(client, "POST", "movies/new", json_body={})  # type: ignore[arg-type]
    assert answer == {"id": 3, "code": 1000}
    client.refresh_token.assert_awaited_once()
    assert [headers["X-Auth-Token"] for _, _, headers in client.requests] == ["old", "new"]


async def test_a_refused_request_raises() -> None:
    """A device answer without code 1000 is an error, not a success."""
    client = _Client([_Response(200, {"code": 1104})])
    with pytest.raises(TwinklyError):
        await movies.device_request(client, "DELETE", "movies/X")  # type: ignore[arg-type]


async def test_delete_runs_the_app_sequence(device_calls: list) -> None:
    """LEDs off, delete by upper-case unique id, back to the mode it was in."""
    client = AsyncMock()
    await movies.delete_movie(client, FLARE_UID, "movie")
    assert device_calls == [("DELETE", f"movies/{FLARE_UID.upper()}", None)]
    assert client.set_mode.await_args_list == [call("off"), call("movie")]


async def test_delete_restores_the_mode_even_when_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A refused delete still leaves the LEDs as they were."""
    monkeypatch.setattr(movies, "device_request", AsyncMock(side_effect=TwinklyError("no")))
    client = AsyncMock()
    with pytest.raises(TwinklyError):
        await movies.delete_movie(client, FLARE_UID, "effect")
    assert client.set_mode.await_args_list == [call("off"), call("effect")]


async def test_choosing_a_recording_uploads_and_plays_it(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_twinkly_client: AsyncMock,
    library: Path,
    device_calls: list,
) -> None:
    """A movie the device does not have is uploaded as recorded, then played."""
    frames = _record(library, "aaaaaaaa-0000-4000-8000-000000000001", "Candy Cane")
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(LIBRARY).attributes["options"] == ["Candy Cane"]

    await _select(hass, LIBRARY, "Candy Cane")

    assert [(method, endpoint) for method, endpoint, _ in device_calls] == [
        ("POST", "movies/new"),
        ("POST", "movies/full"),
    ]
    assert device_calls[0][2]["unique_id"] == "aaaaaaaa-0000-4000-8000-000000000001"
    assert device_calls[1][2] == frames
    mock_twinkly_client.set_current_movie.assert_awaited_once_with(7)
    mock_twinkly_client.set_mode.assert_awaited_once_with("movie")


async def test_a_recording_on_the_device_is_played_without_upload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_twinkly_client: AsyncMock,
    library: Path,
    device_calls: list,
) -> None:
    """The device already has it (unique id in another case): just play it."""
    _record(library, FLARE_UID.upper(), "Flare")
    await setup_integration(hass, mock_config_entry)

    await _select(hass, LIBRARY, "Flare")

    assert device_calls == []
    mock_twinkly_client.set_current_movie.assert_awaited_once_with(2)


async def test_too_little_room_names_the_shortfall(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_twinkly_client: AsyncMock,
    library: Path,
    device_calls: list,
) -> None:
    """Nothing is deleted or uploaded when the movie does not fit."""
    _record(library, "aaaaaaaa-0000-4000-8000-000000000001", "Candy Cane", frames_number=40)
    await setup_integration(hass, mock_config_entry)
    mock_twinkly_client.get_saved_movies.return_value = {"movies": [], "available_frames": 25, "code": 1000}

    with pytest.raises(HomeAssistantError, match="15 frames missing"):
        await _select(hass, LIBRARY, "Candy Cane")

    assert device_calls == []
    mock_twinkly_client.set_current_movie.assert_not_awaited()


async def test_a_damaged_recording_is_not_uploaded(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_twinkly_client: AsyncMock,
    library: Path,
    device_calls: list,
) -> None:
    """Frames that no longer match their hash never reach the device."""
    _record(library, "aaaaaaaa-0000-4000-8000-000000000001", "Candy Cane")
    await setup_integration(hass, mock_config_entry)
    frames_path = library / "TW2016-100" / "aaaaaaaa-0000-4000-8000-000000000001" / "frames.bin"
    frames = bytearray(frames_path.read_bytes())
    frames[0] ^= 0xFF
    frames_path.write_bytes(bytes(frames))

    with pytest.raises(HomeAssistantError, match="damaged"):
        await _select(hass, LIBRARY, "Candy Cane")

    assert device_calls == []


async def test_choosing_a_movie_to_delete_deletes_it(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_twinkly_client: AsyncMock,
    device_calls: list,
) -> None:
    """The delete select lists the device's movies and deletes the chosen one."""
    await setup_integration(hass, mock_config_entry)
    state = hass.states.get(DELETE)
    assert state.attributes["options"] == ["Rainbow", "Flare"]

    await _select(hass, DELETE, "Flare")

    assert device_calls == [("DELETE", f"movies/{FLARE_UID.upper()}", None)]
    assert mock_twinkly_client.set_mode.await_args_list == [call("off"), call("color")]


async def test_without_a_library_there_is_no_library_select(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_twinkly_client: AsyncMock, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The library select exists only where a library is mounted; delete always."""
    monkeypatch.setattr(movies, "LIBRARY_DIR", tmp_path / "absent")
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(LIBRARY) is None
    assert hass.states.get(DELETE) is not None
