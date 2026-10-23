#!/usr/bin/env python3
"""Generate custom_components/twinkly/translations/en.json from strings.json.

Home Assistant core builds translations from strings.json at release time and
resolves `[%key:common::…%]` references against homeassistant/strings.json. A
custom integration is loaded without that build step, so the resolved file has
to be committed. Run with the test venv, which provides the matching
homeassistant package:

    .venv/bin/python script/gen_translations.py          # write
    .venv/bin/python script/gen_translations.py --check  # exit 1 on drift
"""

import argparse
import json
import pathlib
import re
import sys

import homeassistant

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "custom_components/twinkly/strings.json"
TARGET = ROOT / "custom_components/twinkly/translations/en.json"
COMMON = pathlib.Path(homeassistant.__file__).parent / "strings.json"
KEY_REF = re.compile(r"^\[%key:([a-z0-9_:]+)%\]$")


def resolve(node, common: dict):
    """Return node with every whole-string key reference replaced by its text."""
    if isinstance(node, dict):
        return {k: resolve(v, common) for k, v in node.items()}
    if isinstance(node, str) and (match := KEY_REF.match(node)):
        value = common
        for part in match.group(1).split("::"):
            value = value[part]
        if not isinstance(value, str):
            raise ValueError(f"{node} does not resolve to a string")
        return value
    return node


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if en.json is stale")
    args = parser.parse_args()

    rendered = resolve(json.loads(SOURCE.read_text()), json.loads(COMMON.read_text()))
    text = json.dumps(rendered, indent=2, ensure_ascii=False) + "\n"
    if leftover := re.findall(r"\[%key:[^%]*%\]", text):
        print(f"unresolved references: {leftover}", file=sys.stderr)
        return 1

    if args.check:
        if not TARGET.exists() or TARGET.read_text() != text:
            print(f"{TARGET.relative_to(ROOT)} is stale; run without --check", file=sys.stderr)
            return 1
        return 0

    TARGET.parent.mkdir(exist_ok=True)
    TARGET.write_text(text)
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
