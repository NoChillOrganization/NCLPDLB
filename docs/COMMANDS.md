# Discord Bot Commands Reference

Complete reference for all slash commands with examples, parameters, and edge cases.

---

## Draft Setup

### `/draft-setup`

**Permission:** Manage Server

Interactive 3-step wizard to configure a new draft.

**Steps:**

1. **League Info** — Name, format (Snake/Auction/Tiered), game mode (Showdown/SV/SwSh)
2. **Player Config** — Player count (4-20), pools (None/A+B), snake reversal
3. **Tera Rules** — Max tera captains per team, tera type assignment

**Example flow:**

```text
User: /draft-setup
Bot: [Shows Step 1 modal]
User: Fills in "Spring 2026 League", "Snake", "Showdown"
Bot: [Shows Step 2 modal]
User: Sets 12 players, 2 pools, snake reversal ON
Bot: [Shows Step 3 modal]
User: Sets 1 tera captain max
Bot: ✅ Draft created! Players can now /draft-join
```

**Notes:**

- Creates draft in Setup tab of Google Sheets
- Overwrites any existing draft for this guild
- Players must `/draft-join` before `/draft-start`

---

### `/draft-create`

**Permission:** Manage Server

Quick-create draft with inline parameters (alternative to wizard).

**Parameters:**

- `league_name` (required) — League display name
- `format` (required) — `snake`, `auction`, `tiered`, or `custom`
- `game_mode` (required) — `showdown`, `sv`, `swsh`, `bdsp`, `legends`
- `player_count` (required) — 4-20
- `pools` (optional) — `none`, `a_b`
- `snake_reversal` (optional) — `true` or `false` (default: true)
- `max_tera_captains` (optional) — 0-3 (default: 1)

**Example:**

```text
/draft-create league_name:"Gen 9 OU Draft" format:snake game_mode:showdown player_count:8
```

**Notes:**

- Faster than `/draft-setup` if you know all settings upfront
- Same validation rules as wizard

---

### `/draft-join`

**Permission:** Anyone

Join an active draft and set your team info.

**Parameters:**

- `team_name` (required) — Your team name (e.g., "Fire Strikers")
- `pool` (optional) — `a` or `b` (required if draft uses pools)
- `logo` (optional) — Upload PNG/JPG team logo

**Example:**

```text
/draft-join team_name:"Thunder Bolts" pool:a
[Attach logo.png]
```

**Response:**

```text
✅ Joined draft as "Thunder Bolts" (Pool A)
Pick order: 3
```

**Edge cases:**

- If draft is full → "Draft is full (12/12 players)"
- If already joined → "You are already in this draft"
- If logo > 8MB → "Logo must be under 8MB"

---

### `/draft-start`

**Permission:** Commissioner (first person to `/draft-setup`)

Start the draft once all players have joined.

**Example:**

```text
/draft-start
```

**Response:**

```text
🎉 Draft started!
Round 1, Pick 1: @Alice — you're up! (⏰ 2 minutes)
```

**Edge cases:**

- If player count doesn't match setup → "Waiting for X more players"
- If draft already started → "Draft is already in progress"

**Notes:**

- Posts a pick prompt in the draft channel
- Starts a 2-minute timer (configurable)
- Players notified via DM

---

## Picking

### `/pick`

Pick a Pokemon during your turn.

**Parameters:**

- `pokemon` (required) — Pokemon name (autocomplete enabled)
- `tera_type` (optional) — Tera type override (default: primary type)
- `is_tera_captain` (optional) — Mark as tera captain (default: false)

**Example:**

```text
/pick pokemon:Garchomp tera_type:Fire is_tera_captain:true
```

**Response:**

```text
✅ Picked Garchomp (Tera: Fire, Captain)
Next: @Bob (⏰ 2 minutes)
```

**Edge cases:**

- Not your turn → "It's @Alice's turn"
- Pokemon already picked → "Garchomp was already picked by @Alice"
- Tera captain limit exceeded → "You already have 1 tera captain"
- Invalid Pokemon → "Pokemon 'Fakemon' not found"

**Notes:**

