"""Chronological, event-driven commentary engine (live-caster behavior on a completed demo).

Walks the GameEvent stream in DEMO-TIME order, maintains running game state, and for each
event decides — using ONLY past+current information — whether it deserves commentary, with
what priority, and whether a cheap deterministic template or a (rare) LLM call is used.

The engine NEVER looks at future events when producing a line. This is what makes it feel live.
"""
import logging
import random
from dataclasses import dataclass, field
from typing import List, Optional

from .detection import _is_awp, _is_knife

log = logging.getLogger("cs2.engine")


@dataclass
class CommentaryEvent:
    demo_time: float
    round: int
    event_type: str
    reason: str
    priority: int
    hype_level: int
    text: str
    method: str                      # TEMPLATE | LLM
    player: Optional[str] = None
    victim: Optional[str] = None
    facts: List[str] = field(default_factory=list)
    duration: float = 1.5


def _mmss(t):
    return f"{int(t // 60):02d}:{t % 60:05.2f}"


def _dur(text):
    words = max(1, len(text.split()))
    return round(words / 2.8 + 0.5, 2)


class _Round:
    def __init__(self, number):
        self.number = number
        self.alive = {"CT": set(), "T": set()}
        self.first_kill_done = False
        self.bomb_planted = False
        self.kill_seq = {}        # player -> [timestamps]
        self.clutch = None        # {player, side, enemies, kills, hp_start}


