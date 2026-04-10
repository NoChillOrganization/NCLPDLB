"""
Integration test for the rewritten sheets.py against the live spreadsheet.
Tests all public methods that were rewritten.

Run: py -3 scripts/test_sheets_integration.py
"""
import sys
import io
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PASS = "✓"
FAIL = "✗"
WARN = "?"
results = []


def check(name: str, condition: bool, detail: str = "") -> None:
    icon = PASS if condition else FAIL
    msg = f"  {icon} {name}"
    if detail:
        msg += f"  [{detail}]"
    print(msg)
    results.append((name, condition))


def warn(name: str, detail: str = "") -> None:
    msg = f"  {WARN} {name} (warning/skip)"
    if detail:
        msg += f"  [{detail}]"
    print(msg)
    results.append((name, True))  # warnings don't count as failures


def main() -> None:
    print("=" * 60)
    print("sheets.py Integration Test")
    print("=" * 60)

    # ── Import the module ────────────────────────────────────────
    print("\n--- Import & connect ---")
    try:
        from src.data.sheets import sheets, Tab
        print(f"  {PASS} Imported sheets.py successfully")
        results.append(("import", True))
    except Exception as e:
        print(f"  {FAIL} Import failed: {e}")
        results.append(("import", False))
        return

    try:
        sheets.connect()
        print(f"  {PASS} Connected to Google Sheets")
        results.append(("connect", True))
    except Exception as e:
        print(f"  {FAIL} Connection failed: {e}")
        results.append(("connect", False))
        return

    # ── Tab existence ────────────────────────────────────────────
    print("\n--- Tab existence ---")
    critical_tabs = [
        Tab.SETUP, Tab.RULES, Tab.SCHEDULE, Tab.MATCH_STATS,
        Tab.STANDINGS, Tab.TRANSACTIONS, Tab.POKEDEX, Tab.POKEMON_STATS,
        Tab.MVP_RACE, Tab.PLAYOFFS,
    ]
    for tab in critical_tabs:
        try:
            sheets.get_tab(tab)
            check(f"Tab '{tab}' exists", True)
        except Exception as e:
            check(f"Tab '{tab}' exists", False, str(e))

    # ── Setup tab reads ──────────────────────────────────────────
    print("\n--- Setup tab reads ---")
    try:
        setup = sheets.get_league_setup()
        check("get_league_setup() returns dict", isinstance(setup, dict))
        check("league_name present", "league_name" in setup, setup.get("league_name", ""))
        check("league_name is 'No Chill League'",
              setup.get("league_name", "").strip() == "No Chill League",
              repr(setup.get("league_name", "")))
        check("coaches list present", isinstance(setup.get("coaches"), list))
        check("coaches not empty", len(setup.get("coaches", [])) > 0,
              f"{len(setup.get('coaches', []))} coaches")
        check("first coach has name",
              bool(setup["coaches"][0].get("name") if setup.get("coaches") else ""),
              setup["coaches"][0].get("name", "") if setup.get("coaches") else "")
        check("total_weeks is numeric string",
              setup.get("total_weeks", "").isdigit() if setup.get("total_weeks") else False,
              setup.get("total_weeks", ""))
        check("current_week present", bool(setup.get("current_week")),
              setup.get("current_week", ""))
        print(f"    Setup values: {", ".join(f'{k}={v!r}' for k, v in setup.items() if k != 'coaches')}")
        print(f"    Coaches ({len(setup.get('coaches', []))}): "
              f"{[c['name'] for c in setup.get('coaches', [])[:5]]}")
    except Exception as e:
        check("get_league_setup()", False, str(e))

    # ── Standings tab reads ──────────────────────────────────────
    print("\n--- Standings tab reads ---")
    try:
        standings = sheets.get_standings()
        check("get_standings() returns list", isinstance(standings, list))
        check("standings not empty", len(standings) > 0, f"{len(standings)} entries")
        if standings:
            first = standings[0]
            check("standing has rank", "rank" in first, first.get("rank", ""))
            check("standing has coach_name", bool(first.get("coach_name")), first.get("coach_name", ""))
            check("standing has team_name", bool(first.get("team_name")), first.get("team_name", ""))
            check("standing has record", bool(first.get("record")), first.get("record", ""))
            print(f"    #1: {first.get('team_name')} ({first.get('coach_name')}) — {first.get('record')}")
            print(f"    Total standings: {len(standings)}")
    except Exception as e:
        check("get_standings()", False, str(e))

    # ── Schedule tab reads ───────────────────────────────────────
    print("\n--- Schedule tab reads ---")
    try:
        schedule = sheets.get_schedule()
        check("get_schedule() returns list", isinstance(schedule, list))
        check("schedule not empty", len(schedule) > 0, f"{len(schedule)} matches")
        if schedule:
            first = schedule[0]
            check("match has week", bool(first.get("week")), first.get("week", ""))
            check("match has coach1", bool(first.get("coach1")), first.get("coach1", ""))
            check("match has coach2", bool(first.get("coach2")), first.get("coach2", ""))
            print(f"    First match: {first.get('week')} — {first.get('coach1')} vs {first.get('coach2')}")
    except Exception as e:
        check("get_schedule()", False, str(e))

    # ── Transactions tab reads ───────────────────────────────────
    print("\n--- Transactions tab reads ---")
    try:
        transactions = sheets.get_transactions()
        check("get_transactions() returns list", isinstance(transactions, list))
        check("transactions not empty", len(transactions) > 0, f"{len(transactions)} entries")
        if transactions:
            first = transactions[0]
            check("transaction has number", bool(first.get("number")), first.get("number", ""))
            check("transaction has event", bool(first.get("event")), first.get("event", ""))
            check("transaction has coach1", bool(first.get("coach1")), first.get("coach1", ""))
            print(f"    First: {first.get('number')} {first.get('event')} — "
                  f"{first.get('coach1')} / {first.get('pokemon1')}")
    except Exception as e:
        check("get_transactions()", False, str(e))

    # ── Rules tab reads ──────────────────────────────────────────
    print("\n--- Rules tab reads ---")
    try:
        rules = sheets.get_rules()
        check("get_rules() returns list", isinstance(rules, list))
        check("rules not empty", len(rules) > 0, f"{len(rules)} rules")
        if rules:
            print(f"    First rule (first 80 chars): {rules[0][:80]}")
    except Exception as e:
        check("get_rules()", False, str(e))

    # ── Save transaction (dry-run using a test entry) ────────────
    print("\n--- Transactions write (live test) ---")
    import time
    try:
        before = sheets.get_transactions()
        before_count = len(before)

        test_txn = {
            "type": "Test",
            "week": "99",
            "from_player_name": "TestCoach1",
            "to_player_name": "TestCoach2",
            "pokemon_given": "Pikachu",
            "pokemon_received": "Raichu",
            "status": "Integration test — delete me",
        }
        sheets.save_transaction(test_txn)
        time.sleep(2)

        after = sheets.get_transactions()
        after_count = len(after)
        check("save_transaction() increased row count by 1",
              after_count == before_count + 1,
              f"before={before_count}, after={after_count}")
        if after:
            last = after[-1]
            check("test transaction has correct coach", last.get("coach1") == "TestCoach1",
                  last.get("coach1", ""))
            check("test transaction has correct pokemon", last.get("pokemon1") == "Pikachu",
                  last.get("pokemon1", ""))
    except Exception as e:
        check("save_transaction()", False, str(e))

    # ── No-op write methods (should log warnings, not raise) ─────
    print("\n--- No-op write methods (should not raise) ---")
    try:
        sheets.upsert_standing({"player_name": "test"})
        check("upsert_standing() safe no-op", True)
    except Exception as e:
        check("upsert_standing() safe no-op", False, str(e))

    try:
        sheets.save_match_stats({"match_id": "test"})
        check("save_match_stats() safe no-op", True)
    except Exception as e:
        check("save_match_stats() safe no-op", False, str(e))

    try:
        sheets.save_schedule_match({"week": 1})
        check("save_schedule_match() safe no-op", True)
    except Exception as e:
        check("save_schedule_match() safe no-op", False, str(e))

    try:
        sheets.save_playoff_match({"round": "Quarterfinals"})
        check("save_playoff_match() safe no-op", True)
    except Exception as e:
        check("save_playoff_match() safe no-op", False, str(e))

    try:
        sheets.refresh_mvp_race([])
        check("refresh_mvp_race() safe no-op", True)
    except Exception as e:
        check("refresh_mvp_race() safe no-op", False, str(e))

    # ── get_league_setup() with server_id (compat) ───────────────
    print("\n--- Backwards-compat ---")
    try:
        setup = sheets.get_league_setup("12345678")
        check("get_league_setup(server_id) still returns dict", isinstance(setup, dict))
    except Exception as e:
        check("get_league_setup(server_id) compat", False, str(e))

    # ── Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    total  = len(results)
    passed = sum(1 for _, ok in results if ok)
    failed = total - passed
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if failed == 0:
        print("✓ All checks passed!")
    else:
        print("Failed checks:")
        for name, ok in results:
            if not ok:
                print(f"  ✗ {name}")


if __name__ == "__main__":
    main()
