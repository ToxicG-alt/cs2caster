"""Deterministic highlight detection, clutch & multi-kill detection, mechanical
timing analysis, scoring and clustering. The LLM is NOT used here."""
import logging
from typing import Dict, List

from .config import hype_level_from_score
from .models import CERTAIN, STRONGLY_INFERRED

log = logging.getLogger("cs2.detection")

AWP = {"AWP", "awp", "SSG 08", "ssg08"}
KNIFE_HINTS = ("knife", "bayonet", "karambit")


def _is_knife(w):
    w = (w or "").lower()
    return any(h in w for h in KNIFE_HINTS)


def _is_awp(w):
    return (w or "") in AWP or "awp" in (w or "").lower()


def detect_round_highlights(match, cfg) -> List[Dict]:
    """Return a list of candidate situations (one per notable round moment)."""
    situations = []
    for rnd in match.rounds:
        if not rnd.kills:
            continue
        situations.extend(_analyze_round(match, rnd, cfg))
    # score + hype level + sort
    for s in situations:
        s["hype_level"] = hype_level_from_score(s["hype_score"], cfg)
    situations.sort(key=lambda s: s["hype_score"], reverse=True)
    return situations


def _per_player_kill_sequences(rnd):
    seq = {}
    for k in rnd.kills:
        seq.setdefault(k.player, []).append(k)
    return seq


def _analyze_round(match, rnd, cfg):
    sc = cfg["scoring"]
    tm = cfg["timing"]
    out = []
    seq = _per_player_kill_sequences(rnd)

    for player, kills in seq.items():
        if not player:
            continue
        kills = sorted(kills, key=lambda k: k.tick)
        n = len(kills)
        gaps = [round(kills[i].timestamp - kills[i - 1].timestamp, 2) for i in range(1, n)]
        weapons = [k.metadata.get("weapon") for k in kills]
        first = kills[0]
        last = kills[-1]
        reasons = []
        score = 0
        confidence = CERTAIN
        mechanical = []

        # base + opening + low hp + round-winning + bomb
        score += n * sc["normal_kill"]
        reasons.append(f"{n} kill(s)")
        if rnd.opening_kill is kills[0]:
            score += sc["opening_kill"]
            reasons.append("opening kill")
        low_hp_kills = [k for k in kills if (k.metadata.get("attacker_hp") or 100) <= tm["low_hp_threshold"]]
        if low_hp_kills:
            score += sc["low_hp_kill"]
            reasons.append("low-HP kill")
        very_low = min([(k.metadata.get("attacker_hp") or 100) for k in kills])
        if very_low <= tm["very_low_hp_threshold"]:
            score += sc["very_low_hp_survival"]
            reasons.append(f"survived at {very_low} HP")
        if rnd.winner and player and any(k.team == rnd.winner for k in kills) and last is rnd.kills[-1]:
            score += sc["round_winning_kill"]
            reasons.append("round-winning kill")
        if rnd.bomb_planted:
            score += sc["bomb_critical_kill"]
            reasons.append("bomb in play")

        # multi-kill tiers
        if n == 2:
            score += sc["double_rapid"] if gaps and min(gaps) <= tm["fast_double_s"] else 2
            if gaps and min(gaps) <= tm["fast_double_s"]:
                reasons.append(f"fast double ({min(gaps)}s)")
        elif n == 3:
            score += sc["triple"]
            reasons.append("triple kill (3K)")
        elif n == 4:
            score += sc["quad"]
            reasons.append("quad kill (4K)")
        elif n >= 5:
            score += sc["ace"]
            reasons.append("ACE (5K)")

        # mechanical timing analysis
        if n >= 2 and gaps:
            total = round(last.timestamp - first.timestamp, 2)
            fastest = min(gaps)
            if n >= 3 and total <= tm["fast_triple_s"]:
                mechanical.append(f"3+ kills in {total}s")
            if fastest <= tm["extremely_fast_s"]:
                mechanical.append(f"kills {fastest}s apart (extremely fast)")
                confidence = STRONGLY_INFERRED
            if _is_awp(weapons[0]) and n >= 2 and fastest <= tm["fast_double_s"]:
                score += sc["fast_awp_multi"]
                mechanical.append("rapid AWP multi")
        if any(_is_knife(w) for w in weapons):
            score += sc["knife_kill"]
            reasons.append("knife kill")

        # --- clutch detection ---
        clutch = _detect_clutch(rnd, player, kills, cfg)
        situation_type = _multi_label(n)
        if clutch:
            score += clutch["score_bonus"]
            reasons.extend(clutch["reasons"])
            situation_type = clutch["situation"]

        out.append({
            "round": rnd.number,
            "player": player,
            "team": first.team,
            "situation_type": situation_type,
            "kills": n,
            "gaps_s": gaps,
            "weapons": weapons,
            "min_hp": very_low,
            "bomb_planted": rnd.bomb_planted,
            "round_won": bool(rnd.winner and first.team == rnd.winner),
            "sequence_duration": round(last.timestamp - first.timestamp, 2) if n >= 2 else 0.0,
            "start_ts": first.timestamp,
            "end_ts": last.timestamp,
            "hype_score": score,
            "reasons": reasons + mechanical,
            "mechanical": mechanical,
            "confidence": confidence,
            "clutch": clutch,
            "headshots": sum(1 for k in kills if k.metadata.get("headshot")),
            "score_ct": match.ct_score,
            "score_t": match.t_score,
        })
    return out


