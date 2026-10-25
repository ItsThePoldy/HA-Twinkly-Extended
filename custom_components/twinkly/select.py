"""The Twinkly select component."""

import logging
from typing import Any, override

from aiohttp import ClientError
from ttls.client import TWINKLY_MODES, TwinklyError

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import TwinklyConfigEntry, TwinklyCoordinator
from .entity import TwinklyEntity
from .movies import LibraryMovie, delete_movie, option_labels, read_frames, upload_movie

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TwinklyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the selects from a config entry."""
    coordinator = config_entry.runtime_data
    entities: list[SelectEntity] = [TwinklyModeSelect(coordinator)]
    if coordinator.supports_effects:
        entities.append(TwinklyAnimationSelect(coordinator))
        entities.append(TwinklyDeleteMovieSelect(coordinator))
        if coordinator.data.library is not None:
            entities.append(TwinklyLibrarySelect(coordinator))
    async_add_entities(entities, update_before_add=True)


def _device_movie_labels(coordinator: TwinklyCoordinator) -> dict[str, dict[str, Any]]:
    return option_labels(
        (movie for movie in coordinator.data.movie_list if movie.get("unique_id")),
        lambda movie: str(movie["name"]),
        lambda movie: str(movie["unique_id"]),
    )


def _animation_options(coordinator: TwinklyCoordinator) -> dict[str, tuple[str, int]]:
    """Label everything the device can play: its movies, then its predefined effects.

    Values are ("movie", movie id) or ("effect", effect index).
    """
    movies = option_labels(
        coordinator.data.movie_list,
        lambda movie: str(movie["name"]),
        lambda movie: str(movie.get("unique_id") or movie["id"]),
    )
    options: dict[str, tuple[str, int]] = {
        label: ("movie", int(movie["id"])) for label, movie in movies.items()
    }
    for index, name in coordinator.data.predefined_effects.items():
        label = f"{name} (effect)" if name in options else name
        options[label] = ("effect", index)
    return options


def _library_labels(coordinator: TwinklyCoordinator) -> dict[str, LibraryMovie]:
    return option_labels(
        coordinator.data.library or [], lambda movie: movie.name, lambda movie: movie.unique_id
    )


class TwinklyModeSelect(TwinklyEntity, SelectEntity):
    """The device's raw mode; which effect or movie plays is chosen in the Animation select."""

    _attr_translation_key = "mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = TWINKLY_MODES

    def __init__(self, coordinator: TwinklyCoordinator) -> None:
        """Initialize TwinklyModeSelect."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.device_info['mac']}_mode"
        self.client = coordinator.client

    @property
    @override
    def current_option(self) -> str | None:
        """Return current mode."""
        return self.coordinator.data.current_mode

    @override
    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        self.coordinator.end_pause()
        await self.client.set_mode(option)
        await self.coordinator.async_refresh()


class TwinklyAnimationSelect(TwinklyEntity, SelectEntity):
    """Choose what the device plays: one of its movies or a predefined effect."""

    _attr_translation_key = "animation"

    def __init__(self, coordinator: TwinklyCoordinator) -> None:
        """Initialize the animation select."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.device_info['mac']}_animation"
        self.client = coordinator.client

    @property
    @override
    def options(self) -> list[str]:
        """Return the movies on the device, then its predefined effects."""
        return list(_animation_options(self.coordinator))

    @property
    @override
    def current_option(self) -> str | None:
        """Return what plays, if it is a movie or a predefined effect."""
        data = self.coordinator.data
        if data.current_mode == "movie" and data.current_movie is not None:
            playing: tuple[str, int] = ("movie", data.current_movie)
        elif data.current_mode == "effect" and data.current_predefined_effect is not None:
            playing = ("effect", data.current_predefined_effect)
        else:
            return None
        return next(
            (label for label, target in _animation_options(self.coordinator).items() if target == playing),
            None,
        )

    @override
    async def async_select_option(self, option: str) -> None:
        """Play the chosen movie or effect, as the light's effect list does."""
        kind, number = _animation_options(self.coordinator)[option]
        self.coordinator.end_pause()
        try:
            if kind == "movie":
                await self.client.interview()
                await self.client.set_current_movie(number)
            else:
                await self.client.set_current_predefined_effect(number)
            await self.client.set_mode(kind)
            self.client.default_mode = kind
            if not self.coordinator.data.is_on:
                await self.client.turn_on()
        except (TwinklyError, TimeoutError, ClientError) as exception:
            raise HomeAssistantError(f"Cannot play {option}: {exception}") from exception
        finally:
            await self.coordinator.async_refresh()


