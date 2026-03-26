# Pokemon Draft League API Documentation

FastAPI backend serving the React dashboard with real-time draft updates via WebSocket.

**Base URL (local):** `http://localhost:8000`

**Auto-generated docs:** `/docs` (Swagger UI) or `/redoc` (ReDoc)

---

## Authentication

Currently **no authentication** required (designed for private Discord servers). Add API keys or OAuth if exposing publicly.

---

## Endpoints

### Health Check

**GET** `/health`

Returns API status and Pokemon database load count.

**Response:**

```json
{
  "status": "ok",
  "pokemon_loaded": 1025
}
```

---

## Pokemon

### List Pokemon

**GET** `/api/pokemon`

Query parameters:

- `tier` (optional) — Filter by Smogon tier (e.g., `OU`, `UU`, `Uber`)
- `gen` (optional) — Filter by generation (1-9)
- `q` (optional) — Fuzzy search by name

Returns up to 100 results.

**Examples:**

```bash
# All Pokemon (first 100)
curl http://localhost:8000/api/pokemon

# Search by name
curl http://localhost:8000/api/pokemon?q=charizard

# Filter by tier
curl http://localhost:8000/api/pokemon?tier=OU

# Filter by generation
curl http://localhost:8000/api/pokemon?gen=9
```

**Response:**

```json
[
  {
    "name": "Charizard",
    "dex_number": 6,
    "types": ["fire", "flying"],
    "tier": "UU",
    "generation": 1,
    "sprite_url": "https://play.pokemonshowdown.com/sprites/ani/charizard.gif",
    "console_legal": {
      "sv": true,
      "swsh": true,
      "bdsp": false,
      "legends": false
    },
    "vgc_legal": false,
    "vgc_season": null
  }
]
```

---

### Get Pokemon by Name

**GET** `/api/pokemon/{name}`

**Example:**

```bash
curl http://localhost:8000/api/pokemon/garchomp
```

**Response:** Same schema as list endpoint, single object.

**Error (404):**

```json
{
  "detail": "Pokemon 'notreal' not found"
}
```

---

## Drafts

### Get Active Draft

**GET** `/api/drafts/{guild_id}`

**Example:**

```bash
curl http://localhost:8000/api/drafts/123456789012345678
```

**Response:**

```json
{
  "guild_id": "123456789012345678",
  "league_name": "My Pokemon League",
  "draft_format": "snake",
  "game_mode": "showdown",
  "current_round": 3,
  "current_pick": 15,
  "active_player_id": "987654321098765432",
  "active_player_name": "Alice",
  "timer_expires_at": "2026-02-16T20:30:00Z",
  "picks": [
    {
      "round": 1,
      "pick": 1,
      "player_id": "987654321098765432",
      "player_name": "Alice",
      "pokemon_name": "Garchomp",
      "tera_type": "Fire",
      "is_tera_captain": true,
      "tier": "OU"
    }
  ],
  "status": "active"
}
```

**Error (404):**

```json
{
  "detail": "No active draft"
}
```

---

### Make a Pick

**POST** `/api/drafts/{guild_id}/pick`

**Request Body:**

```json
{
  "player_id": "987654321098765432",
  "pokemon_name": "Garchomp"
}
```

**Response:**

```json
{
  "success": true,
  "next_player": "Bob"
}
```

**Error (400):**

```json
{
  "detail": "Pokemon already picked"
}
```

**Side effect:** Broadcasts `{"event": "pick", "pokemon": "Garchomp", "player": "987..."}` to all WebSocket clients.

---

## Teams

### Get Team Roster

**GET** `/api/teams/{guild_id}/{player_id}`

**Example:**

```bash
curl http://localhost:8000/api/teams/123456789012345678/987654321098765432
```

**Response:**