def _multi_label(n):
    return {1: "single_kill", 2: "double_kill", 3: "triple_kill",
            4: "quad_kill"}.get(n, "ace" if n >= 5 else "single_kill")


def _detect_clutch(rnd, player, kills, cfg):
    """A clutch = player becomes the LAST alive on their side facing >=2 enemies,
    then we measure what they did from that moment on."""
    team = kills[0].team
    if team not in ("CT", "T"):
        return None
    enemy = "T" if team == "CT" else "CT"
    sc = cfg["scoring"]
    tm_alive = set(rnd.roster.get(team, set()))
    en_alive = set(rnd.roster.get(enemy, set()))
    clutch_start_tick = None
    enemies_at_start = None
    for k in sorted(rnd.kills, key=lambda x: x.tick):
        vic, vt = k.metadata.get("victim"), k.metadata.get("victim_team")
        if vt == team:
            tm_alive.discard(vic)
        elif vt == enemy:
            en_alive.discard(vic)
        if (clutch_start_tick is None and player in tm_alive
                and not (tm_alive - {player}) and len(en_alive) >= 2):
            clutch_start_tick = k.tick
            enemies_at_start = len(en_alive)
    if clutch_start_tick is None:
        return None

    clutch_kills = [k for k in kills if k.tick >= clutch_start_tick]
    if not clutch_kills:
        return None
    won = bool(rnd.winner == team)
    bonus_map = {2: sc["clutch_1v2"], 3: sc["clutch_1v3"],
                 4: sc["clutch_1v4"], 5: sc["clutch_1v5"]}
    bonus = bonus_map.get(min(enemies_at_start, 5), sc["clutch_1v5"])
    hp_start = clutch_kills[0].metadata.get("attacker_hp") or 100
    if hp_start <= cfg["timing"]["very_low_hp_threshold"]:
        bonus += sc["huge_disadvantage"]
    return {
        "type": "clutch",
        "player": player,
        "situation": f"clutch_1v{enemies_at_start}",
        "starting_situation": f"1v{enemies_at_start}",
        "enemies": enemies_at_start,
        "hp_start": hp_start,
        "kills": len(clutch_kills),
        "duration": round(clutch_kills[-1].timestamp - clutch_kills[0].timestamp, 2),
        "round_won": won,
        "score_bonus": bonus,
        "reasons": [f"1v{enemies_at_start} clutch", f"started at {hp_start} HP",
                    "clutch WON" if won else "clutch lost"],
    }


def cluster_situations(situations, cfg):
    """Merge situations happening in the same round close in time (not used to
    drop data, just to avoid double commentary). Returns deduped list."""
    window = cfg["clustering"]["window_s"]
    situations = sorted(situations, key=lambda s: (s["round"], s["start_ts"]))
    clustered, last = [], {}
    for s in situations:
        key = s["round"]
        prev = last.get(key)
        if prev and abs(s["start_ts"] - prev["end_ts"]) <= window and prev["player"] == s["player"]:
            # same player burst already represented -> keep higher score
            if s["hype_score"] > prev["hype_score"]:
                clustered[clustered.index(prev)] = s
                last[key] = s
            continue
        clustered.append(s)
        last[key] = s
    clustered.sort(key=lambda s: s["hype_score"], reverse=True)
    return clustered