- Autocomplete shows filtered list based on tier/gen
- Tera type defaults to primary type if not specified
- Updates Google Sheets Draft tab

---

### `/ban`

Ban a Pokemon during the ban phase (if enabled).

**Parameters:**

- `pokemon` (required) — Pokemon to ban

**Example:**

```text
/ban pokemon:Zacian
```

**Response:**

```text
🚫 Zacian has been banned
Banned Pokemon: Zacian, Kyogre, Calyrex-Shadow
```

**Edge cases:**

- Not in ban phase → "Draft is not in ban phase"
- Pokemon already banned → "Zacian is already banned"
- Ban limit reached → "Ban phase is over (3/3 bans used)"

---

### `/bid`

Place a bid during auction drafts.

**Parameters:**

- `amount` (required) — Bid amount (integer)

**Example:**

```text
/bid amount:250
```

**Response:**

```text
💰 @Alice bids 250 for Garchomp
Current high bid: 250 (⏰ 30 seconds)
```

**Edge cases:**

- Not auction format → "This is not an auction draft"
- Bid too low → "Minimum bid is 260 (current: 250)"
- Insufficient budget → "You only have 200 left (bid: 250)"

---

## Team Management

### `/team`

View yours or another player's team.

**Parameters:**

- `user` (optional) — @mention or user ID (default: yourself)

**Example:**

```text
/team user:@Alice
```

**Response:**

```text
🔥 Fire Strikers — Alice (Pool A)

1. Garchomp (Dragon/Ground) — OU ⚡ Tera Captain: Fire
2. Corviknight (Flying/Steel) — OU
3. Toxapex (Poison/Water) — OU
4. Heatran (Fire/Steel) — OU
5. Dragapult (Dragon/Ghost) — OU
6. Ferrothorn (Grass/Steel) — OU

[Full Analysis] [Export to Showdown]
```

**Notes:**

- Shows team logo if uploaded
- Interactive buttons for full analysis + Showdown export
- Shows tera types and captains

---

### `/team-register`

Update your team name, pool, or logo after drafting.

**Parameters:**

- `team_name` (required) — New team name
- `pool` (optional) — `a` or `b`
- `logo` (optional) — New logo upload

**Example:**

```text
/team-register team_name:"Ice Warriors" pool:b
[Attach new_logo.png]
```

**Response:**

```text
✅ Team updated!
Name: Ice Warriors
Pool: B
Logo: Uploaded
```

---

### `/teamimport`

Import a Pokemon Showdown team export.

**Modal input:** Paste Showdown format team.

**Example:**

```text
User: /teamimport
Bot: [Opens modal]
User: Pastes:
  Garchomp @ Choice Scarf
  Ability: Rough Skin
  EVs: 252 Atk / 4 SpD / 252 Spe
  Jolly Nature
  - Earthquake
  - Scale Shot
  ...
Bot: ✅ Imported 6 Pokemon
```

**Edge cases:**

- Malformed text → "Could not parse team"
- Pokemon not in draft → "Garchomp is not on your roster"
- Duplicate Pokemon → "Garchomp appears twice"

---

### `/teamexport`

Export your team to Showdown format.

**Example:**

```text
/teamexport
```

**Response:**

```text
Garchomp @ Choice Scarf
Ability: Rough Skin
Tera Type: Fire
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Earthquake
- Scale Shot

Corviknight @ Leftovers
...

[Copy to clipboard]
```

---

### `/trade`

Propose a trade with another player.

**Parameters:**

- `user` (required) — @mention recipient
- `offer` (required) — Pokemon you're offering
- `want` (required) — Pokemon you want

**Example:**

```text
/trade user:@Bob offer:Garchomp want:Dragapult
```

**Response:**

```text
📤 Trade proposed to @Bob
Offering: Garchomp
Requesting: Dragapult
Trade ID: 7a3f9c

@Bob can /trade-accept 7a3f9c or /trade-decline 7a3f9c
```

**Notes:**

- Both Pokemon must be on respective rosters
- Trade ID is 6-character hex
- Logs to Transactions tab

---

### `/trade-accept` / `/trade-decline`

