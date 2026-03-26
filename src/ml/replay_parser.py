"""
Replay Parser — converts a raw Showdown battle log into structured Python objects.

Showdown battle logs are line-based text.  Each line starts with a pipe-delimited
protocol token, e.g.:

    |move|p1a: Garchomp|Earthquake|p2a: Iron Hands
    |-damage|p2a: Iron Hands|201/397
    |switch|p1a: Miraidon|Miraidon|397/397
    |faint|p2a: Iron Hands
    |win|TrainerName

This module parses those tokens into BattleRecord objects that are safe to
serialize to JSON and feed directly into the feature extractor.

Usage:
    from src.ml.replay_parser import parse_replay_file, parse_replay_json

    record = parse_replay_json(json.load(open("data/replays/gen9ou/abc123.json")))
    print(record.winner, record.turns)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Domain objects ────────────────────────────────────────────────────────────

@dataclass
class PokemonState:
    """Snapshot of one Pokemon's state at a point in the battle."""
    species:  str   = ""          # e.g. "Garchomp"
    player:   str   = ""          # "p1" or "p2"
    slot:     str   = ""          # "p1a", "p1b" (doubles), etc.
    hp:       int   = 0           # current HP (absolute, from log if available)
    max_hp:   int   = 0
    hp_pct:   float = 1.0         # 0.0–1.0
    fainted:  bool  = False
    status:   str   = ""          # "brn", "par", "slp", "frz", "psn", "tox"
    boosts:   dict[str, int] = field(default_factory=dict)   # atk/def/spa/spd/spe/acc/eva
    tera_type: str  = ""
    is_tera:  bool  = False


@dataclass
class BattleEvent:
    """One atomic event from the battle log."""
    kind:     str            # "move", "switch", "damage", "heal", "faint",
                             # "status", "boost", "weather", "terrain", "tera", "other"
    turn:     int   = 0
    slot:     str   = ""     # which Pokemon slot is involved (e.g. "p1a")
    detail:   str   = ""     # move name, species name, status, etc.
    target:   str   = ""     # target slot if applicable
    hp_after: float = -1.0   # hp_pct after event (-1 = not applicable)
    raw:      str   = ""     # original log line for debugging


@dataclass
class TurnSnapshot:
    """All events that happened within one turn."""
    turn_number: int
    events:      list[BattleEvent] = field(default_factory=list)

    # Active Pokemon at start of this turn
    p1_active: str = ""   # species name
    p2_active: str = ""


