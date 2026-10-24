"""Tests for the predefined-effect name rules."""

from typing import Any

import pytest

from custom_components.twinkly.effect_names import (
    EffectNameRule,
    load_rules,
    parse_rules,
    resolve_effect_names,
)

UID = [f"00000000-0000-0000-0000-00000000000{n}" for n in range(1, 6)]
CURTAIN = {"product_code": "TWW210SPP2", "hardware_version": "308", "fw_family": "G"}


def rule(match: dict[str, str], effects: dict[str, str | None]) -> dict[str, Any]:
    """Build one raw rule as it appears in the YAML file."""
    return {"match": match, "effects": effects}


def test_shipped_rules_are_valid() -> None:
    """The rules file shipped with the integration passes validation."""
    rules = load_rules()
    assert rules, "the shipped rules file holds no rules"


def test_shipped_rules_name_the_measured_curtain() -> None:
    """The Curtain 210 RGBW measured in docs/device-notes.md gets its five names."""
    assert resolve_effect_names(load_rules(), CURTAIN, UID) == {
        0: "Rainbow",
        1: "Silver Shower",
        2: "Color Glow",
        3: "Fireworks",
        4: "Spring Glow",
    }


def test_no_matching_rule_falls_back_for_every_effect() -> None:
    """A device no rule matches shows all effects as "Effect <n>"."""
    rules = parse_rules([rule({"product_code": "OTHER"}, {UID[0]: "Rainbow"})])

    assert resolve_effect_names(rules, CURTAIN, UID[:3]) == {
        0: "Effect 1",
        1: "Effect 2",
        2: "Effect 3",
    }


def test_null_hides_and_unlisted_id_falls_back() -> None:
    """Within the winning rule, null hides an effect and an unlisted id falls back."""
    rules = parse_rules(
        [rule({"product_code": "TWW210SPP2"}, {UID[0]: "Rainbow", UID[1]: None})]
    )

    assert resolve_effect_names(rules, CURTAIN, UID[:3]) == {
        0: "Rainbow",
        2: "Effect 3",
    }


def test_most_specific_matching_rule_wins() -> None:
    """A rule matching more fields overrides a broader one, regardless of order."""
    narrow = rule({"product_code": "TWW210SPP2", "hardware_version": "308"}, {UID[0]: "Narrow"})
    broad = rule({"product_code": "TWW210SPP2"}, {UID[0]: "Broad"})

    for ordered in ([narrow, broad], [broad, narrow]):
        assert resolve_effect_names(parse_rules(ordered), CURTAIN, UID[:1]) == {0: "Narrow"}

    other_revision = CURTAIN | {"hardware_version": "200"}
    assert resolve_effect_names(parse_rules([narrow, broad]), other_revision, UID[:1]) == {
        0: "Broad"
    }


def test_match_compares_device_values_as_strings() -> None:
    """A numeric field reported by the device matches its string in the rules."""
    rules = parse_rules([rule({"hardware_version": "308"}, {UID[0]: "Rainbow"})])

    assert resolve_effect_names(rules, {"hardware_version": 308}, UID[:1]) == {0: "Rainbow"}


def test_rule_applies_only_when_every_field_matches() -> None:
    """A rule with one non-matching field does not apply."""
    applies = EffectNameRule({"product_code": "TWW210SPP2", "fw_family": "G"}, {}).applies_to
    assert applies(CURTAIN)
    assert not applies(CURTAIN | {"fw_family": "F"})
    assert not applies({"product_code": "TWW210SPP2"})


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"match": {}}, "top level must be a list"),
        ([{"match": {"product_code": "X"}}], "exactly the keys"),
        ([rule({"product_code": "X"}, {UID[0]: "A"}) | {"extra": 1}], "exactly the keys"),
        ([rule({}, {UID[0]: "A"})], "'match' must be a non-empty mapping"),
        ([rule({"fw_version": "2.11.0"}, {UID[0]: "A"})], "cannot match on"),
        ([rule({"product_code": ""}, {UID[0]: "A"})], "non-empty strings"),
        ([rule({"product_code": 308}, {UID[0]: "A"})], "non-empty strings"),
        ([rule({"product_code": "X"}, {})], "'effects' must be a non-empty mapping"),
        ([rule({"product_code": "X"}, {"": "A"})], "effect ids must be"),
        ([rule({"product_code": "X"}, {UID[0]: " "})], "must be a string or null"),
        ([rule({"product_code": "X"}, {UID[0]: 3})], "must be a string or null"),
        ([rule({"product_code": "X"}, {UID[0]: "1 Rainbow"})], "collides with a generated"),
        ([rule({"product_code": "X"}, {UID[0]: "Effect 2"})], "collides with a generated"),
        ([rule({"product_code": "X"}, {UID[0]: "A", UID[1]: "A"})], "duplicate effect names"),
        (
            [rule({"product_code": "X"}, {UID[0]: "A"}), rule({"product_code": "X"}, {UID[0]: "B"})],
            "equal specificity",
        ),
        (
            [
                rule({"product_code": "X", "fw_family": "G"}, {UID[0]: "A"}),
                rule({"product_code": "X", "hardware_version": "308"}, {UID[0]: "B"}),
            ],
            "equal specificity",
        ),
    ],
)
def test_invalid_rules_are_rejected(data: Any, message: str) -> None:
    """Every violation form is refused with a message naming the problem."""
    with pytest.raises(ValueError, match=message):
        parse_rules(data)


def test_disjoint_rules_of_equal_specificity_are_accepted() -> None:
    """Two equally specific rules that can never match the same device coexist."""
    rules = parse_rules(
        [
            rule({"product_code": "X", "fw_family": "G"}, {UID[0]: "A"}),
            rule({"product_code": "Y", "hardware_version": "308"}, {UID[0]: "B"}),
        ]
    )
    assert len(rules) == 2