Accept or decline a pending trade.

**Parameters:**

- `trade_id` (required) — Trade ID from proposal

**Example:**

```text
/trade-accept trade_id:7a3f9c
```

**Response:**

```text
✅ Trade completed!
@Alice receives Dragapult
@Bob receives Garchomp
```

---

### `/legality`

Check if a Pokemon is legal in a console game format.

**Parameters:**

- `pokemon` (required) — Pokemon name
- `game` (required) — `sv`, `swsh`, `bdsp`, `legends`, or `vgc`

**Example:**

```text
/legality pokemon:Mewtwo game:sv
```

**Response (legal):**

```text
✅ Mewtwo is available in Scarlet/Violet
```

**Response (illegal):**

```text
❌ Mewtwo is NOT available in Scarlet/Violet
Available in: Legends Arceus, Brilliant Diamond/Shining Pearl
```

---

## Stats & Analysis

### `/analysis`

Full team analysis with coverage, weaknesses, archetypes.

**Parameters:**

- `user` (optional) — @mention or user ID (default: yourself)

**Example:**

```text
/analysis user:@Alice
```

**Response:**

```text
📊 Team Analysis — Fire Strikers

Type Coverage:
▰▰▰▰▰▰▰▰░░ Fire (8/10)
▰▰▰▰▰▰▰░░░ Ground (7/10)
▰▰▰▰▰▰░░░░ Water (6/10)
...

Weaknesses:
⚠️ 2x weak to Ice (Garchomp, Dragonite)
⚠️ 2x weak to Rock (Corviknight)

Speed Tiers:
Fast (>100): Garchomp, Dragapult
Medium (50-100): Heatran, Corviknight
Slow (<50): Toxapex, Ferrothorn

Archetype: Hyper Offense
Threat Score: 8.5/10

Role Distribution:
Attacker: 3 | Wall: 2 | Support: 1
```

---

### `/matchup`

Compare two teams head-to-head.

**Parameters:**

- `user1` (required) — First player
- `user2` (required) — Second player

**Example:**

```text
/matchup user1:@Alice user2:@Bob
```

**Response:**

```text
⚔️ Matchup — Fire Strikers vs Thunder Bolts

Advantage: Fire Strikers (55-45)

Fire Strikers Threats:
• Garchomp threatens 3 opposing Pokemon
• Heatran threatens 2 opposing Pokemon

Thunder Bolts Threats:
• Dragapult threatens 2 opposing Pokemon

Type Advantage:
Fire Strikers: 12 super-effective matchups
Thunder Bolts: 8 super-effective matchups
```

---

### `/standings`

View league standings with ELO and W/L records.

**Parameters:**

- `pool` (optional) — `a`, `b`, or `all` (default: all)

**Example:**

```text
/standings pool:a
```

**Response:**

```text
📈 Standings — Pool A

1. Alice (Fire Strikers) — 1150 ELO | 5-2 (71.4%)
2. Bob (Thunder Bolts) — 1050 ELO | 3-4 (42.9%)
3. Charlie (Water Warriors) — 1000 ELO | 2-2 (50.0%)
```

---

### `/replay`

Submit a Pokemon Showdown replay link.

**Parameters:**

- `url` (required) — Full replay URL

**Example:**

```text
/replay url:https://replay.pokemonshowdown.com/gen9ou-123456
```

**Response:**

```text
✅ Replay recorded
Winner: @Alice
Turns: 24
Alice's team: Garchomp, Corviknight, Toxapex
Bob's team: Dragapult, Ferrothorn, Heatran
```

**Notes:**

- Auto-parses JSON from URL
- Updates Match Stats tab
- Can link to match results

---

### `/match-upload`

Upload a battle video (capture card footage).

**Parameters:**

- `opponent` (required) — @mention opponent
- `file` (required) — MP4/MOV/AVI (max 100MB)

**Example:**

```text
/match-upload opponent:@Bob
[Attach battle.mp4]
```

**Response:**

```text
⏳ Uploading video... (24.5 MB)
✅ Video uploaded!
URL: https://storage.example.com/matches/7a3f9c.mp4
Thumbnail: https://storage.example.com/matches/7a3f9c.jpg
```

