"""
Type Chart utility for normalizing type effectiveness.
"""
import math
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from poke_env.battle import Move, Pokemon

def get_type_effectiveness_float(move: "Move", target: "Pokemon") -> float:
    """
    Returns normalized type effectiveness centered at 0.0 (Decision 43).
    Range: [-1.0, 1.0]
    
    Mapping:
    - 4x weak:   1.0
    - 2x weak:   0.5
    - Neutral:   0.0
    - 0.5x resist: -0.5
    - 0.25x resist: -1.0
    - Immune:    -1.0
    """
    try:
        mult = target.damage_multiplier(move)
    except Exception: # pragma: no cover
        return 0.0 # Unknown/Neutral default
        
    if mult == 0:
        return -1.0
        
    # Clamp to [-2, 2] in log2 space (0.25x to 4x)
    log_mult = math.log2(mult)
    return max(-1.0, min(1.0, log_mult / 2.0))