```json
{
  "guild_id": "123456789012345678",
  "player_id": "987654321098765432",
  "display_name": "Alice",
  "team_name": "Fire Strikers",
  "pool": "Pool A",
  "logo_url": "https://cdn.discordapp.com/attachments/.../logo.png",
  "roster": [
    {
      "name": "Garchomp",
      "types": ["dragon", "ground"],
      "tier": "OU",
      "tera_type": "Fire",
      "is_tera_captain": true
    },
    {
      "name": "Corviknight",
      "types": ["flying", "steel"],
      "tier": "OU",
      "tera_type": null,
      "is_tera_captain": false
    }
  ]
}
```

---

### Get Team Analysis

**GET** `/api/teams/{guild_id}/{player_id}/analysis`

Returns type coverage, weaknesses, archetypes, and threat score.

**Example:**

```bash
curl http://localhost:8000/api/teams/123456789012345678/987654321098765432/analysis
```

**Response:**

```json
{
  "coverage": {
    "fire": 3,
    "water": 2,
    "grass": 1,
    "electric": 2,
    "ice": 1,
    "fighting": 2,
    "poison": 0,
    "ground": 3,
    "flying": 2,
    "psychic": 1,
    "bug": 1,
    "rock": 2,
    "ghost": 1,
    "dragon": 2,
    "dark": 1,
    "steel": 2,
    "fairy": 1
  },
  "weaknesses": {
    "fire": 1,
    "ice": 2,
    "rock": 1,
    "fighting": 0
  },
  "speed_tiers": {
    "fast": 2,
    "medium": 3,
    "slow": 1
  },
  "archetype": "Hyper Offense",
  "threat_score": 8.5,
  "role_distribution": {
    "attacker": 3,
    "wall": 1,
    "support": 1,
    "mixed": 1
  }
}
```

---

## Standings

### Get League Standings

**GET** `/api/leagues/{guild_id}/standings`

**Example:**

```bash
curl http://localhost:8000/api/leagues/123456789012345678/standings
```

**Response:**

```json
[
  {
    "player_id": "987654321098765432",
    "display_name": "Alice",
    "elo": 1150,
    "wins": 5,
    "losses": 2,
    "win_rate": 71.4
  },
  {
    "player_id": "111222333444555666",
    "display_name": "Bob",
    "elo": 1050,
    "wins": 3,
    "losses": 4,
    "win_rate": 42.9
  }
]
```

---

## Matchups

### Compare Two Teams

**GET** `/api/matchups/{guild_id}/{p1_id}/{p2_id}`

**Example:**

```bash
curl http://localhost:8000/api/matchups/123456789012345678/987654321098765432/111222333444555666
```

**Response:**

```json
{
  "advantage": "Player 1 has a slight advantage (55-45)",
  "p1_threats": [
    "Garchomp threatens 3 opposing Pokemon",
    "Heatran threatens 2 opposing Pokemon"
  ],
  "p2_threats": [
    "Dragapult threatens 2 opposing Pokemon"
  ],
  "type_summary": {
    "p1_super_effective_count": 12,
    "p2_super_effective_count": 8
  },
  "p1_score": 55,
  "p2_score": 45
}
```

---

## WebSocket

### Live Draft Board

**WS** `/ws/{guild_id}`

Connect to receive real-time draft updates.

**Example (JavaScript):**

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/123456789012345678');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Draft event:', data);
  // { event: "pick", pokemon: "Garchomp", player: "987..." }
};

// Keep-alive ping every 30s
setInterval(() => {
  ws.send('ping');
}, 30000);
```

**Events broadcast:**

- `{"event": "pick", "pokemon": "<name>", "player": "<id>"}` — A pick was made
- `{"event": "ban", "pokemon": "<name>"}` — A Pokemon was banned
- `{"event": "round_change", "round": <number>}` — Round incremented

---

## Error Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (invalid pick, Pokemon already taken, etc.) |
| 404 | Resource not found (draft, team, player, Pokemon) |
| 422 | Validation error (malformed JSON) |
| 500 | Internal server error |

---

## Rate Limiting

No rate limiting currently implemented. Add with `slowapi` if exposing publicly.

---

## CORS

Configured via `CORS_ORIGINS` in `.env`. Default allows:

- `http://localhost:5173` (Vite dev server)
- Your production frontend URL

---

## Development

Start the API server:

```bash
uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
```

Interactive API docs:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
