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

### Draft mechanics

**Draft status**:
The stage of a Draft: setup, ban phase, active, paused or completed.
_Avoid_: State, phase

**Ban phase**:
The stage of a custom-format Draft in which any joined Coach can ban before picks begin.
_Avoid_: Adaptive Ban

**Round**:
One full pass of the Draft order; snake order reverses on even Rounds.
_Avoid_: Turn

**Pick number**:
A Pick's overall position in the Draft, not its position in the Round.
_Avoid_: Turn, slot

**Pick timer**:
The per-Pick countdown in seconds (default 60, 0 for none); expiry auto-skips the current Coach.
_Avoid_: Clock

**Auto-skip**:
The Pick timer advancing the Draft past a Coach who ran out of time.
_Avoid_: Timeout skip

**Force-skip**:
A Moderator advancing the Draft past a Coach (`/admin-skip`).
_Avoid_: Auto-skip

**Pause / Resume**:
A Moderator halting a Draft (cancelling the Pick timer) and continuing it; Resume does not restart the timer.
_Avoid_: Stop

**Override pick**:
A Moderator replacing one drafted Pokémon with another; held in memory only and not written to the League sheet.
_Avoid_: Swap (that is a Trade), edit

**Reset draft**:
Wiping a Draft from memory and the Local store.
_Avoid_: Cancel, delete

**Nomination**:
The Pokémon currently up for bid in an auction Draft.
_Avoid_: Lot, listing

**Bid**:
A Coach's offer on a Nomination, at least 1, at most their Budget, and above the current high bid.
_Avoid_: Offer

**Close nomination**:
Awarding a Nomination to the highest Bidder and deducting their Budget.
_Avoid_: Sell, hammer

### Pokémon data

**Base stat total**:
The sum of a Pokémon's six base stats (BST).
_Avoid_: Stat total, power

**Speed tier**:
A bucket of base Speed from Hyper Fast to Very Slow; unrelated to Smogon Tiers.
_Avoid_: Tier (bare), speed bracket

**Tera type**:
The type a Pokémon becomes when it terastallizes; Stellar is for Tera Captains only.
_Avoid_: Tera (bare)

**VGC legal**:
Whether a Pokémon is allowed in the current VGC season.
_Avoid_: Legal (bare)

**Hidden ability**:
A Pokémon's rare alternate ability.
_Avoid_: HA (in docs)

**Draft tier points**:
The cost of a Pokémon in a tiered Draft (default 1).
_Avoid_: Tier cost, price

**Showdown paste**:
Showdown's text format for a Team, used by team import and export.
_Avoid_: Export string, team text

**Legality**:
Whether a Pokémon may be used in a Game format, checked by `/legality`.
_Avoid_: Eligibility

### Team analytics

**Team analysis report**:
The summary of a Team: coverage, weaknesses, speed, archetype, threat score and role distribution.
_Avoid_: Scouting report

**Coverage**:
The types present on a Team's own Pokémon; not move coverage.
_Avoid_: Offensive coverage

**Weakness**:
An attacking type that two or more Pokémon on a Team are weak to.
_Avoid_: Hole

**Threat score**:
A 0-100 heuristic: average Team BST divided by 6, capped at 100.
_Avoid_: Power rating

**Role distribution**:
The count of Attackers, Walls and Mixed Pokémon on a Team.
_Avoid_: Role split

**Archetype**:
A Team's style, one of Trick Room, Rain / Water Spam, Sun / Fire Core, VGC Restricted, Hyper Offense, Stall / Bulky or Balance.
_Avoid_: Playstyle, strategy

**Matchup**:
A comparison of two Teams (`/matchup`).
_Avoid_: Head-to-head

**Matchup score**:
A heuristic of summed type effectiveness plus a speed bonus; an advantage is a gap above 5.
_Avoid_: Win probability

### League operations

**Season**:
An integer written to the Setup Tab at League creation; not a separate record.
_Avoid_: League

