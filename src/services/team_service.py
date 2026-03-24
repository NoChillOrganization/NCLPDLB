"""
Team Service — Roster management, trades, Showdown import/export, console legality.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass

__all__ = ["TeamService", "TradeResult", "ImportResult", "LegalityResult"]

from src.data.models import Pokemon, TeamRoster, Trade
from src.data.pokeapi import pokemon_db
from src.data.sheets import Tab, sheets

log = logging.getLogger(__name__)

_roster_cache: dict[str, TeamRoster] = {}  # f"{guild_id}:{player_id}" -> roster


@dataclass
class TradeResult:
    success: bool
    trade_id: str = ""
    summary: str = ""
    error: str = ""


@dataclass
class ImportResult:
    success: bool
    pokemon: list[Pokemon] = None
    error: str = ""

    def __post_init__(self):
        if self.pokemon is None:
            self.pokemon = []


@dataclass
class LegalityResult:
    legal: bool
    reason: str


class TeamService:
    def _cache_key(self, guild_id: str, player_id: str, format_key: str = "") -> str:
        """Build a roster cache key.

        Args:
            guild_id: Discord guild ID.
            player_id: Discord user ID.
            format_key: Optional Showdown format string (e.g. "gen9ou"). When empty,
                returns the legacy key for backward compatibility.

        Returns:
            "{guild_id}:{player_id}" when format_key is empty, otherwise
            "{guild_id}:{player_id}:{format_key}".
        """
        if format_key:
            return f"{guild_id}:{player_id}:{format_key}"
        return f"{guild_id}:{player_id}"

    async def get_team(self, guild_id: str, player_id: str) -> TeamRoster | None:
        key = self._cache_key(guild_id, player_id)
        if key in _roster_cache:
            return _roster_cache[key]

        record = sheets.find_row(Tab.TEAM_TEMPLATE, "player_id", player_id)
        if not record or str(record.get("guild_id")) != guild_id:
            return None

        import json
        pokemon_names: list[str] = json.loads(record.get("pokemon_list", "[]"))
        pokemon_list = [p for name in pokemon_names if (p := pokemon_db.find(name))]

        roster = TeamRoster(
            team_id=str(record.get("team_id", "")),
            player_id=player_id,
            guild_id=guild_id,
            pokemon=pokemon_list,
        )
        _roster_cache[key] = roster
        return roster

    async def register_team(
        self,
        guild_id: str,
        player_id: str,
        player_name: str,
        team_name: str,
        team_logo_url: str = "",
        pool: str = "A",
    ) -> TeamRoster:
        """Register or update a player's team name, logo, and pool assignment."""
        key = self._cache_key(guild_id, player_id)
        roster = _roster_cache.get(key) or TeamRoster(
            player_id=player_id,
            guild_id=guild_id,
        )
        roster.team_name = team_name
        roster.team_logo_url = team_logo_url
        roster.pool = pool
        _roster_cache[key] = roster

        # Persist to Team Page Template tab
        slots = [
            (p.name, getattr(p, "tera_type", "")) for p in roster.pokemon
        ]
        sheets.upsert_team_page({
            "player_id": player_id,
            "player_name": player_name,
            "team_name": team_name,
            "team_logo_url": team_logo_url,
            "pool": pool,
            "slots": slots,
        })
        log.info(f"Team registered: {team_name} (pool {pool}) for player {player_id}")
        return roster

    async def propose_trade(
        self,
        guild_id: str,
        from_player: str,
        to_player: str,
        offering: str,
        requesting: str,
    ) -> TradeResult:
        from_team = await self.get_team(guild_id, from_player)
        to_team = await self.get_team(guild_id, to_player)

        if not from_team:
            return TradeResult(success=False, error="You don't have a team.")
        if not to_team:
            return TradeResult(success=False, error="That player doesn't have a team.")

        offer_mon = next((p for p in from_team.pokemon if p.name.lower() == offering.lower()), None)
        request_mon = next((p for p in to_team.pokemon if p.name.lower() == requesting.lower()), None)

        if not offer_mon:
            return TradeResult(success=False, error=f"You don't have {offering}.")
        if not request_mon:
            return TradeResult(success=False, error=f"Opponent doesn't have {requesting}.")

        trade = Trade(
            trade_id=str(uuid.uuid4())[:8],
            league_id="",
            from_player=from_player,
            to_player=to_player,
            pokemon_given=offer_mon.name,
            pokemon_received=request_mon.name,
            status="pending",
        )
        sheets.save_transaction({
            "transaction_id": trade.trade_id,
            "league_id": guild_id,   # stored so accept/decline can locate rosters
            "type": "trade",
            "from_player_id": from_player,
            "from_player_name": "",
            "to_player_id": to_player,
            "to_player_name": "",
            "pokemon_given": trade.pokemon_given,
            "pokemon_received": trade.pokemon_received,
            "status": "pending",
            "approved_by": "",
        })
        return TradeResult(success=True, trade_id=trade.trade_id)

    async def accept_trade(self, player_id: str, trade_id: str) -> TradeResult:
        record = sheets.find_row(Tab.TRANSACTIONS, "transaction_id", trade_id)
        if not record:
            return TradeResult(success=False, error="Trade not found.")
        if str(record.get("to_player_id")) != player_id:
            return TradeResult(success=False, error="This trade is not for you.")
        if record.get("status") != "pending":
            return TradeResult(success=False, error="Trade is no longer pending.")

        given = record["pokemon_given"]
        received = record["pokemon_received"]
        # league_id stores guild_id (set in propose_trade)
        guild_id = str(record.get("league_id", ""))

        from_key = self._cache_key(guild_id, str(record["from_player_id"]))
        to_key = self._cache_key(guild_id, player_id)

        if from_key in _roster_cache and to_key in _roster_cache:
            from_team = _roster_cache[from_key]
            to_team = _roster_cache[to_key]
            from_team.pokemon = [p for p in from_team.pokemon if p.name != given]
            to_team.pokemon = [p for p in to_team.pokemon if p.name != received]
            if mon := pokemon_db.find(received):
                from_team.pokemon.append(mon)
            if mon := pokemon_db.find(given):
                to_team.pokemon.append(mon)

        # Mark accepted in sheets
        record["status"] = "accepted"
        sheets.save_transaction(record)
        return TradeResult(success=True, summary=f"Trade complete! {given} ↔ {received}")

    async def decline_trade(self, player_id: str, trade_id: str) -> TradeResult:
        record = sheets.find_row(Tab.TRANSACTIONS, "transaction_id", trade_id)
        if not record:
            return TradeResult(success=False, error="Trade not found.")
        if str(record.get("to_player_id")) != player_id:
            return TradeResult(success=False, error="This trade is not for you.")
        if record.get("status") != "pending":
            return TradeResult(success=False, error="Trade is no longer pending.")
        record["status"] = "declined"
        sheets.save_transaction(record)
        return TradeResult(success=True, summary="Trade declined.")

    async def import_showdown(
        self,
        guild_id: str,
        player_id: str,
        showdown_text: str,
        format_key: str = "",
    ) -> ImportResult:
        """
        Parse a Showdown team export and update the player's roster.

        Showdown format:
            Garchomp @ Choice Scarf
            Ability: Rough Skin
            EVs: 252 Atk / 4 SpD / 252 Spe
            Jolly Nature
            - Scale Shot
        Also handles nickname format: Speedy (Garchomp) @ Choice Scarf
        """
        pokemon_list: list[Pokemon] = []
        current_name = ""

        for line in showdown_text.strip().split("\n"):
            line = line.strip()
            if not line:
                current_name = ""
                continue

            skip_prefixes = ("-", "Ability:", "EVs:", "IVs:", "Level", "Shiny", "Happiness", "Gigantamax")
            if any(line.startswith(p) for p in skip_prefixes) or line.endswith("Nature"):
                continue

            if current_name == "":
                # Handle: "Nickname (Pokemon) @ Item" or "Pokemon @ Item"
                match = re.match(r"^(?:[\w\s'-]+\s+\()?([A-Za-z][A-Za-z\-'. ]+?)(?:\)|\s*@|$)", line)
                if match:
                    current_name = match.group(1).strip()
                    pokemon = pokemon_db.find(current_name)
                    if pokemon:
                        pokemon_list.append(pokemon)
                    else:
                        log.warning(f"Pokemon not found during import: '{current_name}'")

        if not pokemon_list:
            return ImportResult(success=False, error="No valid Pokemon found. Check the Showdown export format.")

        key = self._cache_key(guild_id, player_id, format_key)
        roster = _roster_cache.get(key) or TeamRoster(player_id=player_id, guild_id=guild_id)
        roster.pokemon = pokemon_list
        _roster_cache[key] = roster

        return ImportResult(success=True, pokemon=pokemon_list)

    async def export_showdown(self, guild_id: str, player_id: str) -> str:
        """Export team roster in Showdown paste format."""
        roster = await self.get_team(guild_id, player_id)
        if not roster:
            return "No team found."
        lines = []
        for p in roster.pokemon:
            lines.append(p.name)
            if p.abilities:
                lines.append(f"Ability: {p.abilities[0]}")
            lines.append("- Tackle")  # Placeholder — full moveset support in Phase 3
            lines.append("")
        return "\n".join(lines)

    async def check_legality(self, pokemon_name: str, game_format: str) -> LegalityResult:
        pokemon = pokemon_db.find(pokemon_name)
        if not pokemon:
            return LegalityResult(legal=False, reason=f"'{pokemon_name}' not found in database.")

        if game_format == "vgc":
            legal = pokemon.vgc_legal
            reason = f"{pokemon.name} is {'✅ legal' if legal else '❌ NOT legal'} in VGC ({pokemon.vgc_season or 'current season'})."
        elif game_format.startswith("showdown"):
            tier = game_format.split("_")[-1].upper() if "_" in game_format else "OU"
            legal = pokemon.showdown_tier.upper() in [tier, "OU"]
            reason = f"{pokemon.name} is in tier **{pokemon.showdown_tier}** on Pokemon Showdown."
        else:
            legal = pokemon.console_legal.get(game_format, False)
            game_names = {
                "sv": "Scarlet/Violet",
                "swsh": "Sword/Shield",
                "bdsp": "Brilliant Diamond/Shining Pearl",
                "legends": "Legends: Arceus",
            }
            game_label = game_names.get(game_format, game_format.upper())
            reason = f"{pokemon.name} is {'✅ available' if legal else '❌ NOT available'} in **{game_label}**."

        return LegalityResult(legal=legal, reason=reason)
