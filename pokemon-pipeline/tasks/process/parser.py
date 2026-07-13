"""Showdown paste parsing, paste-URL resolution, and canonical normalization for hashing."""

from __future__ import annotations

import logging
import re

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_HEADER_RE = re.compile(
    r"^(?:(?P<nickname>[^()@]+?)\s*\((?P<species>[^)]+)\)|(?P<species_only>[^@]+?))"
    r"(?:\s*\((?P<gender>[MF])\))?"
    r"(?:\s*@\s*(?P<item>.+))?$"
)
_MOVE_RE = re.compile(r"^-\s*(.+)$")


class ShowdownPasteParser:
    """Parses a Showdown export into a list of structured Pokemon-set dicts.

    Never raises on malformed input — returns whatever it could parse and logs
    a warning for the rest, per project convention (00_master_context.xml).
    """

    def parse(self, raw_paste: str) -> list[dict]:
        if not raw_paste or not raw_paste.strip():
            logger.warning("parse() called with empty paste")
            return []

        sets: list[dict] = []
        blocks = [b for b in re.split(r"\n\s*\n", raw_paste.strip()) if b.strip()]
        for slot_index, block in enumerate(blocks):
            try:
                sets.append(self._parse_block(block, slot_index))
            except Exception as exc:  # noqa: BLE001 - never raise, log + skip
                logger.warning("Failed to parse Pokemon block %d: %s", slot_index, exc)
        return sets

    def _parse_block(self, block: str, slot_index: int) -> dict:
        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        header = lines[0] if lines else ""

        result: dict = {
            "slot_index": slot_index,
            "species": None,
            "nickname": None,
            "item": None,
            "ability": None,
            "nature": None,
            "tera_type": None,
            "moves": [],
            "evs": {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            "ivs": {"hp": 31, "atk": 31, "def": 31, "spa": 31, "spd": 31, "spe": 31},
            "level": 50,
            "gender": None,
            "is_shiny": False,
        }

        m = _HEADER_RE.match(header)
        if m:
            if m.group("species"):
                result["nickname"] = m.group("nickname").strip() if m.group("nickname") else None
                result["species"] = m.group("species").strip()
            else:
                result["species"] = (m.group("species_only") or "").strip()
            if m.group("gender"):
                result["gender"] = m.group("gender")
            if m.group("item"):
                result["item"] = m.group("item").strip()
        else:
            # Regex fallback failed entirely — best-effort: species is the whole header
            result["species"] = header.strip() or None
            logger.warning("Header regex fallback used for: %r", header)

        for line in lines[1:]:
            stripped = line.strip()
            move_m = _MOVE_RE.match(stripped)
            if move_m:
                result["moves"].append(move_m.group(1).strip())
            elif stripped.startswith("Ability:"):
                result["ability"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("Level:"):
                try:
                    result["level"] = int(stripped.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif stripped.startswith("Shiny:"):
                result["is_shiny"] = stripped.split(":", 1)[1].strip().lower() == "yes"
            elif stripped.startswith("Tera Type:"):
                result["tera_type"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("EVs:"):
                result["evs"].update(self._parse_stat_line(stripped.split(":", 1)[1]))
            elif stripped.startswith("IVs:"):
                result["ivs"].update(self._parse_stat_line(stripped.split(":", 1)[1]))
            elif stripped.endswith("Nature"):
                result["nature"] = stripped.replace("Nature", "").strip()

        # Handle formes with dashes inside species (Calyrex-Shadow, Indeedee-F, etc.)
        # already preserved verbatim since we don't split on '-'.

        while len(result["moves"]) < 4:
            result["moves"].append(None)
        result["moves"] = result["moves"][:4]

        return result

    @staticmethod
    def _parse_stat_line(text: str) -> dict:
        stat_map = {"HP": "hp", "Atk": "atk", "Def": "def", "SpA": "spa", "SpD": "spd", "Spe": "spe"}
        out: dict[str, int] = {}
        for chunk in text.split("/"):
            chunk = chunk.strip()
            if not chunk:
                continue
            parts = chunk.split()
            if len(parts) != 2:
                continue
            value_str, stat_name = parts
            key = stat_map.get(stat_name)
            if key is None:
                continue
            try:
                out[key] = int(value_str)
            except ValueError:
                continue
        return out


_POKEPASTE_RE = re.compile(r"pokepast\.es/([a-f0-9]+)", re.IGNORECASE)
_PASTEBIN_RE = re.compile(r"pastebin\.com/([A-Za-z0-9]+)")
_GDOCS_RE = re.compile(r"docs\.google\.com/document/d/([\w-]+)")


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
async def resolve_paste_url(url: str) -> str:
    """Resolve any of: pokepast.es, pastebin.com, Google Docs /pub URL, or raw text -> raw paste."""
    stripped = url.strip()

    if not stripped.lower().startswith("http"):
        # Not a URL at all — treat as raw paste text already.
        return url

    url = stripped

    async with httpx.AsyncClient(timeout=10.0) as client:
        pp_match = _POKEPASTE_RE.search(url)
        if pp_match:
            try:
                from pokepastes_scraper import PokePasteScraper

                paste = PokePasteScraper(url)
                return paste.get_paste()
            except Exception as exc:  # noqa: BLE001 - lib unavailable or its own network path failed
                logger.debug("pokepastes-scraper unavailable (%s), falling back to /raw", exc)
                resp = await client.get(f"{url.rstrip('/')}/raw")
                resp.raise_for_status()
                return resp.text

        pb_match = _PASTEBIN_RE.search(url)
        if pb_match:
            resp = await client.get(f"https://pastebin.com/raw/{pb_match.group(1)}")
            resp.raise_for_status()
            return resp.text

        if _GDOCS_RE.search(url) or "/pub" in url:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text

        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


_FIELD_LINE_PREFIXES = ("ability:", "level:", "shiny:", "tera type:", "evs:", "ivs:", "gender:")


def _is_field_line(line: str) -> bool:
    """True for any Showdown set-detail line (moves, stats, ability...), false for a species header."""
    lower = line.lower()
    return line.startswith("-") or lower.endswith("nature") or lower.startswith(_FIELD_LINE_PREFIXES)


def normalize_paste(raw_paste: str) -> str:
    """Canonical string for deterministic SHA-256 hashing regardless of whitespace/order.

    Blocks are detected by species-header lines rather than blank-line separators, so stray
    blank/whitespace-only noise anywhere in the paste can't fragment or merge Pokemon blocks.
    """
    lines = [line.strip() for line in raw_paste.split("\n") if line.strip()]

    blocks: list[list[str]] = []
    for line in lines:
        if not blocks or not _is_field_line(line):
            blocks.append([line])
        else:
            blocks[-1].append(line)

    normalized_blocks = []
    for block_lines in blocks:
        lower_lines = [line.lower() for line in block_lines]
        move_lines = sorted(line for line in lower_lines if line.startswith("-"))
        other_lines = [line for line in lower_lines if not line.startswith("-")]
        normalized_blocks.append("\n".join(other_lines + move_lines))
    return "\n\n".join(sorted(normalized_blocks))
