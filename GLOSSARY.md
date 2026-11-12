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
