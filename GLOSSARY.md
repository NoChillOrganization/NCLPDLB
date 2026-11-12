# No Chill Draft League

A Discord bot that runs Pokémon draft leagues, plus battle agents trained to play Pokémon Showdown.

## Language

### League and drafting

**League**:
The persistent season container: teams, standings, trades and matches. One League per Discord server.
_Avoid_: Season, server

**Draft**:
The one-time event inside a League in which Coaches pick Pokémon to fill their Teams.
_Avoid_: Auction (that is one Draft format), event

**Draft format**:
How a Draft orders picks: snake, linear, auction, tiered or custom.
_Avoid_: Format (bare), draft type

**Game format**:
The game a League is played in, such as Showdown, VGC or Scarlet/Violet.
_Avoid_: Format (bare), game mode, mode

**Coach**:
A League participant; also the name of the base Discord role (Draft League Coaches).
_Avoid_: Player, captain, manager

**Commissioner**:
The user who created a Draft; only they can start it. Not a Discord role.
_Avoid_: Admin, owner

**Guildmaster**:
The top Discord role; runs League, Draft and training administration.
_Avoid_: Commissioner (that is a per-Draft user), admin

**Moderator**:
The middle Discord role; can skip, pause, resume and override picks and write to the League sheet.
_Avoid_: Mod (in docs), admin

**Pool**:
Pool A or Pool B: a split of a League's Coaches into two conferences, with separate Tabs.
_Avoid_: Conference, group, division

**Draft pool**:
The Pokémon still available to pick in a Draft.
_Avoid_: Pool (bare), pokédex

**Team**:
The set of Pokémon a Coach has drafted.
_Avoid_: Roster

**Tera Captain**:
A Pokémon designated on a Team to carry a Tera type; Scarlet/Violet Leagues only.
_Avoid_: Captain (bare)

**Match**:
One game between two Coaches in a League; its Result updates Standings and ELO ratings.
_Avoid_: Game, fixture

**Result**:
A reported Match outcome that updates ELO ratings (`/result`).
_Avoid_: Score

**Sheet result**:
A Match outcome written to the League sheet by hand without updating ELO ratings (`/sheet-result`).
_Avoid_: Manual result

**Standings**:
The League's table of ELO ratings with wins and losses, sorted by ELO.
_Avoid_: Leaderboard, rankings

**ELO rating**:
A Coach's skill score within one League.
_Avoid_: Rank, points

**Trade**:
A post-Draft swap of Pokémon between two Teams. Never a Pick.
_Avoid_: Swap, transfer

**Pick**:
A Coach's selection of one Pokémon from the Draft pool.
_Avoid_: Selection, claim

**Ban**:
Removal of a Pokémon from the Draft pool for every Coach, made before picks start.
_Avoid_: Block, veto

**Budget**:
The auction currency each Coach holds, counted in points (default 1000).
_Avoid_: Coins, money

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
A Battle agent driven by a Transformer policy/value model. By default it runs with zero search simulations (a one-ply prior), not full tree search.
_Avoid_: Transformer agent, AlphaZero agent

**Self-play**:
Battle agents playing each other, either against a lagging copy of themselves (PPO) or two MCTS players on a local server.
_Avoid_: Ladder (that is playing humans)

**Ladder loop**:
Repeated ranked-ladder games played by a Battle agent against real human opponents on public Showdown, filling the replay buffer.
_Avoid_: Self-play

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
The kind of data a record carries: tournament, usage or replay.
_Avoid_: Type, kind

**Raw record**:
A fetched payload stored exactly as received, deduplicated by identical payload.
_Avoid_: Raw row, dump

**Canonical row**:
A typed, source-independent row (species, usage, tournament or replay) produced from a Raw record.
_Avoid_: Clean row, normalized record

**Land**:
To store a Raw record. The `landed` run statistic counts every record processed, duplicates included.
_Avoid_: Load, save

**Normalize**:
To turn a Raw record into Canonical rows.
_Avoid_: Parse (that is replay parsing), transform

**Ingest**:
The whole pipeline of Land then Normalize. Workflow and alert names (`sync-prod`, `STALE_SYNC`) say "sync" for this.
_Avoid_: Sync (outside those names), import

**Ingest run**:
One execution of Ingest for a single Source.
_Avoid_: Job, sync run

**Dead letter**:
A Raw record that failed to Normalize, parked for review and not retried automatically.
_Avoid_: Failed record, error row

**Run failure**:
An Ingest run that failed as a whole, such as exhausted retries; stored in the dead-letter table with no record attached.
_Avoid_: Dead letter (that is record-level)

**Dry run**:
An Ingest that fetches and validates records without writing to the Platform database (`--dry-run`).
_Avoid_: Test run

**Idempotency check**:
A real Ingest into a throwaway database, run twice, that asserts the second run lands no new Raw records (`sync-dryrun`).
_Avoid_: Dry run

**Pairing**:
A tournament round pairing of two entrants (the platform `match` table); not a League Match.
_Avoid_: Match (that is a League game)

**Canonical species**:
The single agreed identity of a Pokémon across Sources inside the platform.
_Avoid_: Pokémon (inside the platform), mon

**Species alias**:
A Source's spelling of a Pokémon name, mapped to a Canonical species.
_Avoid_: Synonym, nickname

### Discord

**Command sync**:
Registering the bot's slash commands with Discord, hash-gated to avoid rate limits.
_Avoid_: Sync (bare)
