"""
Type Chart utility for normalizing type effectiveness.
"""
import math
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from poke_env.battle import Move, Pokemon

def get_type_effectiveness_float(move: "Move", target: "Pokemon") -> float:
    """
    Returns normalized type effectiveness:
    - 0.0: Immune (0x)
    - 0.25: 0.25x
    - 0.5: 0.5x
    - 0.75: 1x (Neutral)
    - 0.875: 2x
    - 1.0: 4x
    
    Actually, the ROADMAP.md suggested a specific formula:
    `0.0 if mult==0 else (log2(mult)+2)/4`
    - mult=0.25 -> ( -2 + 2 ) / 4 = 0.0  -- WAIT. 
    If mult=1 -> ( 0 + 2 ) / 4 = 0.5
    If mult=2 -> ( 1 + 2 ) / 4 = 0.75
    If mult=4 -> ( 2 + 2 ) / 4 = 1.0
    If mult=0.5 -> ( -1 + 2 ) / 4 = 0.25
    If mult=0 -> 0.0
    
    This is very clean.
    """
    mult = target.damage_multiplier(move)
    if mult == 0:
        return 0.0
    return (math.log2(mult) + 2) / 4.0
