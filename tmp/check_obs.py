import sys
import os

# Add src to path
sys.path.append('f:/Claude Code/projects/pokemon-draft-bot/NCLPDLB')

from src.ml.battle_env import build_observation, build_doubles_observation
from unittest.mock import MagicMock

class MockBattle:
    def __init__(self):
        self.active_pokemon = MagicMock()
        self.active_pokemon.species = "pikachu"
        self.active_pokemon.moves = {"m1": MagicMock()}
        self.active_pokemon.status = None
        self.active_pokemon.boosts = {}
        self.opponent_active_pokemon = MagicMock()
        self.opponent_active_pokemon.species = "charmander"
        self.opponent_active_pokemon.status = None
        self.team = {"p1": MagicMock()}
        self.opponent_team = {"o1": MagicMock()}
        self.available_moves = [[]]
        self.weather = {}
        self.fields = {}
        self.turn = 10

def check():
    battle = MockBattle()
    # Mocking more complex structure for doubles if needed
    battle.active_pokemon = [MagicMock(), MagicMock()]
    battle.opponent_active_pokemon = [MagicMock(), MagicMock()]
    
    # We can't easily run it because it needs poke_env imports which might fail
    print("This is a placeholder check")

if __name__ == "__main__":
    # Just read the file and count idx increments manually or via regex
    with open('f:/Claude Code/projects/pokemon-draft-bot/NCLPDLB/src/ml/battle_env.py', 'r') as f:
        content = f.read()
        
    def count_idx(func_name, content):
        import re
        start_match = re.search(f"def {func_name}", content)
        if not start_match: return None
        func_content = content[start_match.start():]
        # Find the next def or end of file
        next_def = re.search("\ndef ", func_content[1:])
        if next_def:
            func_content = func_content[:next_def.start()+1]
            
        print(f"--- {func_name} ---")
        increments = re.findall(r"idx \+= (\d+|[A-Z_]+)", func_content)
        total = 0
        for inc in increments:
            if inc.isdigit():
                total += int(inc)
            else:
                # Need to find constant value
                const_match = re.search(f"{inc} = (\d+)", content)
                if const_match:
                    total += int(const_match.group(1))
                else:
                    print(f"Unknown constant: {inc}")
        print(f"Total calculated idx: {total}")
        return total

    count_idx("build_observation", content)
    count_idx("build_doubles_observation", content)
