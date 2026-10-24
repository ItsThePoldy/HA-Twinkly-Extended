"""Display names for the predefined effects of Twinkly devices.

A device reports its predefined effects only as an ordered list of unique ids.
effect_names.yaml maps those ids to names, per device variant: each rule names
the device fields it matches on, and the matching rule with the most fields
wins, so a narrower rule (one hardware revision) overrides a broader one (the
whole product code).

Within the winning rule an id mapped to a name is shown under that name, an id
mapped to null is hidden, and an id the rule does not mention is shown as
"Effect <n>". A device no rule matches shows every effect as "Effect <n>".
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
import pathlib
import re
from typing import Any

import yaml

RULES_FILE = pathlib.Path(__file__).parent / "effect_names.yaml"

# Fields of the device details (gestalt) a rule may match on. Firmware version
# is deliberately absent: it changes with every update, so a rule bound to it
# would silently stop applying.
MATCH_FIELDS = frozenset({"product_code", "hardware_version", "fw_family", "led_profile"})

# Movies appear in the effect list as "<id> <name>"; a predefined effect name in
# that shape would be read back as a movie.
_MOVIE_SHAPED = re.compile(r"^\d+ ")
_FALLBACK_SHAPED = re.compile(r"^Effect \d+$")


@dataclass(frozen=True)
class EffectNameRule:
    """Names for the predefined effects of one device variant."""

    match: Mapping[str, str]
    effects: Mapping[str, str | None]

    @property
    def specificity(self) -> int:
        """Return how many device fields the rule matches on."""
        return len(self.match)

    def applies_to(self, device_info: Mapping[str, Any]) -> bool:
        """Return whether every matched field equals the device's value."""
        return all(
            str(device_info.get(field)) == value for field, value in self.match.items()
        )


def fallback_name(index: int) -> str:
    """Return the name shown for an effect no rule names."""
    return f"Effect {index + 1}"


def parse_rules(data: Any) -> list[EffectNameRule]:
    """Validate the parsed content of effect_names.yaml and build the rules.

    Raises ValueError naming the offending rule.
    """
    if not isinstance(data, list):
        raise ValueError("effect names: top level must be a list of rules")
    rules: list[EffectNameRule] = []
    for position, raw in enumerate(data):
        where = f"effect names rule #{position}"
        if not isinstance(raw, dict) or set(raw) != {"match", "effects"}:
            raise ValueError(f"{where}: needs exactly the keys 'match' and 'effects'")
        match, effects = raw["match"], raw["effects"]
        if not isinstance(match, dict) or not match:
            raise ValueError(f"{where}: 'match' must be a non-empty mapping")
        if unknown := set(match) - MATCH_FIELDS:
            raise ValueError(f"{where}: cannot match on {sorted(unknown)}")
        if not all(isinstance(value, str) and value for value in match.values()):
            raise ValueError(f"{where}: match values must be non-empty strings")
        if not isinstance(effects, dict) or not effects:
            raise ValueError(f"{where}: 'effects' must be a non-empty mapping")
        names: list[str] = []
        for unique_id, name in effects.items():
            if not isinstance(unique_id, str) or not unique_id:
                raise ValueError(f"{where}: effect ids must be non-empty strings")
            if name is None:
                continue
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"{where}: name of {unique_id} must be a string or null")
            if _MOVIE_SHAPED.match(name) or _FALLBACK_SHAPED.match(name):
                raise ValueError(f"{where}: name {name!r} collides with a generated name")
            names.append(name)
        if len(names) != len(set(names)):
            raise ValueError(f"{where}: duplicate effect names")
        rules.append(EffectNameRule(dict(match), dict(effects)))

    for first, second in combinations(rules, 2):
        if first.specificity == second.specificity and all(
            first.match[field] == second.match[field]
            for field in first.match.keys() & second.match.keys()
        ):
            raise ValueError(
                f"effect names: rules {dict(first.match)} and {dict(second.match)} "
                "can match the same device with equal specificity"
            )
    return rules


def load_rules(path: pathlib.Path = RULES_FILE) -> list[EffectNameRule]:
    """Read and validate a rules file. Blocking: run it in the executor."""
    return parse_rules(yaml.safe_load(path.read_text(encoding="utf-8")))


def resolve_effect_names(
    rules: Sequence[EffectNameRule],
    device_info: Mapping[str, Any],
    unique_ids: Sequence[str],
) -> dict[int, str]:
    """Return {effect index: display name} for the effects the device reports."""
    matching = [rule for rule in rules if rule.applies_to(device_info)]
    if not matching:
        return {index: fallback_name(index) for index in range(len(unique_ids))}
    rule = max(matching, key=lambda candidate: candidate.specificity)
    names: dict[int, str] = {}
    for index, unique_id in enumerate(unique_ids):
        if unique_id not in rule.effects:
            names[index] = fallback_name(index)
        elif (name := rule.effects[unique_id]) is not None:
            names[index] = name
    return names
