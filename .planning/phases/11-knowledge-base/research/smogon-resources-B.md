# Smogon + Tools Research — Group B

Extracted: 2026-03-24
Phase: 11 — Knowledge Base

---

## Table of Contents

1. [stalruth.dev — Stuart Rutherford's Competitive Tools](#1-stalruthdev)
2. [cut-explorer.stalruth.dev — VGC Top Cut Explorer](#2-cut-explorerstalruthdev)
3. [smogon.com — Main Site Overview](#3-smogoncom)
4. [smogon.com/dex — Strategy Pokedex](#4-smogoncomdex)
5. [smogon.com/articles/getting-started — Competitive Intro](#5-smogoncomarticlesgetting-started)
6. [Beginner's Guide to Pokemon Showdown (Forum)](#6-beginners-guide-to-pokemon-showdown)
7. [smogon.com/resources/beginner — Beginner Resource Hub](#7-smogoncomresourcesbeginner)
8. [Teambuilder Using PS Bases (Forum Thread)](#8-teambuilder-using-pokemon-showdown-bases)

---

## 1. stalruth.dev

**URL:** https://www.stalruth.dev

**Site Description:**
Personal tools site by Stuart Rutherford. Hosts several competitive Pokemon utilities built
primarily for the VGC (Video Game Championship) community.

### Tools Available

| Tool | Description | Tech |
|------|-------------|------|
| Sableye Bot | Discord bot for competitive info/discussion; ~2,700 servers since 2019 | Node.js, Discord Interactions API |
| Top Cut Explorer | Progressive Web App; examines competitive sets from Regional Championships | Svelte/SvelteKit |
| Pokemon Set Reverser | Calculates EV/IV distribution from species, form, nature, and stats | - |
| Pokemon Moveset Planner | Analyzes PS exports; shows move acquisition methods (outdated, no SV coverage) | - |
| Pokemon Tournament Resistance Calculator | Computes opponent win ratios; estimates single-elimination qualification likelihood | - |

### Key Data Points

- Sableye Bot provides rapid in-Discord access to competitive info — useful reference for
  bot design patterns
- Top Cut Explorer is regularly updated with tournament data and Core Web Vitals optimized
- Set Reverser is relevant for recreating/reverse-engineering competitive teams
- Moveset Planner lacks Scarlet/Violet coverage — gap to note in knowledge base

### Relevance to Knowledge Base

- Sableye Bot: reference architecture for a competitive info Discord bot
- Top Cut Explorer: source of actual tournament team data (VGC sets, regulations)
- Set Reverser: utility for team reconstruction workflows
- Tournament Resistance Calculator: tournament logistics tool, lower priority

---

## 2. cut-explorer.stalruth.dev

**URL:** https://cut-explorer.stalruth.dev

**Site Description:**
Progressive Web App for browsing top-placing teams from VGC Regional, Special, and
International Championships. Covers 2023-2026 seasons.

### Regulation Periods Covered

| Regulation | Date Range |
|------------|------------|
| Regulation H | September 1 – November 30, 2025 |
| Regulation F | December 1, 2025 – March 31, 2026 |
| (Earlier regs) | 2023–2025 seasons available |

### Tournament Categories

- **Regional Championships** — city-specific competitive events
- **Special Events** — limited competitive gatherings
- **International Championships** — continental-level competitions (NA, EU, SA, APAC)

### Key Data Extracted

- Tournament results browsable by season and regulation period
- Geographic coverage: North America, Europe, South America, Asia-Pacific
- Data shows actual sets used by top-cut players — real metagame usage evidence
- Useful for: identifying dominant Pokemon, items, moves per regulation cycle

### Format/Tier Relevance

- Exclusively VGC-focused (doubles format, official Nintendo/TPC rules)
- Regulation periods map to VGC format versions (Reg F = VGC2026regf, etc.)
- Complements Smogon singles tiers for the VGC/doubles side of the knowledge base

### Relevance to Knowledge Base

- Primary source for actual VGC team compositions at high-level play
- Can populate the knowledge base with: popular picks, item spreads, move choices
- Cross-reference with Smogon dex data for stat/ability context

---

## 3. smogon.com

**URL:** https://www.smogon.com

**Site Description:**
"A Pokemon website and community specializing in the art of competitive battling."
Central hub for competitive singles and doubles strategy.

### Main Sections

| Section | Description |
|---------|-------------|
| Strategy Pokedex | Per-Pokemon analysis and set recommendations |
| Flying Press Articles | Community strategy articles |
| In-Game Guides & Resources | Non-competitive guides |
| The Smog Archives | Historical community magazine |
| Game-specific guides | RBY, GSC, RSE, DPPt, BW, XY |
| Pokemon Showdown | Battle simulator |
| Damage Calculator | Damage range tool |
| Battling 101 | One-on-one tutoring program |
| Tournaments | Organized competitive play |
| Wi-Fi Trading & Battling | Community trade/battle forum |

### Community Platforms

- Smogon Forums (primary discussion)
- Discord server
- Create-A-Pokemon Project (CAP)
- Social: Facebook, Twitter, YouTube, Twitch

### Key Notes

- Homepage does not surface tier structures directly — tier data lives in deeper pages
- Battling 101 tutoring program is a notable community resource for beginners
- Damage Calculator is an essential competitive tool to reference

---

## 4. smogon.com/dex

**URL:** https://www.smogon.com/dex/

**Site Description:**
Smogon's Strategy Pokedex. Comprehensive per-Pokemon data covering stats, tiers, moves,
abilities, and competitive analysis across all generations.

### Data Available per Pokemon

- Base stats (HP, Atk, Def, SpA, SpD, Spe)
- Type classifications
- Abilities (including hidden abilities)
- Height and weight
- Evolution chains
- Dex numbers
- Format/tier eligibility flags
- Regional form variants (Alola, Galar, Hisui, Paldea)

### Competitive Tiers Documented

| Category | Tiers |
|----------|-------|
| Standard usage tiers | OU, UU, RU, NU, PU, ZU |
| Special tiers | LC (Little Cup), NFE (Not Fully Evolved) |
| Extreme tiers | AG (Anything Goes), Ubers |

### Generation Coverage

- Red/Blue (Gen 1) through Scarlet/Violet (Gen 9)
- "genfamily" field tracks cross-gen availability
- Non-standard Pokemon flagged with `isNonstandard` (CAP, etc.)

### Notable Gaps in Extracted Data

- Move pools and compatibility not surfaced in main dex view
- Item usage recommendations not visible at top level
- Ability mechanics explanations separate from dex entries
- Detailed strategy write-ups and set recommendations require per-Pokemon drill-down

### Relevance to Knowledge Base

- Primary structured data source for Pokemon stats, tiers, and eligibility
- API or scraping target for populating the knowledge base with canonical tier assignments
- Tier flags per Pokemon are the ground truth for format legality checks

---

## 5. smogon.com/articles/getting-started

**URL:** https://www.smogon.com/articles/getting-started

**Site Description:**
Competitive battling introduction article. Covers the fundamental concepts needed to
transition from casual to competitive play.

### Tier Structures

Usage-based tiers (Pokemon assigned by monthly usage statistics):

| Tier | Name | Description |
|------|------|-------------|
| OU | OverUsed | Top-usage tier; most common competitive format |
| UU | UnderUsed | Below OU usage threshold |
| RU | RarelyUsed | Below UU threshold |
| NU | NeverUsed | Below RU threshold |
| PU | PU | Below NU threshold |

Special / non-usage tiers:

| Tier | Description |
|------|-------------|
| Ubers | Banned from OU; separate "overcentralizing" tier |
| LC | Little Cup — level 5, first-stage only |
| DOU | Doubles OU |
| Monotype | Teams restricted to one shared type |
| OMs | Other Metagames — alternative formats |

Legacy formats: Each tier playable across generations (Gen 1-8+).

### Format Rules

- Healing items **prohibited** (no Full Restore, Revive, etc.)
- **Team Preview**: both players see full opponent team before battle starts
- Objective: eliminate all six opposing Pokemon
- Prediction and strategy replace item-based recovery
- Standard format: 6v6 singles (OU and most tiers)

### Core Mechanics

**EV System:**
- 252 EV points max per stat
- 510 total EVs per Pokemon
- Common spread: 252/252/4 for offensive; 252 HP/x/x for defensive

**IV System:**
- Range: 0-31 per stat
- Competitive standard: 31 (perfect) IVs in all stats
- 0 IVs used intentionally for Trick Room or Foul Play counterplay

**Natures:**
- Boost one stat by 10%, reduce another by 10%
- 25 natures total; 5 neutral (no change)
- Critical for fine-tuning stat benchmarks

### Five Team Archetypes

| Archetype | Description |
|-----------|-------------|
| Hyper Offense (HO) | Breaking down opponents with brute strength; minimal defensive investment |
| Bulky Offense | Offensive core supported by defensive pivots |
| Balance | Defensive backbone + strong wallbreakers; most common tournament archetype |
| Semi-Stall | Multiple walls supporting one bulky setup sweeper |
| Stall | Wins through residual damage; entry hazards, status, attrition |

### Four Core Pokemon Roles

| Role | Function |
|------|----------|
| Wallbreaker | High offensive stats; punches holes in opponent's defensive core |
| Setup Sweeper | Accumulates stat boosts in safe windows; requires support |
| Wall | High bulk + recovery; wears down attackers via passive damage or utility |
| Pivot | Generates momentum; U-turn/Volt Switch/Teleport to gain favorable matchups |

### Damage Categories

| Type | Examples |
|------|---------|
| Direct | Attack moves — primary wallbreaking method |
| Indirect | Entry hazards (Stealth Rock, Spikes), weather (Sand, Rain, Sun, Snow), status (Burn, Poison, Para), held items (Rocky Helmet, Iron Barbs) |

### Key Battle Concepts

1. **Team Preview strategy** — identify threats and wincons before choosing lead
2. **Prediction** — anticipating opponent switches; risk vs. reward per turn
3. **Momentum** — controlling which side is forced to react
4. **Short vs. long game** — immediate threats vs. win conditions over time

### Resources Listed

- Smogon Pokedex: optimal sets + analysis per Pokemon
- Viability Rankings: tier-specific rankings within each format
- Sample Teams: battle-tested team templates
- Rate My Team (RMT): community team feedback
- Battling 101: certified tutor matching
- Tournaments: competitive ladder and organized events
- Discord: real-time community support

---

## 6. Beginner's Guide to Pokemon Showdown

**URL:** https://www.smogon.com/forums/threads/the-beginners-guide-to-pok%C3%A9mon-showdown.3676132/

**Site Description:**
Comprehensive forum guide to using Pokemon Showdown (PS). Covers UI, commands, teambuilder,
and battling workflow from first login through competitive play.

### Pokemon Showdown Background

- Web-based battle simulator
- Created: October 2011
- Adopted as Smogon's official platform: July 2012
- Works in all major browsers; no installation required
- Replaces Wi-Fi battles with stable, accessible competitive play

### Teambuilder Workflow

Steps for building a team in PS:

1. Open Teambuilder from main menu
2. Select format/generation
3. Add Pokemon one by one (or import via paste)
4. Per Pokemon, configure:
   - Species and form
   - Item
   - Ability
   - Moves (4 moves)
   - Level (1-100; competitive standard is 50 for VGC, 100 for Smogon)
   - Gender
   - Happiness
   - Shiny toggle
5. Validate team against format rules (PS flags illegal sets automatically)
6. Save and name the team

### Battling Workflow

1. Select format from ladder or direct challenge
2. Team Preview phase: view opponent's 6 Pokemon, choose your lead
3. Battle turn loop:
   - Choose move or switch
   - Mega Evolve / Dynamax / Terastallize via checkbox below moves
   - Timer available to prevent stalling
4. Win condition: faint all 6 opponent Pokemon

### Battle Format Options

- **Ladder**: random matchmaking vs. opponents at similar rating
- **Direct challenge**: challenge a specific user by username
- **Random Battle**: PS generates teams automatically (no teambuilder needed)
- **Tournaments**: bracket-style organized events

### Room Types

| Type | Description |
|------|-------------|
| Lobby | Default public room |
| Help | Support channel |
| Tournaments | Organized bracket events |
| Public rooms | Topic-specific communities |
| Private rooms | Invite-only niche groups |

### Staff Rank System

| Symbol | Rank |
|--------|------|
| ^ | Driver |
| % | Moderator |
| + | Voice |
| @ | Room Owner |
| * | Global Staff |
| # | Administrator |
| ~ | Head Administrator |

Voice users (+) can broadcast commands. Global promotion requires Administrator (~) action.

### Commands Categories

- **Informational**: lookup commands (/data, /dex, /analysis)
- **Settings/Preferences**: account and display settings
- **Battle-related**: timer, forfeit, replay controls
- **Rooms/Chat**: join, leave, create rooms
- **Highlights**: keyword notification triggers

### Resources Mentioned in Thread

- Damage calculators
- Smogon analyses by generation
- Rate My Team subforum
- Trainer Academy room for skill development

---

## 7. smogon.com/resources/beginner

**URL:** https://www.smogon.com/resources/beginner

**Site Description:**
Curated beginner resource hub. Aggregates the most important introductory guides,
community tools, and learning pathways for new competitive players.

### Full Tier List Referenced

| Tier | Full Name |
|------|-----------|
| Ubers | Ubers |
| OU | OverUsed |
| UU | UnderUsed |
| RU | RarelyUsed |
| NU | NeverUsed |
| PU | PU |
| LC | Little Cup |
| DOU | Doubles OverUsed |
| Monotype | Monotype |

### Beginner Guides Listed

| Guide Title | Topic |
|-------------|-------|
| Introduction to Smogon Metagames | Tier system overview, format explanations |
| Tiering FAQ | How Pokemon move between tiers, tiering process |
| A Beginner's Guide to Understanding EVs | EV mechanics, spreads, optimization |
| Synergies and Cores — The Fundamentals of Teambuilding | Team construction, type/role synergy |
| A Guide to Common Battle Conditions | Weather, terrain, entry hazards, status |
| The Pokemon Dictionary | Competitive terminology glossary |
| Risk/Reward | Decision-making framework for battle turns |
| PKMN 101 | General competitive intro |
| How to Use Pokemon Showdown | PS UI and workflow guide |

### Community Resources

| Resource | Description |
|----------|-------------|
| Pokemon Showdown | Online battle simulator for practice |
| Forums | Metagame subforums, RMT, beginner battles, tier discussion |
| Discord | Main server + specialized side servers |
| StrategyDex | Per-Pokemon analysis and recommended sets |
| Damage Calculator | Matchup analysis tool |

### Key Teambuilding Principle Highlighted

Synergies and team cohesion are the foundational concepts — not individual Pokemon power.
Team construction starts with identifying type coverage gaps, role balance, and
defensive/offensive cores that support each other.

### Community Scale

"Hundreds of thousands" of members. Community philosophy: learning through experience
alongside structured resource access.

---

## 8. Teambuilder Using Pokemon Showdown Bases

**URL:** https://www.smogon.com/forums/threads/teambuilder-using-pokemon-showdown-bases.3774080/

**Site Description:**
Forum thread about extracting and reusing the Pokemon Showdown teambuilder as a
standalone component for custom software projects.

### Actual Thread Content

This thread is **software development focused**, not competitive strategy. Key discussion:

- Original poster: wants to extract PS teambuilder component from the main codebase
- Goal: convert embedded data (Pokemon, abilities, items) into user-configurable files
- Secondary goal: manage image assets for custom creations

### Technical Recommendation Given

The `@pkmn/ps` npm wrapper package was recommended:
- GitHub: provides wrappers around PS data modules
- "contains some wrapper aiming to do what you want about the data part"
- Provides structured access to PS data without requiring full PS infrastructure

### Key Insight from Thread

Building a custom teambuilder from scratch may be more efficient than stripping PS down,
because competitive teambuilding does not require all PS backend features:
- Type charts not needed
- Full battle logic not needed
- Core requirement: Pokemon data + move data + format legality validation

### Relevance to Knowledge Base

- `@pkmn/ps` package is a relevant dependency for programmatic access to PS data
- The thread confirms PS data is modular and extractable
- For the knowledge base: PS data layer (`@pkmn/data`, `@pkmn/dex`) can serve as the
  canonical data source for Pokemon stats, moves, abilities, and items

---

## Summary: Key Findings for Knowledge Base

### Tier Structure (Canonical Order)

```
Ubers > OU > UU > RU > NU > PU > ZU > LC
Special: DOU, Monotype, AG, OMs
```

Tiers are assigned by **monthly usage statistics** — not permanent. Pokemon move up/down
based on actual ladder usage percentages.

### Format Rules (Smogon Singles Standard)

- 6v6 singles
- No held healing items (no Full Restore / Revive)
- Team Preview (both teams visible before battle)
- Level 100, perfect IVs, EV optimization expected
- Gen 9 SV is the current generation standard (Scarlet/Violet)

### VGC / Doubles Rules (from Top Cut Explorer context)

- Regulation periods define legal Pokemon pools
- Current: Regulation F (Dec 2025 – Mar 2026) = VGC2026regf
- VGC uses best-of-3, level 50, 4 Pokemon selected from 6 (Bring 6 Pick 4)
- Team Preview required; Item Clause (no duplicate held items)

### Teambuilding Core Principles

1. Build around a **win condition** (sweeper, wallbreaker, weather setter)
2. Identify **defensive and offensive cores** (2-3 Pokemon that cover each other's weaknesses)
3. Cover **common threats** in the metagame (check the Viability Rankings)
4. Balance **roles**: at minimum, address wallbreaking, sweeping, and pivoting
5. Test via **ladder** and iterate with RMT feedback

### Essential Competitive Mechanics

| Mechanic | Key Facts |
|----------|-----------|
| EVs | 252 max per stat; 510 total; fine-tunes benchmark damage/speed thresholds |
| IVs | 0-31; competitive standard 31 in all; 0 SpA on physical, 0 Spe for Trick Room |
| Natures | 10% boost/nerf; 25 total (5 neutral); critical for speed tiers |
| Entry Hazards | Stealth Rock (most common), Spikes, Toxic Spikes, Sticky Web |
| Status Conditions | Burn (halves Atk), Paralysis (halves Spe), Poison/Toxic (residual), Sleep, Freeze |
| Weather | Rain (Water x1.5), Sun (Fire x1.5), Sand (SpD boost Rock), Snow (Def boost Ice) |
| Terrain | Electric, Grassy, Misty, Psychic — priority move and type interactions |

### Tools for Knowledge Base Population

| Tool | Use Case |
|------|----------|
| Smogon Dex API | Pokemon stats, tier assignments, move pools, abilities |
| Top Cut Explorer | Real tournament VGC team compositions |
| `@pkmn/ps` / `@pkmn/dex` | Programmatic PS data access |
| Damage Calculator | Set validation and matchup analysis |
| Sableye Bot (reference) | Discord bot architecture for competitive info delivery |

### Beginner Learning Path (from Smogon resources)

1. Read "Introduction to Smogon Metagames" — understand tier system
2. Read "A Beginner's Guide to Understanding EVs" — stat customization
3. Read "Synergies and Cores" — teambuilding fundamentals
4. Read "A Guide to Common Battle Conditions" — hazards, weather, status
5. Learn "The Pokemon Dictionary" — competitive terminology
6. Study "Risk/Reward" — decision-making framework
7. Practice on PS ladder with sample teams
8. Submit team to RMT for feedback
9. Enroll in Battling 101 for personalized coaching

---

*Research compiled from Group B URLs. See smogon-resources-A.md for Group A sources.*