@dataclass
class BattleRecord:
    """
    Fully parsed battle.  This is the main output of the parser and the
    primary input to the feature extractor and ML models.
    """
    replay_id:   str
    format:      str
    rating:      int
    p1_name:     str
    p2_name:     str
    winner:      str    # "p1" | "p2" | "tie" | "unknown"
    winner_name: str

    p1_team:     list[str]  # species names in team preview order
    p2_team:     list[str]

    turns:       list[TurnSnapshot]
    total_turns: int

    # Derived stats filled in post-parse
    p1_fainted:  int = 0   # how many of p1's Pokemon fainted
    p2_fainted:  int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (JSON-safe)."""
        return {
            "replay_id":   self.replay_id,
            "format":      self.format,
            "rating":      self.rating,
            "p1_name":     self.p1_name,
            "p2_name":     self.p2_name,
            "winner":      self.winner,
            "winner_name": self.winner_name,
            "p1_team":     self.p1_team,
            "p2_team":     self.p2_team,
            "total_turns": self.total_turns,
            "p1_fainted":  self.p1_fainted,
            "p2_fainted":  self.p2_fainted,
            "turns": [
                {
                    "turn": t.turn_number,
                    "p1_active": t.p1_active,
                    "p2_active": t.p2_active,
                    "events": [
                        {
                            "kind":     e.kind,
                            "slot":     e.slot,
                            "detail":   e.detail,
                            "target":   e.target,
                            "hp_after": e.hp_after,
                        }
                        for e in t.events
                    ],
                }
                for t in self.turns
            ],
        }


# ── Parser internals ──────────────────────────────────────────────────────────

_HP_RE     = re.compile(r"(\d+)/(\d+)")
_HP_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)/100")
_SLOT_RE   = re.compile(r"^(p[12][a-d]):")   # e.g. "p1a:"
_SPECIES_RE = re.compile(r"^p[12][a-d]: (.+)$")

STATUS_TOKENS = {"brn", "par", "slp", "frz", "psn", "tox"}
BOOST_STATS   = {"atk", "def", "spa", "spd", "spe", "accuracy", "evasion"}


def _slot_player(slot: str) -> str:
    """'p1a' → 'p1'"""
    return slot[:2] if slot else ""


def _extract_species(token: str) -> str:
    """
    Extract species name from a slot+species token like 'p1a: Garchomp'.
    Returns '' if the token doesn't match.
    """
    m = _SPECIES_RE.match(token.strip())
    return m.group(1) if m else token.strip()


def _parse_hp(hp_str: str) -> tuple[int, int, float]:
    """
    Parse HP strings like '201/397' or '0 fnt'.
    Returns (current, max, pct).
    """
    if not hp_str or hp_str.strip() in ("0 fnt", "0"):
        return 0, 0, 0.0
    m = _HP_RE.match(hp_str.strip())
    if m:
        cur, mx = int(m.group(1)), int(m.group(2))
        pct = cur / mx if mx else 0.0
        return cur, mx, pct
    # Some logs use percentage format "72/100"
    m2 = _HP_PCT_RE.match(hp_str.strip())
    if m2:
        pct = float(m2.group(1)) / 100.0
        return -1, -1, pct
    return -1, -1, 1.0


class _Parser:
    """
    Stateful parser that processes lines from a Showdown battle log.
    Instantiate once per replay.
    """

    def __init__(self, replay_id: str, format: str, rating: int) -> None:
        self.replay_id = replay_id
        self.format    = format
        self.rating    = rating

        self.p1_name   = ""
        self.p2_name   = ""
        self.winner    = "unknown"
        self.winner_name = ""

        self.p1_team: list[str] = []
        self.p2_team: list[str] = []

        # Track active Pokemon per slot
        self._active: dict[str, str] = {}   # slot → species

        # Turn tracking
        self._current_turn = 0
        self._turns: list[TurnSnapshot] = []
        self._cur_snapshot: TurnSnapshot | None = None

        # Faint counters
        self.p1_fainted = 0
        self.p2_fainted = 0

    # ── Line dispatchers ──────────────────────────────────────────

    def process_line(self, line: str) -> None:
        if not line.startswith("|"):
            return
        parts = line.split("|")
        if len(parts) < 2:  # pragma: no cover
            return
        token = parts[1]

        dispatch = {
            "player":   self._on_player,
            "poke":     self._on_poke,
            "turn":     self._on_turn,
            "switch":   self._on_switch,
            "drag":     self._on_switch,    # forced switch
            "move":     self._on_move,
            "-damage":  self._on_damage,
            "-heal":    self._on_heal,
            "-status":  self._on_status,
            "-boost":   self._on_boost,
            "-unboost": self._on_boost,
            "faint":    self._on_faint,
            "-terastallize": self._on_tera,
            "win":      self._on_win,
            "tie":      self._on_tie,
        }
        handler = dispatch.get(token)
        if handler:
            handler(parts)

    def _add_event(self, event: BattleEvent) -> None:
        if self._cur_snapshot is not None:
            event.turn = self._current_turn
            self._cur_snapshot.events.append(event)

    # ── Handlers ──────────────────────────────────────────────────

    def _on_player(self, parts: list[str]) -> None:
        # |player|p1|username|...
        if len(parts) < 4:
            return
        slot, name = parts[2], parts[3]
        if slot == "p1":
            self.p1_name = name
        elif slot == "p2":
            self.p2_name = name

    def _on_poke(self, parts: list[str]) -> None:
        # |poke|p1|Garchomp, M|...  — team preview
        if len(parts) < 4:
            return
        player  = parts[2]   # "p1" or "p2"
        species = parts[3].split(",")[0].strip()
        if player == "p1":
            if species not in self.p1_team:
                self.p1_team.append(species)
        elif player == "p2":
            if species not in self.p2_team:
                self.p2_team.append(species)

    def _on_turn(self, parts: list[str]) -> None:
        # |turn|N
        if self._cur_snapshot is not None:
            self._turns.append(self._cur_snapshot)
        self._current_turn = int(parts[2]) if len(parts) > 2 else self._current_turn + 1
        snap = TurnSnapshot(turn_number=self._current_turn)
        snap.p1_active = self._active.get("p1a", "")
        snap.p2_active = self._active.get("p2a", "")
        self._cur_snapshot = snap

    def _on_switch(self, parts: list[str]) -> None:
        # |switch|p1a: Garchomp|Garchomp, L50, M|342/342
        if len(parts) < 4:
            return
        slot_raw = parts[2]
        m = _SLOT_RE.match(slot_raw)
        if not m:
            return
        slot    = m.group(1)
        species = parts[3].split(",")[0].strip()

        # Update active tracker
        self._active[slot] = species

        # If team preview didn't fire (some formats skip it), record species
        player = _slot_player(slot)
        team   = self.p1_team if player == "p1" else self.p2_team
        if species not in team:
            team.append(species)

        hp_pct = -1.0
        if len(parts) > 4:
            _, _, hp_pct = _parse_hp(parts[4])

        self._add_event(BattleEvent(
            kind="switch", slot=slot, detail=species, hp_after=hp_pct,
            raw="|".join(parts),
        ))

    def _on_move(self, parts: list[str]) -> None:
        # |move|p1a: Garchomp|Earthquake|p2a: Iron Hands
        if len(parts) < 4:
            return
        slot_raw = parts[2]
        m = _SLOT_RE.match(slot_raw)
        slot   = m.group(1) if m else slot_raw.rstrip(":")
        move   = parts[3]
        target = ""
        if len(parts) > 4:
            tm = _SLOT_RE.match(parts[4])
            target = tm.group(1) if tm else parts[4]

        self._add_event(BattleEvent(
            kind="move", slot=slot, detail=move, target=target,
            raw="|".join(parts),
        ))

    def _on_damage(self, parts: list[str]) -> None:
        # |-damage|p2a: Iron Hands|201/397
        if len(parts) < 4:
            return
        slot_raw = parts[2]
        m = _SLOT_RE.match(slot_raw)
        slot = m.group(1) if m else ""
        _, _, hp_pct = _parse_hp(parts[3])
        self._add_event(BattleEvent(
            kind="damage", slot=slot, hp_after=hp_pct, raw="|".join(parts),
        ))

    def _on_heal(self, parts: list[str]) -> None:
        # |-heal|p1a: Garchomp|342/342
        if len(parts) < 4:  # pragma: no cover
            return
        m = _SLOT_RE.match(parts[2])
        slot = m.group(1) if m else ""
        _, _, hp_pct = _parse_hp(parts[3])
        self._add_event(BattleEvent(
            kind="heal", slot=slot, hp_after=hp_pct, raw="|".join(parts),
        ))

    def _on_status(self, parts: list[str]) -> None:
        # |-status|p1a: Garchomp|brn
        if len(parts) < 4:  # pragma: no cover
            return
        m = _SLOT_RE.match(parts[2])
        slot   = m.group(1) if m else ""
        status = parts[3]
        self._add_event(BattleEvent(
            kind="status", slot=slot, detail=status, raw="|".join(parts),
        ))

    def _on_boost(self, parts: list[str]) -> None:
        # |-boost|p1a: Garchomp|atk|2
        if len(parts) < 5:
            return
        m    = _SLOT_RE.match(parts[2])
        slot = m.group(1) if m else ""
        stat = parts[3]
        val  = parts[4]
        sign = -1 if parts[1] == "-unboost" else 1
        try:
            amount = sign * int(val)
        except ValueError:
            amount = 0
        self._add_event(BattleEvent(
            kind="boost", slot=slot, detail=f"{stat}:{amount:+d}", raw="|".join(parts),
        ))

    def _on_faint(self, parts: list[str]) -> None:
        # |faint|p2a: Iron Hands
        if len(parts) < 3:
            return
        m    = _SLOT_RE.match(parts[2])
        slot = m.group(1) if m else ""
        self._add_event(BattleEvent(
            kind="faint", slot=slot, hp_after=0.0, raw="|".join(parts),
        ))
        player = _slot_player(slot)
        if player == "p1":
            self.p1_fainted += 1
        elif player == "p2":
            self.p2_fainted += 1

    def _on_tera(self, parts: list[str]) -> None:
        # |-terastallize|p1a: Garchomp|Dragon
        if len(parts) < 4:
            return
        m        = _SLOT_RE.match(parts[2])
        slot     = m.group(1) if m else ""
        tera_type = parts[3]
        self._add_event(BattleEvent(
            kind="tera", slot=slot, detail=tera_type, raw="|".join(parts),
        ))

    def _on_win(self, parts: list[str]) -> None:
        # |win|username
        if len(parts) < 3:
            return
        self.winner_name = parts[2]
        if self.winner_name == self.p1_name:
            self.winner = "p1"
        elif self.winner_name == self.p2_name:
            self.winner = "p2"
        else:
            self.winner = "unknown"

    def _on_tie(self, parts: list[str]) -> None:
        self.winner = "tie"
        self.winner_name = ""

    # ── Build result ──────────────────────────────────────────────

    def build(self) -> BattleRecord:
        # Flush last turn
        if self._cur_snapshot is not None:
            self._turns.append(self._cur_snapshot)

        return BattleRecord(
            replay_id=self.replay_id,
            format=self.format,
            rating=self.rating,
            p1_name=self.p1_name,
            p2_name=self.p2_name,
            winner=self.winner,
            winner_name=self.winner_name,
            p1_team=self.p1_team,
            p2_team=self.p2_team,
            turns=self._turns,
            total_turns=self._current_turn,
            p1_fainted=self.p1_fainted,
            p2_fainted=self.p2_fainted,
        )


# ── Public API ────────────────────────────────────────────────────────────────

def parse_log(
    log_text: str,
    replay_id: str = "unknown",
    format: str = "unknown",
    rating: int = 0,
) -> BattleRecord:
    """
    Parse a raw Showdown battle log string into a BattleRecord.

    Args:
        log_text:  The raw |pipe|delimited battle log text.
        replay_id: Showdown replay ID (e.g. 'gen9ou-1234567890').
        format:    Format string (e.g. 'gen9ou').
        rating:    Player rating for this game (used for data quality filtering).

    Returns:
        BattleRecord with all parsed turn/event data.
    """
    parser = _Parser(replay_id=replay_id, format=format, rating=rating)
    for line in log_text.splitlines():
        parser.process_line(line)
    return parser.build()


def parse_replay_json(data: dict[str, Any]) -> BattleRecord:
    """
    Parse a Showdown replay JSON dict (as returned by the replay API or
    saved by the scraper) into a BattleRecord.
    """
    replay_id = data.get("id", "unknown")
    # Prefer 'formatid' (canonical key e.g. 'gen9vgc2024regh') over 'format' (human-readable '[Gen 9] VGC 2024 Reg H')
    fmt       = data.get("formatid") or data.get("format", "unknown")
    rating    = int(data.get("rating", 0) or 0)
    log_text  = data.get("log", "")
    return parse_log(log_text, replay_id=replay_id, format=fmt, rating=rating)


def parse_replay_file(path: Path) -> BattleRecord:
    """Load a saved replay JSON file and parse it."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return parse_replay_json(data)


