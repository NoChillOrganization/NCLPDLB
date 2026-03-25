"""
End-to-End test — Full 4-player snake draft simulation.
Tests the entire flow: create → join → start → pick all rounds → complete.
Run: pytest tests/e2e/test_full_draft.py -v
"""
import pytest
from unittest.mock import MagicMock, patch

from src.data.models import DraftFormat, DraftStatus
from src.services.draft_service import DraftService


GUILD = "e2e_guild"
PLAYERS = ["alice", "bob", "charlie", "diana"]
ROUNDS = 3

# Fake Pokemon for picks
POKEMON_POOL = [f"Pokemon{i}" for i in range(1, ROUNDS * len(PLAYERS) + 5)]


def make_mock_pokemon(name: str):
    m = MagicMock()
    m.name = name
    m.types = ["normal"]
    m.type_string = "Normal"
    m.showdown_tier = "OU"
    m.sprite_url = ""
    m.base_stats.total = 500
    return m


@pytest.mark.asyncio
async def test_full_snake_draft():
    """
    Full E2E snake draft:
    - 4 players, 3 rounds = 12 total picks
    - Round 1: alice, bob, charlie, diana
    - Round 2 (snake reversal): diana, charlie, bob, alice
    - Round 3: alice, bob, charlie, diana
    """
    svc = DraftService()

    with patch("src.services.draft_service.sheets") as mock_sheets, \
         patch("src.services.draft_service.pokemon_db") as mock_db:
        mock_sheets.save_league_setup = MagicMock()
        mock_sheets.save_pick = MagicMock()

        def fake_find(name):
            return make_mock_pokemon(name)

        mock_db.find = fake_find

        # Step 1: Create draft
        draft = await svc.create_draft(GUILD, PLAYERS[0], DraftFormat.SNAKE, rounds=ROUNDS)
        assert draft.status == DraftStatus.SETUP

        # Step 2: All players join
        for p in PLAYERS:
            result = await svc.add_player(GUILD, p)
            assert result.success
        assert draft.player_count == 4

        # Step 3: Start
        draft.status = DraftStatus.ACTIVE  # bypass commissioner check for test

        # Step 4: Simulate all picks
        expected_order_r1 = PLAYERS
        expected_order_r2 = list(reversed(PLAYERS))
        expected_order_r3 = PLAYERS
        expected_full = expected_order_r1 + expected_order_r2 + expected_order_r3

        picks_made = []
        for i, expected_player in enumerate(expected_full):
            current = draft.current_player_id
            assert current == expected_player, (
                f"Pick {i+1}: expected {expected_player} but got {current}"
            )
            pokemon_name = POKEMON_POOL[i]
            result = await svc.make_pick(GUILD, current, pokemon_name)
            assert result.success, f"Pick {i+1} failed: {result.error}"
            picks_made.append((current, pokemon_name))

        # Step 5: Draft complete
        assert draft.status == DraftStatus.COMPLETED
        assert len(draft.picks) == ROUNDS * len(PLAYERS)

        # Step 6: Each player has exactly ROUNDS pokemon
        for player in PLAYERS:
            player_picks = [p.pokemon_name for p in draft.picks if p.player_id == player]
            assert len(player_picks) == ROUNDS, f"{player} should have {ROUNDS} picks"

        # Step 7: No duplicates
        all_picked = [p.pokemon_name for p in draft.picks]
        assert len(all_picked) == len(set(all_picked)), "Duplicate Pokemon detected!"


@pytest.mark.asyncio
async def test_ban_phase_blocks_picks():
    svc = DraftService()
    with patch("src.services.draft_service.sheets"), \
         patch("src.services.draft_service.pokemon_db") as mock_db:
        mock_db.find = lambda n: make_mock_pokemon(n)

        from src.data.models import DraftStatus
        draft = await svc.create_draft(GUILD + "_ban", "p1", DraftFormat.CUSTOM)
        await svc.add_player(GUILD + "_ban", "p1")
        await svc.add_player(GUILD + "_ban", "p2")
        draft.status = DraftStatus.BAN_PHASE

        # Ban a pokemon
        ban_result = await svc.ban_pokemon(GUILD + "_ban", "p1", "Garchomp")
        assert ban_result.success

        # Start draft proper
        draft.status = DraftStatus.ACTIVE

        # Try to pick banned pokemon
        pick_result = await svc.make_pick(GUILD + "_ban", "p1", "Garchomp")
        assert not pick_result.success
        assert "banned" in pick_result.error.lower()


@pytest.mark.asyncio
async def test_draft_not_your_turn():
    svc = DraftService()
    with patch("src.services.draft_service.sheets"), \
         patch("src.services.draft_service.pokemon_db") as mock_db:
        mock_db.find = lambda n: make_mock_pokemon(n)

        draft = await svc.create_draft(GUILD + "_turn", "p1", DraftFormat.SNAKE)
        await svc.add_player(GUILD + "_turn", "p1")
        await svc.add_player(GUILD + "_turn", "p2")
        draft.status = DraftStatus.ACTIVE

        # p2 tries to pick when it's p1's turn
        result = await svc.make_pick(GUILD + "_turn", "p2", "Pikachu")
        assert not result.success
        assert "not your turn" in result.error.lower()