class CommentaryEngine:
    def __init__(self, info, events, cfg, llm):
        self.info = info
        self.events = events
        self.cfg = cfg
        self.llm = llm
        self.sc = cfg["events"]["scoring"]
        self.win = cfg["events"]["windows"]
        self.th = cfg["events"]["thresholds"]
        self.tpl = cfg["templates"]
        self.rng = random.Random(13)
        self._last_tpl = {}
        self.last_comment_t = -999.0
        self.ct_score = 0
        self.t_score = 0
        self.llm_calls = 0
        self.timeline: List[CommentaryEvent] = []
        self.debug: List[str] = []
        self.kills = 0
        self.rounds = 0
        self.pstats_k = {}
        self.pstats_d = {}
        self.clutch_wins = {}
        self.multikills = []
        self.clutches = []
        self.candidates = 0
        self._rosters = self._prescan_rosters()

    # --- roster pre-pass (membership/counts only; not used for commentary content) ---
    def _prescan_rosters(self):
        rosters = {}
        for e in self.events:
            if e.type != "KILL":
                continue
            r = rosters.setdefault(e.round, {"CT": set(), "T": set()})
            if e.team in ("CT", "T") and e.player:
                r[e.team].add(e.player)
            vt, vic = e.metadata.get("victim_team"), e.metadata.get("victim")
            if vt in ("CT", "T") and vic:
                r[vt].add(vic)
        for rn, sides in rosters.items():
            for side in ("CT", "T"):
                names = set(sides[side])
                i = 0
                while len(names) < 5:
                    names.add(f"_pad_{side}_{i}")
                    i += 1
                sides[side] = names
        return rosters

    def _pick(self, cat, **kw):
        opts = self.tpl.get(cat, ["..."])
        choices = [o for o in opts if o != self._last_tpl.get(cat)] or opts
        t = self.rng.choice(choices)
        self._last_tpl[cat] = t
        return t.format(**kw)

    def _level(self, hype):
        t = self.th
        if hype >= t["l5"]:
            return 5
        if hype >= t["l4"]:
            return 4
        if hype >= t["l3"]:
            return 3
        if hype >= t["l2"]:
            return 2
        if hype >= t["l1"]:
            return 1
        return 0

    def _dbg(self, t, etype, head, reason, hype, action, method_or_reason):
        self.debug.append(
            f"[{_mmss(t)}]\n{etype}\n{head}\n{reason}\nhype={hype}\n"
            f"ACTION: {action}\n{method_or_reason}")

    def _emit(self, ev: CommentaryEvent, interrupt: bool):
        """Apply threshold + cooldown, then append to timeline if it survives."""
        if ev.priority < self.th["comment_min"]:
            self._dbg(ev.demo_time, ev.event_type, f"{ev.player or ''} {ev.reason}",
                      ev.reason, ev.priority, "IGNORE", "REASON: below threshold")
            return False
        if not interrupt and (ev.demo_time - self.last_comment_t) < self.cfg["events"]["cooldown_s"]:
            self._dbg(ev.demo_time, ev.event_type, f"{ev.player or ''} {ev.reason}",
                      ev.reason, ev.priority, "IGNORE", "REASON: cooldown")
            return False
        ev.duration = _dur(ev.text)
        self.last_comment_t = ev.demo_time
        self.timeline.append(ev)
        self._dbg(ev.demo_time, ev.event_type, f"{ev.player or ''} -> {ev.victim or ''}",
                  ev.reason, ev.priority, "COMMENT", f"METHOD: {ev.method}")
        return True

    async def run(self, progress=None):
        n = len(self.events)
        for i, e in enumerate(self.events):
            if e.type == "ROUND_START":
                self._on_round_start(e)
            elif e.type == "KILL":
                await self._on_kill(e)
            elif e.type == "BOMB_PLANT":
                self._on_bomb(e)
            elif e.type == "ROUND_END":
                await self._on_round_end(e)
            if progress and i % 40 == 0:
                progress(int(100 * i / max(1, n)))
        self.timeline.sort(key=lambda c: c.demo_time)
        return self.timeline, self.debug, self.llm_calls, self._stats()

    # ------------------------------------------------------------------ handlers
    def _on_round_start(self, e):
        self.rounds += 1
        self.cur = _Round(e.round)
        roster = self._rosters.get(e.round, {"CT": set(), "T": set()})
        self.cur.alive = {"CT": set(roster["CT"]), "T": set(roster["T"])}
        self.last_comment_t = -999.0  # allow a fresh line at round start
        self.debug.append(f"\n===== ROUND {e.round}  (score CT {self.ct_score} - {self.t_score} T) =====")
        if e.round == 1 or e.round % 6 == 0:
            txt = self._pick("round_start", r=e.round, ct=self.ct_score, t=self.t_score)
            self._emit(CommentaryEvent(e.timestamp, e.round, "ROUND_START", "round_start",
                                       self.sc["round_start"], self._level(self.sc["round_start"]),
                                       txt, "TEMPLATE"), interrupt=True)

    async def _on_kill(self, e):
        self.kills += 1
        r = getattr(self, "cur", None)
        if r is None or r.number != e.round:
            r = _Round(e.round)
            roster = self._rosters.get(e.round, {"CT": set(), "T": set()})
            r.alive = {"CT": set(roster["CT"]), "T": set(roster["T"])}
            self.cur = r
        m = e.metadata
        killer, kside = e.player, e.team
        victim, vside = m.get("victim"), m.get("victim_team")
        self.pstats_k[killer] = self.pstats_k.get(killer, 0) + 1
        if victim:
            self.pstats_d[victim] = self.pstats_d.get(victim, 0) + 1

        alive_before = {"CT": len(r.alive["CT"]), "T": len(r.alive["T"])}
        if vside in ("CT", "T"):
            r.alive[vside].discard(victim)
        alive_after = {"CT": len(r.alive["CT"]), "T": len(r.alive["T"])}

        opening = not r.first_kill_done
        r.first_kill_done = True

        seq = r.kill_seq.setdefault(killer, [])
        prev = seq[-1] if seq else None
        seq.append(e.timestamp)
        nseq = len(seq)
        gap = round(e.timestamp - prev, 2) if prev is not None else None

        # ---- deterministic priority scoring (past+current only) ----
        hype = 0
        reasons = []
        cat = "normal"
        wpn = m.get("weapon")
        if opening:
            hype += self.sc["opening"]; reasons.append("opening kill"); cat = "opening"
        if m.get("headshot"):
            hype += self.sc["headshot"]; reasons.append("headshot")
        if _is_awp(wpn):
            hype += self.sc["awp"]; reasons.append("AWP")
        if (m.get("penetrated") or 0):
            hype += self.sc["wallbang"]; reasons.append("wallbang")
        if m.get("thrusmoke"):
            hype += self.sc["smoke"]; reasons.append("through smoke")
        khp = m.get("attacker_hp")
        if khp is not None and khp <= self.win["low_hp"]:
            hype += self.sc["low_hp"]; reasons.append(f"low HP ({int(khp)})")
        # rapid multi-kill escalation
        if nseq == 2 and gap is not None and gap <= self.win["rapid2_s"]:
            hype += self.sc["rapid2"]; reasons.append(f"rapid 2nd ({gap}s)"); cat = "rapid2"
        elif nseq == 3 and (e.timestamp - seq[0]) <= self.win["rapid3_s"]:
            hype += self.sc["rapid3"]; reasons.append("rapid 3rd"); cat = "rapid3"
        elif nseq == 4 and (e.timestamp - seq[0]) <= self.win["rapid4_s"]:
            hype += self.sc["rapid4"]; reasons.append("rapid 4th"); cat = "rapid4"
        elif nseq >= 5:
            hype += self.sc["ace"]; reasons.append("ACE"); cat = "ace"
        if _is_knife(wpn):
            hype += 8; reasons.append("knife")
        # clutch kill (killer is the active clutcher)
        if r.clutch and r.clutch["player"] == killer:
            hype += self.sc["clutch_kill"]
            r.clutch["kills"] += 1
            if r.clutch.get("hp_start") is None:
                r.clutch["hp_start"] = khp
            reasons.append("clutch kill")
            if cat == "normal":
                cat = "clutch_kill"

        # multi-kill stat
        if nseq >= 3:
            self._track_multikill(e.round, killer, seq)

        # ---- build + emit the kill commentary ----
        interrupt = hype >= self.cfg["events"]["major_interrupt"] or cat in (
            "rapid2", "rapid3", "rapid4", "ace", "clutch_kill")
        enemies_now = alive_after["CT" if kside == "T" else "T"]
        text, method = await self._kill_text(cat, killer, enemies_now, hype, e, m,
                                             alive_before, alive_after, opening, reasons, r)
        self.candidates += 1
        self._emit(CommentaryEvent(e.timestamp, e.round, "KILL", ", ".join(reasons) or "normal kill",
                                   hype, self._level(hype), text, method, player=killer,
                                   victim=victim, facts=reasons), interrupt)

        # ---- detect a NEW clutch situation created by this death (before any clutch kill) ----
        await self._maybe_clutch_situation(r, e)

    async def _kill_text(self, cat, killer, enemies_now, hype, e, m, ab, aa, opening, reasons, r):
        """Simple events use free deterministic templates. Kills NEVER call the LLM
        (credit control); the LLM is reserved for 1v3+ clutch wins in _on_round_end."""
        if cat in ("opening", "rapid2", "rapid3", "rapid4", "ace"):
            return self._pick(cat, p=killer), "TEMPLATE"
        if cat == "clutch_kill":
            return self._pick("clutch_kill", p=killer, n=max(enemies_now, 1)), "TEMPLATE"
        return (self._pick("opening", p=killer) if opening else f"{killer} with the kill."), "TEMPLATE"

    def _llm_payload(self, killer, e, m, ab, aa, reasons, r, enemies_now):
        recent = []
        for p, ts in list(r.kill_seq.items()):
            for t in ts:
                if t < e.timestamp:
                    recent.append(p)
        return {
            "event_type": "kill", "timestamp": e.timestamp, "round": e.round,
            "score": f"{self.ct_score}-{self.t_score}", "player": killer,
            "victim": m.get("victim"), "weapon": m.get("weapon"),
            "headshot": bool(m.get("headshot")), "killer_hp": m.get("attacker_hp"),
            "alive_before": ab, "alive_after": aa,
            "situation": (f"1v{r.clutch['enemies']}" if r.clutch else None),
            "enemies_left": enemies_now, "recent_kills": recent[-3:],
            "commentary_reason": ", ".join(reasons) or "kill",
            "player_prior_clutch_wins": self.clutch_wins.get(killer, 0),
        }

    def _llm_line(self, cat, killer, e, m, ab, aa, reasons, r, enemies_now):
        return None  # (kill-path LLM handled inline in _kill_text)

    async def _maybe_clutch_situation(self, r, e):
        if r.clutch is not None:
            return
        for side in ("CT", "T"):
            enemy = "T" if side == "CT" else "CT"
            if len(r.alive[side]) == 1 and len(r.alive[enemy]) >= 2:
                lone = next(iter(r.alive[side]))
                if lone.startswith("_pad_"):
                    continue
                enemies = len(r.alive[enemy])
                r.clutch = {"player": lone, "side": side, "enemies": enemies,
                            "kills": 0, "hp_start": None}
                pri = self.sc.get(f"clutch_1v{min(enemies,5)}", self.sc["clutch_1v5"])
                self.candidates += 1
                text = (self._pick("clutch_1v2", p=lone) if enemies < 3
                        else f"{lone} all alone now — it's a 1v{enemies}!")
                self._emit(CommentaryEvent(e.timestamp, e.round, "CLUTCH", f"1v{enemies} situation",
                                           pri, self._level(pri), text, "TEMPLATE",
                                           player=lone, facts=[f"1v{enemies}"]), interrupt=True)
                return

    def _on_bomb(self, e):
        r = getattr(self, "cur", None)
        if r:
            r.bomb_planted = True
        pri = self.sc["bomb_plant"]
        if r and r.clutch:
            pri += 10
        self.candidates += 1
        self._emit(CommentaryEvent(e.timestamp, e.round, "BOMB_PLANT", "bomb plant",
                                   pri, self._level(pri), self._pick("bomb_plant"), "TEMPLATE",
                                   facts=["bomb planted"]), interrupt=False)

    async def _on_round_end(self, e):
        winner = e.metadata.get("winner")
        if e.metadata.get("ct_score") is not None:
            self.ct_score = e.metadata["ct_score"]; self.t_score = e.metadata["t_score"]
        elif winner == "CT":
            self.ct_score += 1
        elif winner == "T":
            self.t_score += 1

        r = getattr(self, "cur", None)
        # clutch win?
        if r and r.clutch and r.clutch["side"] == winner and r.clutch["kills"] >= 1:
            cl = r.clutch
            self.clutch_wins[cl["player"]] = self.clutch_wins.get(cl["player"], 0) + 1
            self.clutches.append({"round": e.round, "player": cl["player"],
                                  "clutch": {"starting_situation": f"1v{cl['enemies']}",
                                             "kills": cl["kills"], "hp_start": cl["hp_start"],
                                             "round_won": True}})
            pri = self.sc["clutch_win"] + self.sc.get(f"clutch_1v{min(cl['enemies'],5)}", 0)
            self.candidates += 1
            text, method = self._pick("clutch_win", p=cl["player"]), "TEMPLATE"
            if cl["enemies"] >= self.cfg["events"]["llm_min_enemies"] and self.llm.key:
                payload = {"event_type": "clutch_win", "round": e.round,
                           "score": f"{self.ct_score}-{self.t_score}", "player": cl["player"],
                           "situation": f"1v{cl['enemies']}", "clutch_kills": cl["kills"],
                           "hp_start": cl["hp_start"],
                           "player_prior_clutch_wins": self.clutch_wins.get(cl["player"], 1) - 1}
                self.llm_calls += 1
                res = await self.llm.comment_event(payload)
                if res and res.get("commentary"):
                    text, method = res["commentary"], "LLM"
            self._emit(CommentaryEvent(e.timestamp, e.round, "CLUTCH_WIN", f"1v{cl['enemies']} clutch WON",
                                       pri, self._level(pri), text, method, player=cl["player"],
                                       facts=[f"1v{cl['enemies']}", f"{cl['kills']} clutch kills"]),
                       interrupt=True)
            return

        # short, non-summary round-end line
        cat = "round_end_ct" if winner == "CT" else ("round_end_t" if winner == "T" else "round_end")
        pri = self.sc["round_end"]
        self.candidates += 1
        self._emit(CommentaryEvent(e.timestamp, e.round, "ROUND_END", f"round end ({winner})",
                                   pri, self._level(pri), self._pick(cat), "TEMPLATE",
                                   facts=[f"winner {winner}"]), interrupt=True)

    # ------------------------------------------------------------------ helpers
    def _track_multikill(self, rn, player, seq):
        dur = round(seq[-1] - seq[0], 2)
        for mk in self.multikills:
            if mk["round"] == rn and mk["player"] == player:
                mk["kills"] = len(seq); mk["sequence_duration"] = dur
                return
        self.multikills.append({"round": rn, "player": player, "kills": len(seq),
                                "sequence_duration": dur})

    def _stats(self):
        top = sorted(self.timeline, key=lambda c: c.priority, reverse=True)[:10]
        return {
            "score": {"ct": self.ct_score, "t": self.t_score},
            "total_rounds": self.rounds,
            "total_kills": self.kills,
            "candidates": self.candidates,
            "player_stats": {"kills": self.pstats_k, "deaths": self.pstats_d,
                             "clutches": self.clutch_wins,
                             "multikills": {m["player"]: m["kills"] for m in self.multikills}},
            "clutches": self.clutches,
            "multikills": [m for m in self.multikills if m["kills"] >= 3],
            "top_highlights": [{"player": c.player, "round": c.round, "situation_type": c.reason,
                                "hype_score": c.priority, "hype_level": c.hype_level} for c in top],
        }
