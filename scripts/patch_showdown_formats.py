#!/usr/bin/env python3
"""
patch_showdown_formats.py -- CI helper for train-models.yml

Patches config/formats.ts in a freshly-cloned pokemon-showdown repository
to remove tier banlists so poke-env's random team builder can submit any
Pokemon without being rejected by Showdown's legality checker.

Formats patched:
  Singles tiers : Ubers, UU, RU, NU, PU, ZU, LC
  Doubles tiers : Doubles Ubers, Doubles UU

Strategy: replace each problem format's banlist with [] and replace
cascaded ruleset references (e.g. "[Gen 9] UU") with a flat minimal ruleset
so no bans are inherited from parent tiers.

Usage:
    python3 scripts/patch_showdown_formats.py /tmp/showdown/config/formats.ts
"""
from __future__ import annotations
import re
import sys

SAFE_RULES = (
    "['Team Preview', 'HP Percentage Mod', "
    "'Cancel Mod', 'Endless Battle Clause', 'Sleep Clause Mod']"
)

PATCHES: list[tuple[str, str, str]] = [
    (
        "Ubers banlist",
        r'(\{\s*name:\s*"\[Gen 9\] Ubers"[\s\S]*?)banlist:\s*\[[^\]]*\]',
        r'\1banlist: []',
    ),
    (
        "UU ruleset+banlist",
        (
            r'(\{\s*name:\s*"\[Gen 9\] UU"\s*,\s*mod:\s*\'gen9\'\s*,\s*)'
            r"ruleset:\s*\['\[Gen 9\] OU'\]\s*,\s*banlist:\s*\[[^\]]*\]"
        ),
        r'\1ruleset: ' + SAFE_RULES + r', banlist: []',
    ),
    (
        "RU ruleset+banlist",
        (
            r'(\{\s*name:\s*"\[Gen 9\] RU"\s*,\s*mod:\s*\'gen9\'\s*,\s*)'
            r"ruleset:\s*\['\[Gen 9\] UU'\]\s*,\s*banlist:\s*\[[^\]]*\]"
        ),
        r'\1ruleset: ' + SAFE_RULES + r', banlist: []',
    ),
    (
        "NU ruleset+banlist",
        (
            r'(\{\s*name:\s*"\[Gen 9\] NU"\s*,\s*mod:\s*\'gen9\'\s*,\s*)'
            r"ruleset:\s*\['\[Gen 9\] RU'\]\s*,\s*banlist:\s*\[[^\]]*\]"
        ),
        r'\1ruleset: ' + SAFE_RULES + r', banlist: []',
    ),
    (
        "PU ruleset+banlist",
        (
            r'(\{\s*name:\s*"\[Gen 9\] PU"\s*,\s*mod:\s*\'gen9\'\s*,\s*)'
            r"ruleset:\s*\['\[Gen 9\] NU'\]\s*,\s*banlist:\s*\[[^\]]*\]"
        ),
        r'\1ruleset: ' + SAFE_RULES + r', banlist: []',
    ),
    (
        "ZU ruleset+banlist",
        (
            r'(\{\s*name:\s*"\[Gen 9\] ZU"\s*,\s*mod:\s*\'gen9\'\s*,\s*)'
            r"ruleset:\s*\['\[Gen 9\] PU'\]\s*,\s*banlist:\s*\[[^\]]*\]"
        ),
        r'\1ruleset: ' + SAFE_RULES + r', banlist: []',
    ),
    (
        "LC ruleset+banlist",
        (
            r"(\{\s*name:\s*\"\[Gen 9\] LC\"\s*,\s*mod:\s*'gen9'\s*,\s*)"
            r"ruleset:\s*\['Little Cup',\s*'Standard'\]\s*,\s*banlist:\s*\[[\s\S]*?\]\s*,"
        ),
        r"\1ruleset: " + SAFE_RULES + r", banlist: [],",
    ),
    (
        "Doubles Ubers ruleset",
        (
            r"(\{\s*name:\s*\"\[Gen 9\] Doubles Ubers\"\s*,\s*mod:\s*'gen9'\s*,\s*"
            r"gameType:\s*'doubles'\s*,\s*)ruleset:\s*\[[^\]]*\]"
        ),
        r"\1ruleset: " + SAFE_RULES + r", banlist: []",
    ),
    (
        "Doubles UU ruleset+banlist",
        (
            r"(\{\s*name:\s*\"\[Gen 9\] Doubles UU\"\s*,\s*mod:\s*'gen9'\s*,\s*"
            r"gameType:\s*'doubles'\s*,\s*)ruleset:\s*\['\[Gen 9\] Doubles OU'\]\s*,\s*"
            r"banlist:\s*\[[^\]]*\]"
        ),
        r"\1ruleset: " + SAFE_RULES + r", banlist: []",
    ),
]


def patch_formats(path: str) -> None:
    with open(path) as fh:
        src = fh.read()

    failed: list[str] = []
    for label, pattern, replacement in PATCHES:
        new_src, count = re.subn(pattern, replacement, src, flags=re.DOTALL)
        if count == 0:
            failed.append(label)
            print(f"  WARNING: patch did not match for '{label}'")
        else:
            print(f"  OK: patched {count} occurrence(s) for '{label}'")
        src = new_src

    with open(path, "w") as fh:
        fh.write(src)

    if failed:
        print(
            f"\nWARN: {len(failed)} patch(es) did not apply: {failed}\n"
            "Showdown source may have changed upstream; affected formats may still reject teams.",
            file=sys.stderr,
        )
    else:
        print("All patches applied successfully.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path/to/config/formats.ts>", file=sys.stderr)
        sys.exit(1)
    patch_formats(sys.argv[1])