**Week**:
A Schedule and Match filter.
_Avoid_: Round (that is a Draft term)

**Schedule**:
The list of Matches read from the Schedule Tab.
_Avoid_: Fixtures

**Transaction**:
A Transactions Tab row of free-text type (trade, drop, add, waiver); a pending Trade is also stored as one.
_Avoid_: Move

**Team page**:
The League sheet Tab generated for a registered Team.
_Avoid_: Roster page

**Team logo**:
A Discord CDN image URL set at Team registration.
_Avoid_: Avatar

**Match upload**:
Recording a Discord CDN video URL for a Match on the League sheet; no file is stored.
_Avoid_: Video upload

**Replay parse**:
The service that fetches a Showdown replay's JSON and saves winner, teams and turns to the League sheet; distinct from the ML replay parser.
_Avoid_: Replay parser (that is the ML one)

**Notification**:
A best-effort DM about a pick turn, pick warning, trade offer, trade accepted, match reminder, Draft completion or ELO update.
_Avoid_: Alert (that is a platform term), ping

**Help CSV**:
`discord_commands.csv`, the single source for `/help`.
_Avoid_: Command list

**Model pull**:
Downloading trained models from a GitHub Release and verifying their sha256 digest.
_Avoid_: Model update

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

### ML training

**Bot**:
The Discord application that runs the League; not a Battle agent. `ShowdownBotPlayer` is a code name only.
_Avoid_: Agent

**Showdown**:
The Pokémon Showdown site and simulator; the bare word means the site.
_Avoid_: PS, Smogon (that is the tier authority)

**Showdown mode**:
Where training connects: localhost, showdown (public server, two accounts) or browser (disabled).
_Avoid_: Server mode, mode

**Showdown account**:
A login a Battle agent uses on a Showdown server.
_Avoid_: Bot account

**Replay**:
A Showdown battle log or its URL.
_Avoid_: Game log

**Replay buffer**:
The circular store of self-play experience used to train the MCTS agent; not a Showdown Replay.
_Avoid_: Replay (bare)

**Observation**:
The float vector a Battle agent sees each turn (78 dimensions singles, 140 doubles).
_Avoid_: State, features

**Action space**:
The 26 discrete actions: 6 switches plus 4 moves each with no gimmick or one of four.
_Avoid_: Moves

**Gimmick**:
A mega, z-move, dynamax or terastallize modifier on a move.
_Avoid_: Mechanic

**Unmappable action**:
A replay action outside the Action space; a gap above 5% warns and above 15% aborts unless forced.
_Avoid_: Bad action

**Behavioral cloning**:
Pre-training an actor from `(observation, action)` pairs in replays to warm-start PPO (`bc_actor.pt`).
_Avoid_: Imitation, BC (in prose)

**Curriculum**:
The PPO schedule: a warmup phase against a max-base-power opponent, then self-play after a 70% win rate over 500 episodes.
_Avoid_: Epoch 0, stage

**Checkpoint**:
A saved model file: `latest`, `best_model`, `final_model`, or the transformer checkpoint.
_Avoid_: Snapshot, weights

**Team pool**:
The five Showdown-export Teams per Battle format that the Rotating teambuilder cycles through.
_Avoid_: Team list

**Rotating teambuilder**:
The component that gives each training episode the next Team from a Team pool.
_Avoid_: Team picker

**Vocabulary**:
The species-and-move to integer id map saved as `vocab.json`.
_Avoid_: Embedding table

**Training doctor**:
The preflight and auto-fix module that diagnoses training failures such as an offline Showdown server.
_Avoid_: Health check (that is a platform term)

**Training dashboard**:
The FastAPI page and API showing training status (stopped, running, error).
_Avoid_: Monitor

**Stub model**:
An untrained fallback model file under 160,000 bytes; packaging fails if every model is a stub.
_Avoid_: Empty model

**Model release**:
A GitHub Release tagged `ml-models-r<run>-a<attempt>` holding trained models.
_Avoid_: Model drop

