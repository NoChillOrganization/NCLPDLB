# No Chill Draft League

A Discord bot that runs Pokémon draft leagues, plus battle agents trained to play Pokémon Showdown.

## Language

### League and drafting

**League**:
The persistent season container: teams, standings, trades and matches.
_Avoid_: Season, server

**Draft**:
The one-time event inside a League in which players pick Pokémon to fill their Teams.
_Avoid_: Auction (that is one Draft format), event

**Draft format**:
How a Draft orders picks: snake, linear, auction, tiered or custom.
_Avoid_: Format (bare), draft type

**Game format**:
The game a League is played in, such as Showdown, VGC or Scarlet/Violet.
_Avoid_: Format (bare), game mode

**Team**:
The set of Pokémon a player has drafted.
_Avoid_: Roster

**Match**:
One game between two players in a League; its result updates Standings and ELO ratings.
_Avoid_: Game, fixture

**Standings**:
The League's win/loss table, derived from Match results and separate from ELO ratings.
_Avoid_: Leaderboard, rankings

**ELO rating**:
A player's skill score within one League; the same person has separate ratings in different Leagues.
_Avoid_: Rank, points

**Trade**:
A post-Draft swap of Pokémon between two Teams. Never a Pick.
_Avoid_: Swap, transfer

**Pick**:
A player's selection of one Pokémon from the pool during a Draft.
_Avoid_: Selection, claim

**Ban**:
Removal of a Pokémon from the pool for every player, made before picks start.
_Avoid_: Block, veto

**Tier**:
A Smogon usage-based ranking such as OU or UU.
_Avoid_: Rank, bracket

**Draft tier**:
A League-defined grouping of Pokémon used by a tiered Draft, separate from Smogon Tiers.
_Avoid_: Tier (bare, when meaning this)

### Battle agents

**Battle format**:
A Showdown ruleset a battle is played under, such as `gen9ou`.
_Avoid_: Format (bare), ladder, mode

**Battle agent**:
A trained model that plays Pokémon battles; either a PPO agent or an MCTS agent.
_Avoid_: Bot (that is the Discord bot), AI

**PPO agent**:
A Battle agent trained per Battle format with PPO self-play. Legacy, but still shipped and used by `/spar`.
_Avoid_: RL agent, legacy agent

**MCTS agent**:
A Battle agent whose Transformer policy/value model is trained through MCTS ladder self-play.
_Avoid_: Transformer agent, AlphaZero agent

### Storage

**League sheet**:
The League's Google spreadsheet; the record of completed results.
_Avoid_: Database, spreadsheet (bare)

**Tab**:
One sheet within the League sheet or the Learning sheet.
_Avoid_: Page, worksheet

**Learning sheet**:
The separate Google spreadsheet that logs replays and training runs for Battle agents.
_Avoid_: ML sheet

**Local store**:
The SQLite database holding live Draft state and ELO ratings.
_Avoid_: Database (bare), cache

**Platform database**:
The Postgres database used only by the competitive-data platform; unrelated to the Local store.
_Avoid_: Database (bare), Postgres DB

### Competitive-data platform

**Source**:
An external provider of competitive data, such as Smogon, Pikalytics, Limitless or Showdown.
_Avoid_: Feed, site

**Adapter**:
The code that fetches records from one Source.
_Avoid_: Scraper, connector

**Route**:
The kind of data a record carries: tournament, usage or replay. One Source can serve several Routes.
_Avoid_: Type, kind

**Raw record**:
A fetched payload stored exactly as received, deduplicated by identical payload.
_Avoid_: Raw row, dump

**Canonical row**:
A typed, source-independent row (species, usage, tournament or replay) produced from a Raw record.
_Avoid_: Clean row, normalized record

**Land**:
To store a Raw record.
_Avoid_: Load, save

**Normalize**:
To turn a Raw record into Canonical rows.
_Avoid_: Parse (that is replay parsing), transform

**Ingest**:
The whole pipeline of Land then Normalize.
_Avoid_: Sync (that is the command), import

**Ingest run**:
One execution of Ingest for a single Source.
_Avoid_: Job, sync run

**Dead letter**:
A Raw record that failed to Normalize, parked for review and not retried automatically.
_Avoid_: Failed record, error row

**Canonical species**:
The single agreed identity of a Pokémon across Sources inside the platform.
_Avoid_: Pokémon (inside the platform), mon

**Species alias**:
A Source's spelling of a Pokémon name, mapped to a Canonical species.
_Avoid_: Synonym, nickname
