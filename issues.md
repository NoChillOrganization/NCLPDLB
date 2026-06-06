---
title: Issue Tracker
updated: 2026-06-05
closed: 2026-06-03
open: 77
in-progress: 0
---

# Issue Tracker — NCLPDLB

> Source of truth for open work. Individual notes in `issues/`. Add new issues by creating `issues/ISS-NNN-slug.md` with the same frontmatter schema, then add a row here.

---

## Open

| ID                                              | Title                                          | Phase   | Priority | Labels        | Status      |
| ----------------------------------------------- | ---------------------------------------------- | ------- | -------- | ------------- | ----------- |

---

## Audit Findings — Code Review 2026-06-05

> Static audit of `src/`, `data_pipeline.py`, `setup.py`, `scripts/`. 16 HIGH, 34 MEDIUM, 28 LOW. Notes in `Issues/`. See `f-nclpdlb-role-you-are-an-compiled-cocoa` report for resolutions.

| ID                                                                        | Title                                                       | Location                                                       | Priority | Status |
| ------------------------------------------------------------------------- | ----------------------------------------------------------- | -------------------------------------------------------------- | -------- | ------ |
| [[H1 `accept_trade` reads…\|H1]]                                          | accept_trade reads…                                         | `services/team_service.py:181-206`                             | high     | open   |
| [[H2 Roster JSON contract mismatch\|H2]]                                  | Roster JSON contract mismatch                               | `data/sheets.py:527-536 ↔ services/team_service.py:71-83`      | high     | open   |
| [[H3 `upsert_row` matches header by name but writes the caller's…\|H3]]   | upsert_row matches header by name but writes the caller's…  | `data/sheets.py:166-178`                                       | high     | open   |
| [[H4 `get_tab` auto-creates a 1000×26 worksheet on…\|H4]]                 | get_tab auto-creates a 1000×26 worksheet on…                | `data/sheets.py:119-126`                                       | high     | open   |
| [[H5 `get_team` filters `record.get(guild_id) != guild_id`,…\|H5]]        | get_team filters record.get("guild_id") != guild_id,…       | `services/team_service.py:67-72`                               | high     | open   |
| [[H6 `record_match` updates `elo``wins``losses` but never…\|H6]]          | record_match updates elo/wins/losses but never…             | `services/elo_service.py:123-135`                              | high     | done   |
| [[H7 `bot.start(settings.discord_token)` passes a `SecretStr`…\|H7]]      | bot.start(settings.discord_token) passes a SecretStr…       | `scripts/force_sync.py:47`                                     | high     | done   |
| [[H8 `int(settings.discord_guild_id)` with no guard\|H8]]                 | int(settings.discord_guild_id) with no guard                | `scripts/force_sync.py:39`                                     | high     | done   |
| [[H9 No rate-limitbackoffretry on any gspread call\|H9]]                  | No rate-limit/backoff/retry on any gspread call             | `data/sheets.py (all gspread calls) + every service caller`    | high     | open   |
| [[H10 N+1 full-sheet reads\|H10]]                                         | N+1 full-sheet reads                                        | `data/sheets.py:166-203`                                       | high     | open   |
| [[H11 `_species_to_id_normalized` returns `(hash(species_name) %…\|H11]]  | _species_to_id_normalized returns (hash(species_name) %…    | `ml/feature_extractor.py:351`                                  | high     | open   |
| [[H12 `run_mcts(obs, model, n_legal, cfg)` passes `n_legal` (a…\|H12]]    | run_mcts(obs, model, n_legal, cfg) passes n_legal (a…       | `ml/showdown_player.py:177-183 → ml/mcts.py:246-249`           | high     | open   |
| [[H13 `_embed_team_matrix` does `bag[..., ids] = 1.0` with…\|H13]]        | _embed_team_matrix does bag[..., ids] = 1.0 with…           | `ml/train_matchup.py:65-71,112`                                | high     | open   |
| [[H14 `_ReplayEnv``_FakeEnv` obs space `Box(high=1.0)`\|H14]]             | _ReplayEnv/_FakeEnv obs space Box(high=1.0)                 | `ml/browser_trainer.py:205,296-298 vs battle_env.py:453`       | high     | open   |
| [[H15 `build_observation_from_dom` writes HP\|H15]]                       | build_observation_from_dom writes HP                        | `ml/browser_trainer.py:94-124`                                 | high     | open   |
| [[H16 `policy.learn(total_timesteps=n_trans)` on `_ReplayEnv`…\|H16]]     | policy.learn(total_timesteps=n_trans) on _ReplayEnv…        | `ml/browser_trainer.py:418-443`                                | high     | open   |
| [[M1 Unguarded `int(self.season.value or 1)` etc\|M1]]                    | Unguarded int(self.season.value or 1) etc                   | `bot/cogs/draft.py:57-60,168-172`                              | medium   | open   |
| [[M2 `draft_error` calls `interaction.response.send_message` but…\|M2]]   | draft_error calls interaction.response.send_message but…    | `bot/cogs/draft.py:561-565`                                    | medium   | open   |
| [[M3 `on_timeout` calls `force_skip(guild, current_player_id)`…\|M3]]     | on_timeout calls force_skip(guild, current_player_id)…      | `bot/views/draft_view.py:22-31,86-95`                          | medium   | open   |
| [[M4 `report = svc.analyze_pokemon_list(...)` called without…\|M4]]       | report = svc.analyze_pokemon_list(...) called without…      | `bot/views/team_view.py:42-44`                                 | medium   | open   |
| [[M5 Full Showdown export in an inline code block can exceed…\|M5]]       | Full Showdown export in an inline code block can exceed…    | `bot/cogs/team.py:297-300; views/team_view.py:61-64`           | medium   | open   |
| [[M6 `admin_sync` has no `cog_app_command_error`\|M6]]                    | admin_sync has no cog_app_command_error                     | `bot/cogs/admin.py:113-137`                                    | medium   | open   |
| [[M7 `webbrowser.open(...)` runs server-side (bot host), is…\|M7]]        | webbrowser.open(...) runs server-side (bot host), is…       | `bot/cogs/admin.py:383`                                        | medium   | open   |
| [[M8 `asyncio.get_event_loop()` inside a coroutine is deprecated…\|M8]]   | asyncio.get_event_loop() inside a coroutine is deprecated…  | `bot/cogs/ml.py:79`                                            | medium   | open   |
| [[M9 `make_pick` `await`s (`to_thread(save_pick)`,…\|M9]]                 | make_pick awaits (to_thread(save_pick),…                    | `services/draft_service.py:25-30,283-310`                      | medium   | open   |
| [[M10 Snake-draft index math index resets to 0 each round and…\|M10]]     | Snake-draft index math: index resets to 0 each round and…   | `services/draft_service.py (models.py:237-248)`                | medium   | open   |
| [[M11 Auction `place_bid` records bids but there is no method to…\|M11]]  | Auction: place_bid records bids but there is no method to…  | `services/draft_service.py:393-426`                            | medium   | open   |
| [[M12 `int(record.get(elo, 1000))` raises `ValueError` on…\|M12]]         | int(record.get("elo", 1000)) raises ValueError on…          | `services/elo_service.py:83-85,162-166`                        | medium   | open   |
| [[M13 `parse_replay` passes `replay_id``winner``timestamp` but…\|M13]]    | parse_replay passes replay_id/winner/timestamp but…         | `services/battle_sim.py:164-173 ↔ sheets.py:336-343`           | medium   | open   |
| [[M14 `resp.json()` on a non-JSON body (404 HTML, Cloudflare)…\|M14]]     | resp.json() on a non-JSON body (404 HTML, Cloudflare)…      | `services/battle_sim.py:153-154`                               | medium   | open   |
| [[M15 `save_video` fieldtab mismatch (same blank-`match_id`…\|M15]]       | save_video field/tab mismatch (same blank-match_id…         | `services/video_service.py:58-67 ↔ sheets.py:345-352`          | medium   | open   |
| [[M16 Showdown import regex mishandles `Type Null` (stops at…\|M16]]      | Showdown import regex mishandles Type: Null (stops at…      | `services/team_service.py:248-261`                             | medium   | open   |
| [[M17 `find()` returns first dict match on `key in k or k in key`…\|M17]] | find() returns first dict match on key in k or k in key…    | `data/pokeapi.py:62-65`                                        | medium   | open   |
| [[M18 Smogon tier scrape regex `dexSettings = {…}\|M18]]                  | Smogon tier scrape regex dexSettings = {…}                  | `data/smogon.py:36-47; data/showdown.py:54-58,82`              | medium   | open   |
| [[M19 New `aiosqlite.connect` per saveload call\|M19]]                    | New aiosqlite.connect per save/load call                    | `data/db.py:65-130`                                            | medium   | open   |
| [[M20 `best_action` stochastic branch `counts_t counts_t.sum()`\|M20]]    | best_action stochastic branch: counts_t / counts_t.sum()    | `ml/mcts.py:202-205`                                           | medium   | open   |
| [[M21 `predict``policy_probs` do `masked_fill(mask, -inf)` then…\|M21]]   | predict/policy_probs do masked_fill(mask, -inf) then…       | `ml/transformer_model.py:260,290`                              | medium   | open   |
| [[M22 `torch.load(...)` without `weights_only=True` (security…\|M22]]     | torch.load(...) without weights_only=True (security:…       | `ml/train_policy.py:278; pretrain weights load`                | medium   | open   |
| [[M23 `evaluate()` uses `poke_env.battle1` — version-dependent…\|M23]]    | evaluate() uses poke_env.battle1 — version-dependent…       | `ml/train_policy.py:1056`                                      | medium   | open   |
| [[M24 Public-server login sends `\|M24]]                                  | Public-server login sends \                                 | `ml/showdown_client.py:278`                                    | medium   | open   |
| [[M25 `asyncio.Event()` constructed in `__init__` (before loop…\|M25]]    | asyncio.Event() constructed in __init__ (before loop…       | `ml/showdown_client.py:374`                                    | medium   | open   |
| [[M26 Team-HP slot match `my_team_list[i] == my_active` compares…\|M26]]  | Team-HP slot match my_team_list[i] == my_active compares…   | `ml/pretrain.py:199,207`                                       | medium   | open   |
| [[M27 `SimpleHeuristicPlayer.choose_move` does…\|M27]]                    | SimpleHeuristicPlayer.choose_move does…                     | `ml/training_players.py:72`                                    | medium   | open   |
| [[M28 `data.setdefault(...)` runs outside the per-replay try\|M28]]       | data.setdefault(...) runs outside the per-replay try        | `ml/replay_scraper.py:133-138`                                 | medium   | open   |
| [[M29 `settings = Settings()` at import time with required…\|M29]]        | settings = Settings() at import time with required…         | `src/config.py:86`                                             | medium   | open   |
| [[M30 `ws.update` called values-first in one place, range-first…\|M30]]   | ws.update called values-first in one place, range-first…    | `data/sheets.py:148 vs 164,176,463`                            | medium   | open   |
| [[M31 `_OPEN_ROW_RE` alternation precedence `…]].in-progress\|M31]]       | _OPEN_ROW_RE alternation precedence: …\]\].*?in-progress\   | `scripts/sync_closed_issues.py:111-114`                        | medium   | open   |
| [[M32 `urllib.request.urlopen` with no User-Agent\|M32]]                  | urllib.request.urlopen with no User-Agent                   | `scripts/prepare_competitive_data.py:129`                      | medium   | open   |
| [[M33 Monkey-patches private `google.auth._helpers.utcnow`…\|M33]]        | Monkey-patches private google.auth._helpers.utcnow…         | `scripts/setup_google_sheet.py:33-37; setup_ml_sheet.py:33-36` | medium   | open   |
| [[M34 Writes a real Test transaction to the production sheet…\|M34]]      | Writes a real "Test" transaction to the production sheet…   | `scripts/test_sheets_integration.py:163-193,85-147`            | medium   | open   |
| [[L1 Param named `commands` shadows the `discord.ext.commands`…\|L1]]     | Param named commands shadows the discord.ext.commands…      | `bot/main.py:50,57`                                            | low      | open   |
| [[L2 `socket.create_connection(...)` result never closed\|L2]]            | socket.create_connection(...) result never closed           | `bot/cogs/admin.py:375-377`                                    | low      | open   |
| [[L3 `match_upload` claims max 25MB but never checks…\|L3]]               | match_upload claims "max 25MB" but never checks…            | `bot/cogs/stats.py:197-216`                                    | low      | open   |
| [[L4 Help embed can exceed 1024-char field 6000-char total\|L4]]          | Help embed can exceed 1024-char field / 6000-char total     | `bot/cogs/misc.py:44-45`                                       | low      | open   |
| [[L5 Confirm button not disabled before `stop()`\|L5]]                    | Confirm button not disabled before stop()                   | `bot/views/team_import_view.py`                                | low      | open   |
| [[L6 `scrape_format` return code discarded\|L6]]                          | scrape_format return code discarded                         | `data_pipeline.py:269`                                         | low      | open   |
| [[L7 `json.loads(manifest.read_text())` unguarded\|L7]]                   | json.loads(manifest.read_text()) unguarded                  | `data_pipeline.py:125,175`                                     | low      | open   |
| [[L8 Help text all 18 formats but `ALL_FORMATS` has 20\|L8]]              | Help text "all 18 formats" but ALL_FORMATS has 20           | `data_pipeline.py:356`                                         | low      | open   |
| [[L9 Default `API_SECRET_KEY=change-me-in-production` weak…\|L9]]         | Default API_SECRET_KEY="change-me-in-production" weak…      | `setup.py:159`                                                 | low      | open   |
| [[L10 Winloss inferred from player-wide `n_won_battles` delta\|L10]]      | Win/loss inferred from player-wide n_won_battles delta      | `ml/self_play.py:350-361`                                      | low      | open   |
| [[L11 Stale `OBS_DIM = 48`\|L11]]                                         | Stale OBS_DIM = 48                                          | `ml/{self_play,trainer,transformer_model}.py docstrings`       | low      | open   |
| [[L12 Terminal reward broadcast to every transition with no…\|L12]]       | Terminal reward broadcast to every transition with no…      | `ml/trainer.py:123-140`                                        | low      | open   |
| [[L13 `except (asyncio.CancelledError, Exception)` swallows…\|L13]]       | except (asyncio.CancelledError, Exception) swallows…        | `ml/showdown_client.py:133`                                    | low      | open   |
| [[L14 `SelfPlayCallback` is dead code (wired path uses…\|L14]]            | SelfPlayCallback is dead code (wired path uses…             | `ml/train_policy.py:344-384`                                   | low      | open   |
| [[L15 `asyncio.sleep(REQUEST_DELAY)` held inside the semaphore\|L15]]     | asyncio.sleep(REQUEST_DELAY) held inside the semaphore      | `ml/replay_scraper.py:140`                                     | low      | open   |
| [[L16 `apply_fix`\|L16]]                                                  | apply_fix                                                   | `ml/training_doctor.py:230,363`                                | low      | open   |
| [[L17 Sheets writes block createpick\|L17]]                               | Sheets writes block create/pick                             | `services/draft_service.py:152,289`                            | low      | open   |
| [[L18 `getattr(p, tera_type, )` on `Pokemon` (no such attr —…\|L18]]      | getattr(p, "tera_type", "") on Pokemon (no such attr —…     | `services/team_service.py:116`                                 | low      | open   |
| [[L19 Support role bucket initialized but never assigned (dead…\|L19]]    | "Support" role bucket initialized but never assigned (dead… | `services/analytics_service.py:143-150`                        | low      | open   |
| [[L20 `any(... for _ in [1])` — convoluted single-iteration no-op…\|L20]] | any(... for _ in [1]) — convoluted single-iteration no-op…  | `services/battle_sim.py:127`                                   | low      | open   |
| [[L21 `int(player_id)` `ValueError` + `get_user` None\|L21]]              | int(player_id) ValueError + get_user None                   | `services/notification_service.py:99,108`                      | low      | open   |
| [[L22 `ALLOWED_MIME_TYPES` defined but `content_type` never…\|L22]]       | ALLOWED_MIME_TYPES defined but content_type never…          | `services/video_service.py:26`                                 | low      | open   |
| [[L23 `entry[...]` direct indexing in `load()`\|L23]]                     | entry["..."] direct indexing in load()                      | `data/pokeapi.py:34-38`                                        | low      | open   |
| [[L24 DB-URL regex strip is brittle for memoryabs-path URLs\|L24]]        | DB-URL regex strip is brittle for memory/abs-path URLs      | `data/db.py:27`                                                | low      | open   |
| [[L25 Non-atomic in-place rewrite of `pokemon.json`\|L25]]                | Non-atomic in-place rewrite of pokemon.json                 | `data/smogon.py:153; data/showdown.py:87`                      | low      | open   |
| [[L26 No retrybackoff on PokéAPI 429 (batched limit=20)\|L26]]            | No retry/backoff on PokéAPI 429 (batched limit=20)          | `scripts/seed_pokemon_data.py:23-63`                           | low      | open   |
| [[L27 New aiohttp session per probe × ~130 concurrent\|L27]]              | New aiohttp session per probe × ~130 concurrent             | `scripts/scrape_all_formats.py:183,222`                        | low      | open   |
| [[L28 `asyncio.run(...)` at module top level (not under…\|L28]]           | asyncio.run(...) at module top level (not under…            | `scripts/{sync_commands,force_sync}.py`                        | low      | open   |

---
## Roadmap Status

| Phase | Name | Status |
|-------|------|--------|
| 01 | Observation Space Expansion (OBS_DIM 44→48) | ✅ done |
| 02 | Curriculum Opponent (MaxBasePowerPlayer) | ✅ done |
| 03 | BC Pre-Training | ✅ done |
| 04 | Browser Training (Playwright self-play) | ✅ done |
| 05 | MCTSPlayer + Transformer Training | ✅ done |
| 06 | /spar Inference (transformer+MCTS) | 🔄 in progress |

---

## Schema

New issue frontmatter:

```yaml
---
id: ISS-NNN
title: Short title
status: open | in-progress | done | blocked
priority: high | medium | low
phase: "05" | "06" | backlog
labels: [tag1, tag2]
created: YYYY-MM-DD
---
```

Status transitions: `open` → `in-progress` → `done`. Move done rows to a **Closed** section below.

---

## Closed

| ID                                                   | Title                                                       | Phase | Priority | Labels         | Status |
| ---------------------------------------------------- | ----------------------------------------------------------- | ----- | -------- | -------------- | ------ |
| [[ISS-001-mcts-unit-integration-tests\|ISS-001]]     | MCTSPlayer — unit and integration tests                     | 05    | high     | testing, ml    | done   |
| [[ISS-002-mcts-wire-training-opponent\|ISS-002]]     | MCTSPlayer — wire as training pipeline opponent             | 05    | high     | ml, training   | done   |
| [[ISS-003-transformer-train-mcts-selfplay\|ISS-003]] | BattleTransformer — train to convergence via MCTS self-play | 05    | high     | ml, training   | done   |
| [[ISS-004-spar-wire-mcts-inference\|ISS-004]]        | /spar — wire use_mcts=True inference path                   | 06    | high     | bot, inference | done   |
| [[ISS-005-spar-fallback-ppo\|ISS-005]]               | /spar — graceful PPO fallback                               | 06    | high     | bot, inference | done   |
| [[ISS-006-ml-training-environment\|ISS-006]]         | ML training — provision x86 Linux environment               | backlog | medium  | ml, infra      | done   |