class TwinklyLibrarySelect(TwinklyEntity, SelectEntity):
    """Play a recorded movie, uploading it first if the device does not have it."""

    _attr_translation_key = "library"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: TwinklyCoordinator) -> None:
        """Initialize the library select."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.device_info['mac']}_library"
        self.client = coordinator.client

    @property
    @override
    def options(self) -> list[str]:
        """Return the library movies that fit the device."""
        return list(_library_labels(self.coordinator))

    @property
    @override
    def current_option(self) -> str | None:
        """Return the playing movie if it is in the library."""
        data = self.coordinator.data
        if data.current_mode != "movie":
            return None
        playing = next(
            (movie for movie in data.movie_list if movie.get("id") == data.current_movie), None
        )
        if playing is None or not playing.get("unique_id"):
            return None
        return next(
            (
                label
                for label, movie in _library_labels(self.coordinator).items()
                if movie.unique_id.casefold() == str(playing["unique_id"]).casefold()
            ),
            None,
        )

    @override
    async def async_select_option(self, option: str) -> None:
        """Play the movie, uploading it if the device does not have it."""
        movie = _library_labels(self.coordinator)[option]
        self.coordinator.end_pause()
        on_device = next(
            (
                saved
                for saved in self.coordinator.data.movie_list
                if str(saved.get("unique_id", "")).casefold() == movie.unique_id.casefold()
            ),
            None,
        )
        try:
            if on_device is not None:
                movie_id = int(on_device["id"])
            else:
                movie_id = await self._async_upload(movie)
            await self.client.set_current_movie(movie_id)
            await self.client.set_mode("movie")
        except (TwinklyError, TimeoutError, ClientError) as exception:
            raise HomeAssistantError(f"Cannot play {movie.name}: {exception}") from exception
        finally:
            await self.coordinator.async_refresh()
        self.client.default_mode = "movie"

    async def _async_upload(self, movie: LibraryMovie) -> int:
        try:
            frames = await self.hass.async_add_executor_job(read_frames, movie)
        except (OSError, ValueError) as exception:
            raise HomeAssistantError(f"Cannot upload {movie.name}: {exception}") from exception
        available = (await self.client.get_saved_movies()).get("available_frames")
        if isinstance(available, int) and available < movie.frames_number:
            raise HomeAssistantError(
                f"{movie.name} needs {movie.frames_number} frames, the device has "
                f"{available} free: delete a movie first ({movie.frames_number - available} "
                "frames missing)"
            )
        return await upload_movie(self.client, movie, frames)


class TwinklyDeleteMovieSelect(TwinklyEntity, SelectEntity):
    """Delete a movie from the device by choosing it; it reads as a menu."""

    _attr_translation_key = "delete_movie"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_current_option = None

    def __init__(self, coordinator: TwinklyCoordinator) -> None:
        """Initialize the delete select."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.data.device_info['mac']}_delete_movie"
        self.client = coordinator.client

    @property
    @override
    def options(self) -> list[str]:
        """Return the movies on the device."""
        return list(_device_movie_labels(self.coordinator))

    @override
    async def async_select_option(self, option: str) -> None:
        """Delete the chosen movie from the device."""
        movie = _device_movie_labels(self.coordinator)[option]
        self.coordinator.end_pause()
        try:
            await delete_movie(
                self.client, str(movie["unique_id"]), self.coordinator.data.current_mode
            )
        except (TwinklyError, TimeoutError, ClientError) as exception:
            raise HomeAssistantError(f"Cannot delete {movie['name']}: {exception}") from exception
        finally:
            await self.coordinator.async_refresh()