def parse_replay_dir(directory: Path, max_count: int = 0) -> list[BattleRecord]:
    """
    Parse all *.json replay files in a directory.

    Args:
        directory: Path to a directory of replay JSON files.
        max_count: If > 0, stop after this many replays.

    Returns:
        List of BattleRecord objects.
    """
    records: list[BattleRecord] = []
    files = sorted(directory.glob("*.json"))
    if max_count:
        files = files[:max_count]
    for path in files:
        try:
            records.append(parse_replay_file(path))
        except Exception as exc:
            log.warning("[parser] Skipping %s: %s", path.name, exc)
    return records


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    import argparse


    ap = argparse.ArgumentParser(description="Parse a Showdown replay file")
    ap.add_argument("path", help="Path to replay JSON file")
    ap.add_argument("--json", action="store_true", help="Output as JSON")
    args = ap.parse_args()

    record = parse_replay_file(Path(args.path))
    if args.json:
        print(json.dumps(record.to_dict(), indent=2))
    else:
        print(f"Replay:  {record.replay_id}")
        print(f"Format:  {record.format}  Rating: {record.rating}")
        print(f"Players: {record.p1_name} vs {record.p2_name}")
        print(f"Winner:  {record.winner_name} ({record.winner})")
        print(f"Turns:   {record.total_turns}")
        print(f"P1 team: {', '.join(record.p1_team)}")
        print(f"P2 team: {', '.join(record.p2_team)}")
        print(f"Faints:  P1={record.p1_fainted}  P2={record.p2_fainted}")
