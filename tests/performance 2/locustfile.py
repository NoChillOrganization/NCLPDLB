"""
Performance / load tests using Locust.
Run: locust -f tests/performance/locustfile.py --host http://localhost:8000

Simulates realistic usage patterns:
- Browse Pokemon database (heavy read)
- Check standings / team analysis (medium read)
- Submit draft picks (light write)
"""
from __future__ import annotations

import random
from locust import HttpUser, task, between, events

SAMPLE_GUILD = "123456789"
SAMPLE_PLAYERS = [f"player_{i:04d}" for i in range(16)]
SAMPLE_POKEMON = [
    "pikachu", "charizard", "blastoise", "venusaur", "mewtwo", "lucario",
    "garchomp", "gengar", "tyranitar", "dragonite", "salamence", "metagross",
    "heatran", "rotom-wash", "landorus-therian", "tornadus-therian",
    "tapu-koko", "tapu-fini", "urshifu-rapid-strike", "rillaboom",
]
TIERS = ["OU", "UU", "RU", "NU", "Uber", ""]


class PokemonBrowserUser(HttpUser):
    """Simulates a user browsing the Pokemon database (read-heavy)."""
    wait_time = between(0.5, 2.0)
    weight = 5

    @task(10)
    def browse_pokemon_list(self):
        tier = random.choice(TIERS)
        gen = random.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
        params = {}
        if tier:
            params["tier"] = tier
        if gen:
            params["gen"] = gen
        self.client.get("/api/pokemon", params=params, name="/api/pokemon[list]")

    @task(5)
    def search_pokemon(self):
        query = random.choice(["char", "pika", "gen", "sala", "ttar", "man"])
        self.client.get("/api/pokemon", params={"search": query}, name="/api/pokemon[search]")

    @task(3)
    def get_single_pokemon(self):
        name = random.choice(SAMPLE_POKEMON)
        self.client.get(f"/api/pokemon/{name}", name="/api/pokemon[single]")

    @task(1)
    def check_health(self):
        self.client.get("/health")


class StandingsUser(HttpUser):
    """Simulates users checking standings, teams, and schedules."""
    wait_time = between(1.0, 3.0)
    weight = 3

    @task(5)
    def view_standings(self):
        self.client.get(f"/api/leagues/{SAMPLE_GUILD}/standings")

    @task(3)
    def view_team(self):
        player = random.choice(SAMPLE_PLAYERS)
        self.client.get(f"/api/teams/{SAMPLE_GUILD}/{player}", name="/api/teams[view]")

    @task(2)
    def view_team_analysis(self):
        player = random.choice(SAMPLE_PLAYERS)
        self.client.get(f"/api/teams/{SAMPLE_GUILD}/{player}/analysis", name="/api/teams[analysis]")

    @task(1)
    def view_matchup(self):
        p1, p2 = random.sample(SAMPLE_PLAYERS, 2)
        self.client.get(f"/api/matchups/{SAMPLE_GUILD}/{p1}/{p2}", name="/api/matchups")


class ActiveDraftUser(HttpUser):
    """Simulates players actively picking during a draft."""
    wait_time = between(5.0, 30.0)
    weight = 1

    def on_start(self):
        self.player_id = random.choice(SAMPLE_PLAYERS)
        self.available = list(SAMPLE_POKEMON)

    @task(10)
    def check_draft_state(self):
        self.client.get(f"/api/drafts/{SAMPLE_GUILD}", name="/api/drafts[state]")

    @task(3)
    def make_pick(self):
        if not self.available:
            return
        pokemon = random.choice(self.available)
        self.available.remove(pokemon)
        self.client.post(
            f"/api/drafts/{SAMPLE_GUILD}/pick",
            json={"player_id": self.player_id, "pokemon_name": pokemon},
            name="/api/drafts[pick]",
        )


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("\n=== Pokemon Draft League Load Test ===")
    print(f"Target: {environment.host}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    if environment.runner:
        t = environment.runner.stats.total
        print("\n=== Results ===")
        print(f"Requests: {t.num_requests} | Failures: {t.num_failures}")
        print(f"Avg: {t.avg_response_time:.1f}ms | p95: {t.get_response_time_percentile(0.95):.1f}ms")
        print(f"RPS: {t.current_rps:.1f}")
