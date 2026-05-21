"""
Core data models using Pydantic v2.
All models are cross-platform and serializable to/from JSON and Google Sheets rows.
"""
from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, Field

# ── Enums ─────────────────────────────────────────────────────

class DraftFormat(str, Enum):
    SNAKE = "snake"
    LINEAR = "linear"
    AUCTION = "auction"
    TIERED = "tiered"
    CUSTOM = "custom"


class DraftStatus(str, Enum):
    SETUP = "setup"
    BAN_PHASE = "ban_phase"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class GameFormat(str, Enum):
    SHOWDOWN = "showdown"
    VGC = "vgc"
    SV = "sv"          # Scarlet/Violet
    SWSH = "swsh"      # Sword/Shield
    BDSP = "bdsp"      # Brilliant Diamond/Shining Pearl
    LEGENDS = "legends"  # Legends: Arceus


class TeraType(str, Enum):
    NORMAL   = "Normal"
    FIRE     = "Fire"
    WATER    = "Water"
    ELECTRIC = "Electric"
    GRASS    = "Grass"
    ICE      = "Ice"
    FIGHTING = "Fighting"
    POISON   = "Poison"
    GROUND   = "Ground"
    FLYING   = "Flying"
    PSYCHIC  = "Psychic"
    BUG      = "Bug"
    ROCK     = "Rock"
    GHOST    = "Ghost"
    DRAGON   = "Dragon"
    DARK     = "Dark"
    STEEL    = "Steel"
    FAIRY    = "Fairy"
    STELLAR  = "Stellar"   # Added in SV DLC (Tera Captain only)


class ShowdownTier(str, Enum):
    UBER = "Uber"
    OU = "OU"
    UUBL = "UUBL"
    UU = "UU"
    RUBL = "RUBL"
    RU = "RU"
    NUBL = "NUBL"
    NU = "NU"
    PUBL = "PUBL"
    PU = "PU"
    NFE = "NFE"
    LC = "LC"
    AG = "AG"          # Anything Goes
    UNTIERED = "Untiered"


# ── Pokemon Model ─────────────────────────────────────────────

class PokemonStats(BaseModel):
    hp: int = 0
    atk: int = 0
    def_: int = Field(0, alias="def")
    spa: int = 0
    spd: int = 0
    spe: int = 0

    @property
    def total(self) -> int:
        return self.hp + self.atk + self.def_ + self.spa + self.spd + self.spe

    model_config = {"populate_by_name": True}


class Pokemon(BaseModel):
    national_dex: int
    name: str
    name_normalized: str = ""   # Lowercase, no special chars (for lookup)
    types: list[str]
    base_stats: PokemonStats
    abilities: list[str] = []
    hidden_ability: str | None = None
    generation: int
    is_legendary: bool = False
    is_mythical: bool = False
    is_paradox: bool = False

    # Competitive data
    showdown_tier: str = ShowdownTier.UNTIERED
    vgc_legal: bool = False
    vgc_season: str = ""

    # Console legality
    console_legal: dict[str, bool] = Field(default_factory=lambda: {
        "sv": False, "swsh": False, "bdsp": False, "legends": False
    })

    # Draft data
    tier_points: int = 1        # Points cost in tiered draft
    smogon_strategy: str = ""   # Role description
    sprite_url: str = ""        # Animated GIF — Showdown ani/{name}.gif
    sprite_url_shiny: str = ""  # Shiny animated GIF — Showdown ani-shiny/{name}.gif
    sprite_url_back: str = ""   # Back sprite animated GIF — Showdown ani-back/{name}.gif

    def model_post_init(self, __context: object) -> None:
        if not self.name_normalized:
            object.__setattr__(self, "name_normalized", self.name.lower().replace(" ", "-").replace("'", "").replace(".", ""))

    @property
    def type_string(self) -> str:
        return " / ".join(t.capitalize() for t in self.types)

    @property
    def speed_tier(self) -> str:
        spe = self.base_stats.spe
        if spe >= 130:
            return "Hyper Fast (130+)"
        if spe >= 110:
            return "Very Fast (110-129)"
        if spe >= 90:
            return "Fast (90-109)"
        if spe >= 70:
            return "Average (70-89)"
        if spe >= 50:
            return "Slow (50-69)"
        return "Very Slow (<50)"


