"""Movies on the device, and the library of recorded movies they can come from."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from ttls.client import Twinkly, TwinklyError

_LOGGER = logging.getLogger(__name__)

# A proxy on the host records every movie the Twinkly app uploads into this
# directory (one shelf per product code and LED count, one directory per movie
# holding movie.json and frames.bin). When it is mounted into Home Assistant,
# recorded movies can be uploaded to a device again.
LIBRARY_DIR = Path("/twinkly-library")

RESPONSE_OK = 1000
DESCRIPTOR = {"RGBW": ("rgbw_raw", 4), "RGB": ("rgb_raw", 3)}
# Modes a device returns to after a delete; the app turns the LEDs off for it.
RESTORABLE_MODES = ("movie", "playlist", "effect", "color", "demo")


@dataclass(frozen=True)
class LibraryMovie:
    """A recorded movie that fits the device it is listed for."""

    name: str
    unique_id: str
    frames_number: int
    upload: dict[str, Any]
    frames_path: Path
    size: int
    sha256: str


def _read_entry(entry: Path, leds: int, descriptor: str, bytes_per_led: int) -> LibraryMovie:
    record = json.loads((entry / "movie.json").read_text())
    upload = record["upload"]
    frames_number = upload["frames_number"]
    if not isinstance(frames_number, int) or frames_number <= 0:
        raise ValueError("no frames")
    size = frames_number * leds * bytes_per_led
    if upload["unique_id"] != entry.name:
        raise ValueError("unique_id does not match the directory")
    if upload["leds_per_frame"] != leds or upload["descriptor_type"] != descriptor:
        raise ValueError("made for another LED layout")
    if (entry / "frames.bin").stat().st_size != size or record["size"] != size:
        raise ValueError("frames do not match the frame count")
    return LibraryMovie(
        name=str(upload["name"]),
        unique_id=entry.name,
        frames_number=frames_number,
        upload=upload,
        frames_path=entry / "frames.bin",
        size=size,
        sha256=record["sha256"],
    )


def library_mounted() -> bool:
    """Return whether the library directory is there."""
    return LIBRARY_DIR.is_dir()


def read_library(device_info: dict[str, Any]) -> list[LibraryMovie] | None:
    """Return the library movies that fit the device, or None without a library."""
    if not library_mounted():
        return None
    leds = device_info["number_of_led"]
    if device_info.get("led_profile") not in DESCRIPTOR:
        return []
    descriptor, bytes_per_led = DESCRIPTOR[device_info["led_profile"]]
    shelf = LIBRARY_DIR / f"{device_info['product_code']}-{leds}"
    if not shelf.is_dir():
        return []
    movies = []
    for entry in sorted(shelf.iterdir()):
        try:
            movies.append(_read_entry(entry, leds, descriptor, bytes_per_led))
        except (OSError, ValueError, KeyError, TypeError) as exception:
            _LOGGER.debug("Skipping library entry %s: %s", entry, exception)
    return sorted(movies, key=lambda movie: (movie.name.casefold(), movie.unique_id))


def read_frames(movie: LibraryMovie) -> bytes:
    """Return the movie's frames, refusing them if they changed since recording."""
    frames = movie.frames_path.read_bytes()
    if len(frames) != movie.size or hashlib.sha256(frames).hexdigest() != movie.sha256:
        raise ValueError(f"the recording of {movie.name} is damaged")
    return frames


def option_labels[_T](items: Iterable[_T], name: Callable[[_T], str], uid: Callable[[_T], str]) -> dict[str, _T]:
    """Label items by name; names that occur twice get the start of their unique id."""
    items = list(items)
    names = [name(item) for item in items]
    return {
        (f"{name(item)} ({uid(item)[:8]})" if names.count(name(item)) > 1 else name(item)): item
        for item in items
    }


async def device_request(
    client: Twinkly, method: str, endpoint: str, *, json_body: Any = None, data: bytes | None = None
) -> dict[str, Any]:
    """Make an authenticated request ttls has no call for and return its checked answer.

    It uses the client's session and token, so it shares the one login a device
    allows. After a 401 it logs in again once through client.refresh_token,
    where the coordinator counts logins forced by another client.
    """
    await client.get_api_version()
    for attempt in range(2):
        await client.ensure_token()
        headers = dict(client._headers)  # noqa: SLF001
        if data is not None:
            headers["Content-Type"] = "application/octet-stream"
        async with client._get_session().request(  # noqa: SLF001
            method,
            f"{client.base}/{endpoint}",
            headers=headers,
            json=json_body,
            data=data,
            timeout=client._timeout,  # noqa: SLF001
        ) as response:
            if response.status == 401 and attempt == 0:
                await client.refresh_token()
                continue
            response.raise_for_status()
            answer = await response.json(content_type=None)
        if not isinstance(answer, dict) or answer.get("code") != RESPONSE_OK:
            raise TwinklyError(f"{method} {endpoint} answered {answer}")
        return answer
    raise TwinklyError(f"{method} {endpoint} stayed unauthorized")


async def upload_movie(client: Twinkly, movie: LibraryMovie, frames: bytes) -> int:
    """Upload a recorded movie as the app did and return its id on the device."""
    created = await device_request(client, "POST", "movies/new", json_body=movie.upload)
    await device_request(client, "POST", "movies/full", data=frames)
    return int(created["id"])


async def delete_movie(client: Twinkly, unique_id: str, mode: str | None) -> None:
    """Delete one movie in the app's order: LEDs off, delete, back to the mode."""
    await client.set_mode("off")
    try:
        # The app sends the id in upper case; that is the form known to work.
        await device_request(client, "DELETE", f"movies/{unique_id.upper()}")
    finally:
        if mode in RESTORABLE_MODES:
            await client.set_mode(mode)


async def write_playlist(client: Twinkly, unique_ids: list[str], duration: int) -> None:
    """Replace the device's playlist with the given movies, each shown for duration seconds."""
    entries = [{"unique_id": unique_id, "duration": duration} for unique_id in unique_ids]
    await device_request(client, "POST", "playlist", json_body={"entries": entries})