**Train format / Spar format / Team format**:
The three keys per training target: the Battle format trained on, the one `/spar` offers, and the key into the Team pool.
_Avoid_: Format (bare)

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

### Platform data

**Natural key**:
A Source's stable id for a record, used for deduplication (Smogon uses format-cutoff-period).
_Avoid_: External id

**Payload hash**:
The SHA-256 of a Raw record's payload; unique per Source and Natural key.
_Avoid_: Checksum

**Canonical format**:
A normalized competitive format (slug, generation, singles or doubles, regulation).
_Avoid_: Format (bare)

**Period**:
The `YYYY-MM` month of a Smogon usage snapshot.
_Avoid_: Month

**Cutoff**:
The Smogon rating threshold a usage snapshot covers (default 1500).
_Avoid_: ELO, rating floor

**Usage snapshot**:
One Source's usage statistics for one Canonical format, Period and Cutoff.
_Avoid_: Usage report

**Usage entry**:
One species' rank, usage percentage and raw count inside a Usage snapshot.
_Avoid_: Usage row

**Moveset**:
The moves, items, spreads, abilities, teammates and checks recorded for a Usage entry.
_Avoid_: Build

**Tournament event**:
A tournament with a name, date, Canonical format and level (online, major or champions).
_Avoid_: Event (bare)

**Entrant**:
One tournament team's placing, player name and win-loss record (`tournament_team`).
_Avoid_: Team (that is a League Team)

**Decklist slot**:
One Pokémon in an Entrant's decklist, with item, ability, Tera type, moves, nature and spread.
_Avoid_: Team member

**Parser version**:
The version stamp on a parsed replay battle; bumping it makes a re-parse idempotent.
_Avoid_: Normalizer version

**Brought**:
A Pokémon actually taken into a battle.
_Avoid_: Selected

**Lead**:
A Pokémon active on the first turn.
_Avoid_: Starter

**Resolution method**:
How a source name was matched to a Canonical species: exact, form override, fuzzy or unresolved.
_Avoid_: Match type

### Platform operations

**Health check**:
The monitoring command (`python -m src.platform.monitoring`) that exits 1 when any Alert fires.
_Avoid_: Doctor (that is ML)

**Alert**:
A health-check finding: STALE_SYNC (no recent successful run), REPEATED_FAILURE (last 3 runs errored), VOLUME_DROP (landed under half the 30-day average) or PARSE_ERRORS (over 5 Dead letters in 24 hours).
_Avoid_: Notification (that is a DM)

**Production sync**:
The scheduled GitHub workflow (`sync-prod`) that runs Ingest on the self-hosted runner.
_Avoid_: Prod job

**Daily sync**:
The Production sync run for Limitless and replays.
_Avoid_: Nightly

**Monthly sync**:
The Production sync run for Smogon and Pikalytics.
_Avoid_: Usage sync

**Sync watchdog**:
The GitHub-hosted workflow that opens a `sync-stale` issue when Production sync has not succeeded for 3 days.
_Avoid_: Monitor

**Sync-failure issue**:
The single open GitHub issue labelled `sync-failure` that collects Production sync failures during an outage.
_Avoid_: Alert issue

**Deadline**:
The wall-clock budget (default 300 s) shared across all Sources in one sync.
_Avoid_: Timeout

**Rate limiter**:
The per-Source minimum interval between requests, burst of 1.
_Avoid_: Throttle (in prose)

**Retry class**:
Whether a fetch failure is transient, permanent or rate-limited, which decides retry (4 attempts, jittered backoff).
_Avoid_: Error type

**Seed**:
Loading Canonical species and Species aliases from `data/pokemon.json` and Showdown aliases.
_Avoid_: Bootstrap

**Preflight**:
`scripts/preflight.py`, a PASS/FAIL checklist for production readiness, including the 17 League sheet Tabs.
_Avoid_: Smoke test

### Discord

**Command sync**:
Registering the bot's slash commands with Discord, hash-gated to avoid rate limits.
_Avoid_: Sync (bare)
