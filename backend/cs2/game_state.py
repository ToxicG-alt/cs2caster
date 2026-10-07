"""Game State Engine: reconstructs match/round/player state from normalized events,
and enriches the kill stream (opening kills, multi-kills, clutch situations)."""
import logging
from typing import Dict, List

from .models import GameEvent

log = logging.getLogger("cs2.game_state")


class RoundState:
    def __init__(self, number):
        self.number = number
        self.start_ts = 0.0
        self.end_ts = None
        self.winner = None
        self.reason = None
        self.bomb_planted = False
        self.bomb_plant_ts = None
        self.kills: List[GameEvent] = []            # in order
        self.alive = {"CT": set(), "T": set()}      # living players per side
        self.roster = {"CT": set(), "T": set()}
        self.opening_kill = None
        self.clutch = None                           # dict if a clutch occurred

    @property
    def score_at_end(self):
        return (self.winner, self.reason)


class MatchState:
    def __init__(self, info):
        self.info = info
        self.rounds: List[RoundState] = []
        self.ct_score = 0
        self.t_score = 0


def build_match_state(info, events: List[GameEvent]):
    """Sequentially rebuild state and return (MatchState, enriched_round_list)."""
    match = MatchState(info)
    current: RoundState = None
    rounds_by_no: Dict[int, RoundState] = {}

    # First pass: discover rosters per round side from kill participation.
    roster = {}  # round -> {"CT": set, "T": set}
    for e in events:
        if e.type == "KILL":
            r = roster.setdefault(e.round, {"CT": set(), "T": set()})
            if e.team in ("CT", "T") and e.player:
                r[e.team].add(e.player)
            vt = e.metadata.get("victim_team")
            vic = e.metadata.get("victim")
            if vt in ("CT", "T") and vic:
                r[vt].add(vic)

    for e in events:
        if e.type == "ROUND_START":
            current = RoundState(e.round)
            current.start_ts = e.timestamp
            match.rounds.append(current)
            rounds_by_no[e.round] = current
            rr = roster.get(e.round, {"CT": set(), "T": set()})
            # Assume 5 per side; pad with discovered names.
            for sidek in ("CT", "T"):
                names = set(rr[sidek])
                i = len(names)
                while len(names) < 5:
                    names.add(f"{sidek}_player_{i}")
                    i += 1
                current.roster[sidek] = set(names)
                current.alive[sidek] = set(names)
        elif e.type == "BOMB_PLANT":
            if current:
                current.bomb_planted = True
                current.bomb_plant_ts = e.timestamp
        elif e.type == "KILL":
            if current is None or current.number != e.round:
                current = rounds_by_no.get(e.round)
            if current is None:
                continue
            if current.opening_kill is None:
                current.opening_kill = e
            current.kills.append(e)
            vic = e.metadata.get("victim")
            vt = e.metadata.get("victim_team")
            if vt in ("CT", "T") and vic in current.alive.get(vt, set()):
                current.alive[vt].discard(vic)
        elif e.type == "ROUND_END":
            cur = rounds_by_no.get(e.round, current)
            if cur:
                cur.end_ts = e.timestamp
                cur.winner = e.metadata.get("winner")
                cur.reason = e.metadata.get("reason")
                if e.metadata.get("ct_score") is not None:
                    match.ct_score = e.metadata["ct_score"]
                    match.t_score = e.metadata["t_score"]
                elif cur.winner == "CT":
                    match.ct_score += 1
                elif cur.winner == "T":
                    match.t_score += 1

    return match
