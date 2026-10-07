"""Normalized internal schema. The rest of the app depends on THESE types,
not on Awpy/demoparser directly."""
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

# Event type constants
KILL = "KILL"
OPENING_KILL = "OPENING_KILL"
MULTI_KILL = "MULTI_KILL"
CLUTCH = "CLUTCH"
BOMB_PLANT = "BOMB_PLANT"
BOMB_DEFUSE = "BOMB_DEFUSE"
BOMB_EXPLODE = "BOMB_EXPLODE"
ROUND_START = "ROUND_START"
ROUND_END = "ROUND_END"


@dataclass
class GameEvent:
    """Normalized event emitted by any GameDataSource."""
    type: str
    timestamp: float = 0.0   # seconds into the match
    tick: int = 0
    round: int = 0
    player: Optional[str] = None     # primary actor (attacker)
    team: Optional[str] = None       # actor side: "CT" / "T"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


@dataclass
class MatchInfo:
    map: str = "unknown"
    team_ct: str = "CT"
    team_t: str = "T"
    players: List[str] = field(default_factory=list)
    tickrate: int = 64


# Confidence levels for mechanical / inferred claims
CERTAIN = "CERTAIN"
STRONGLY_INFERRED = "STRONGLY_INFERRED"
UNCERTAIN = "UNCERTAIN"