**Notes:**

- Generates thumbnail with ffmpeg
- Uploads to Azure Blob or Cloudflare R2
- Saves metadata to Match Stats tab

---

## League

### `/league-create`

Create a new league (separate from drafts).

**Parameters:**

- `name` (required) — League name

**Example:**

```text
/league-create name:"Spring 2026 Competitive"
```

**Response:**

```text
✅ League "Spring 2026 Competitive" created
Default ELO: 1000
K-Factor: 32
```

---

### `/schedule`

View this week's suggested matchups.

**Example:**

```text
/schedule
```

**Response:**

```text
📅 Week 3 Schedule

Mon: @Alice vs @Bob
Wed: @Charlie vs @Dave
Fri: @Eve vs @Frank
```

---

### `/result`

Report a match result (updates ELO).

**Parameters:**

- `opponent` (required) — @mention opponent
- `winner` (required) — @mention winner

**Example:**

```text
/result opponent:@Bob winner:@Alice
```

**Response:**

```text
✅ Match recorded
Alice: 1000 → 1016 (+16)
Bob: 1000 → 984 (-16)
```

**Notes:**

- Both players notified via DM
- Logged to Match Stats tab
- Updates Standings tab

---

## Admin

### `/admin-skip`

Force-skip a player's turn.

**Permission:** Manage Server

**Parameters:**

- `player` (optional) — @mention player (default: current active player)

**Example:**

```text
/admin-skip player:@Alice
```

**Response:**

```text
⏭️ Skipped @Alice's turn
Next: @Bob (⏰ 2 minutes)
```

---

### `/admin-pause` / `/admin-resume`

Pause or resume the draft timer.

**Example:**

```text
/admin-pause
```

**Response:**

```text
⏸️ Draft paused
Timer stopped at 1:34 remaining
```

---

### `/admin-override-pick`

Force a pick for a player (commissioner override).

**Parameters:**

- `player` (required) — @mention player
- `pokemon` (required) — Pokemon to pick

**Example:**

```text
/admin-override-pick player:@Alice pokemon:Garchomp
```

**Response:**

```text
⚠️ Commissioner override
Picked Garchomp for @Alice
Next: @Bob
```

---

### `/admin-reset`

Reset the entire draft (with confirmation).

**Example:**

```text
/admin-reset
```

**Response:**

```text
⚠️ This will delete all picks and reset the draft.
Are you sure?
[Confirm] [Cancel]
```

---

## Machine Learning

### `/spar`

Battle a trained PPO agent live on Pokemon Showdown.

**Parameters:**

- `format` (required) — Battle format (autocomplete)
- `username` (optional) — Your Showdown username (default: Discord username)

**Supported formats:**

- `gen9randombattle`, `gen9ou`, `gen9doublesou`, `gen9nationaldex`, `gen9monotype`, `gen9anythinggoes`
- `gen9vgc2026regi`, `gen9vgc2026regf`
- `gen7randombattle`, `gen6randombattle`

**Example:**

```text
/spar format:gen9ou username:MyShowdownName
```

**Response:**

```text
🤖 Challenge sent on Pokemon Showdown!
Format: Gen 9 OU
Username: MyShowdownName

Accept the challenge on play.pokemonshowdown.com
The bot is using a PPO agent trained on 500,000 steps.
```

**Notes:**

- Requires trained model at `data/ml/policy/<format>/final_model.zip`
- Bot creates Showdown account and sends challenge
- You must accept on the Showdown website

**Edge cases:**

- Model not trained → "No trained model found for gen9ou. Train it first with: python -m src.ml.train_policy --format gen9ou"
- Showdown server down → "Could not connect to Pokemon Showdown"

---

## Permissions Summary

| Command | Required Permission |
|---------|---------------------|
| Draft setup (`/draft-setup`, `/draft-create`, `/draft-start`) | Manage Server |
| Admin commands (`/admin-*`) | Manage Server |
| All other commands | None (anyone can use) |

**Note:** Commissioner role is automatically assigned to the first person who runs `/draft-setup`.