# ── Draft Models ──────────────────────────────────────────────

class DraftPick(BaseModel):
    pick_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    draft_id: str
    player_id: str
    pokemon_name: str
    round: int
    pick_number: int
    game_format: str = GameFormat.SHOWDOWN
    pool: str = "A"                    # Pool A or B
    team_name: str = ""
    tera_type: str = ""                # Tera type assigned at pick time (SV)
    is_tera_captain: bool = False      # Whether this Pokemon is a Tera Captain
    timestamp: str = ""


class DraftBan(BaseModel):
    ban_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    draft_id: str
    player_id: str
    pokemon_name: str
    timestamp: str = ""


MAX_PLAYERS_PER_DRAFT = 16  # Hard cap per pool


class Draft(BaseModel):
    draft_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    guild_id: str
    league_id: str = ""
    commissioner_id: str
    format: DraftFormat = DraftFormat.SNAKE
    status: DraftStatus = DraftStatus.SETUP
    total_rounds: int = 6
    timer_seconds: int = 60
    tier_mode: bool = False
    max_players: int = MAX_PLAYERS_PER_DRAFT
    game_format: str = GameFormat.SHOWDOWN    # showdown or console (sv/swsh/etc.)
    pool: str = "A"                           # Pool A or B
    team_names: dict[str, str] = {}           # player_id -> team name
    team_logos: dict[str, str] = {}           # player_id -> logo URL (Discord CDN)

    # Tera Captain rules (SV format)
    tera_captains_per_team: int = 0           # 0 = disabled; typically 1-2
    tera_types_per_captain: int = 1           # How many tera types each captain gets

    player_order: list[str] = []      # Discord user IDs in pick order
    current_round: int = 1
    current_pick_index: int = 0       # Index in player_order
    picks: list[DraftPick] = []
    bans: list[DraftBan] = []
    budget: dict[str, int] = {}                 # Auction: player_id -> remaining budget
    current_nomination_id: str = ""             # Auction: Pokémon name currently up for bid
    nomination_bids: dict[str, dict[str, int]] = {}  # Auction: nomination_id -> {player_id: amount}
    created_at: str = ""

    @property
    def player_count(self) -> int:
        return len(self.player_order)

    @property
    def total_picks(self) -> int:
        return len(self.picks)

    @property
    def current_player_id(self) -> str | None:
        if not self.player_order:
            return None
        if self.current_round > self.total_rounds:
            return None
        # Snake draft: reverse direction each round
        if self.format == DraftFormat.SNAKE and self.current_round % 2 == 0:
            idx = len(self.player_order) - 1 - self.current_pick_index
        else:
            idx = self.current_pick_index
        return self.player_order[idx % len(self.player_order)]


# ── Team / Roster ─────────────────────────────────────────────

class TeamRoster(BaseModel):
    team_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    player_id: str
    guild_id: str
    league_id: str = ""
    team_name: str = ""
    team_logo_url: str = ""   # Discord CDN URL for team logo image
    pool: str = "A"
    pokemon: list[Pokemon] = []
    game_format: GameFormat = GameFormat.SHOWDOWN
    updated_at: str = ""

    @property
    def type_coverage(self) -> list[str]:
        types: set[str] = set()
        for p in self.pokemon:
            types.update(p.types)
        return sorted(types)


# ── Match / ELO ───────────────────────────────────────────────

class MatchResult(BaseModel):
    match_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    league_id: str
    player1_id: str
    player2_id: str
    winner_id: str
    game_format: str = GameFormat.SHOWDOWN
    replay_url: str = ""
    video_url: str = ""
    timestamp: str = ""


class PlayerElo(BaseModel):
    player_id: str
    guild_id: str
    display_name: str = ""
    elo: int = 1000
    wins: int = 0
    losses: int = 0
    streak: int = 0

    @property
    def win_rate(self) -> float:
        total = self.wins + self.losses
        return (self.wins / total * 100) if total > 0 else 0.0


# ── Trade ─────────────────────────────────────────────────────

class Trade(BaseModel):
    trade_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    league_id: str
    from_player: str
    to_player: str
    pokemon_given: str
    pokemon_received: str
    status: str = "pending"   # pending | accepted | declined | cancelled
    timestamp: str = ""
