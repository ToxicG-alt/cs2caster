"""Data source abstraction. THIS is the only layer that changes when we later
swap a finished demo for a live/delayed GOTV feed."""
import logging
import random
from abc import ABC, abstractmethod
from typing import List

from .models import GameEvent, MatchInfo

log = logging.getLogger("cs2.datasource")


def _sid(v):
    """Normalize a steamid (pandas may give int/float/str) to a stable string."""
    try:
        return str(int(v))
    except (TypeError, ValueError):
        return str(v)


class GameDataSource(ABC):
    """Analysis/commentary/TTS/broadcast must NOT care where data came from."""

    @abstractmethod
    def get_match_info(self) -> MatchInfo: ...

    @abstractmethod
    def get_events(self) -> List[GameEvent]: ...

    def describe(self) -> str:
        return self.__class__.__name__


# --------------------------------------------------------------------------- #
# DemoDataSource — completed .dem via demoparser2 (built first, per spec)
# --------------------------------------------------------------------------- #
class DemoDataSource(GameDataSource):
    def __init__(self, path: str, tickrate: int = 64):
        self.path = path
        self.tickrate = tickrate
        self._info = None
        self._events = None

    def _t(self, tick, start_tick):
        return round(max(0, (tick - start_tick)) / self.tickrate, 2)

    def _load(self):
        from demoparser2 import DemoParser
        parser = DemoParser(self.path)
        header = {}
        try:
            header = parser.parse_header()
        except Exception as e:  # noqa
            log.warning("parse_header failed: %s", e)
        map_name = header.get("map_name", "unknown")

        want = ["round_start", "round_end", "player_death",
                "bomb_planted", "bomb_defused", "bomb_exploded"]
        parsed = {}
        try:
            for name, df in parser.parse_events(want):
                parsed[name] = df
        except Exception as e:  # noqa
            log.warning("parse_events failed: %s", e)

        start_tick = 0
        rs = parsed.get("round_start")
        if rs is not None and len(rs):
            try:
                start_tick = int(rs.sort_values("tick")["tick"].iloc[0])
            except Exception:
                start_tick = 0

        # Collect kill ticks so we can look up HP/team at those exact moments.
        deaths = parsed.get("player_death")
        kill_ticks = []
        if deaths is not None and len(deaths):
            kill_ticks = sorted({int(t) for t in deaths["tick"].tolist()})

        tick_state = {}  # (tick, steamid) -> {hp, armor, team}
        if kill_ticks:
            try:
                tdf = parser.parse_ticks(
                    ["health", "armor_value", "team_num", "team_name"],
                    ticks=kill_ticks,
                )
                for row in tdf.to_dict("records"):
                    tick_state[(int(row["tick"]), _sid(row.get("steamid")))] = {
                        "hp": row.get("health"),
                        "armor": row.get("armor_value"),
                        "team_num": row.get("team_num"),
                    }
            except Exception as e:  # noqa
                log.warning("parse_ticks failed: %s", e)

        def side(team_num):
            return "T" if team_num == 2 else ("CT" if team_num == 3 else None)

        # Build ordered round boundaries
        rounds = []  # list of (round_no, start_tick, end_tick, winner_side, reason)
        if rs is not None and len(rs):
            st = sorted(int(t) for t in rs["tick"].tolist())
            re = parsed.get("round_end")
            re_rows = []
            if re is not None and len(re):
                for r in re.sort_values("tick").to_dict("records"):
                    re_rows.append(r)
            for i, s in enumerate(st):
                nxt = st[i + 1] if i + 1 < len(st) else 10**12
                winner, reason, etick = None, None, nxt
                for r in re_rows:
                    if s <= int(r["tick"]) < nxt:
                        winner = side(r.get("winner"))
                        reason = r.get("reason")
                        etick = int(r["tick"])
                        break
                rounds.append((i + 1, s, etick, winner, reason))
        if not rounds:
            rounds = [(1, start_tick, 10**12, None, None)]

        def round_of(tick):
            for rn, s, e, w, rsn in rounds:
                if s <= tick <= e + self.tickrate * 10:
                    return rn
            return rounds[-1][0]

        events: List[GameEvent] = []
        players = set()

        # Round start/end events
        for rn, s, e, w, rsn in rounds:
            events.append(GameEvent("ROUND_START", self._t(s, start_tick), s, rn))
            if e < 10**11:
                events.append(GameEvent("ROUND_END", self._t(e, start_tick), e, rn,
                                        metadata={"winner": w, "reason": rsn}))

        # Kills
        if deaths is not None and len(deaths):
            for r in deaths.sort_values("tick").to_dict("records"):
                tick = int(r["tick"])
                rn = round_of(tick)
                atk = r.get("attacker_name")
                vic = r.get("user_name")
                atk_id = _sid(r.get("attacker_steamid"))
                vic_id = _sid(r.get("user_steamid"))
                if atk:
                    players.add(atk)
                if vic:
                    players.add(vic)
                atk_state = tick_state.get((tick, atk_id), {})
                vic_state = tick_state.get((tick, vic_id), {})
                atk_side = side(atk_state.get("team_num"))
                events.append(GameEvent(
                    "KILL", self._t(tick, start_tick), tick, rn,
                    player=atk, team=atk_side,
                    metadata={
                        "victim": vic,
                        "victim_team": side(vic_state.get("team_num")),
                        "weapon": r.get("weapon"),
                        "headshot": bool(r.get("headshot")),
                        "attacker_hp": atk_state.get("hp"),
                        "assister": r.get("assister_name"),
                        "noscope": bool(r.get("noscope")) if "noscope" in r else False,
                        "penetrated": r.get("penetrated") if "penetrated" in r else 0,
                        "thrusmoke": bool(r.get("thrusmoke")) if "thrusmoke" in r else False,
                    },
                ))

        # Bomb events
        for ev_name, etype in (("bomb_planted", "BOMB_PLANT"),
                               ("bomb_defused", "BOMB_DEFUSE"),
                               ("bomb_exploded", "BOMB_EXPLODE")):
            df = parsed.get(ev_name)
            if df is not None and len(df):
                for r in df.to_dict("records"):
                    tick = int(r["tick"])
                    events.append(GameEvent(etype, self._t(tick, start_tick), tick,
                                            round_of(tick), player=r.get("user_name")))

        events.sort(key=lambda e: (e.tick, 0 if e.type == "ROUND_START" else 1))
        self._events = events
        self._info = MatchInfo(map=map_name, players=sorted(p for p in players if p),
                               tickrate=self.tickrate)
        log.info("Demo parsed: map=%s rounds=%d events=%d players=%d",
                 map_name, len(rounds), len(events), len(self._info.players))

    def get_match_info(self) -> MatchInfo:
        if self._info is None:
            self._load()
        return self._info

    def get_events(self) -> List[GameEvent]:
        if self._events is None:
            self._load()
        return self._events


# --------------------------------------------------------------------------- #
# SyntheticDataSource — deterministic sample match so the full pipeline is
# testable end-to-end without a real .dem. Produces a varied, realistic match.
# --------------------------------------------------------------------------- #
class SyntheticDataSource(GameDataSource):
    def __init__(self, seed: int = 7, tickrate: int = 64):
        self.tickrate = tickrate
        self.rng = random.Random(seed)
        self._info = None
        self._events = None

    def get_match_info(self) -> MatchInfo:
        if self._info is None:
            self._build()
        return self._info

    def get_events(self) -> List[GameEvent]:
        if self._events is None:
            self._build()
        return self._events

    def _build(self):
        ct = ["Astra", "Nyx", "Quill", "Rhea", "Sol"]
        t = ["Blaze", "Corvus", "Drift", "Echo", "Frost"]
        players = ct + t
        self._info = MatchInfo(map="de_nuke", team_ct="Team Vanguard", team_t="Team Apex",
                               players=players, tickrate=self.tickrate)
        events: List[GameEvent] = []
        tick = 2000
        secs = lambda s: int(s * self.tickrate)

        def team_of(p):
            return "CT" if p in ct else "T"

        # Pre-scripted round templates: (winner, list of (gap_s, attacker, victim, weapon, hp, headshot))
        scripted = [
            ("CT", [(2, "Astra", "Blaze", "AK-47", 100, True), (6, "Nyx", "Corvus", "M4A1", 90, False),
                    (4, "Quill", "Drift", "AWP", 100, True)]),
            ("T", [(3, "Blaze", "Astra", "AK-47", 80, True), (2, "Blaze", "Nyx", "AK-47", 60, True),
                   (1.1, "Blaze", "Quill", "AK-47", 55, False)]),  # fast triple
            ("CT", [(1, "Sol", "Echo", "AWP", 100, False)]),  # opening only, low activity
            ("T", [(5, "Corvus", "Rhea", "Desert Eagle", 100, True)]),
            # The showcase 1v3 clutch round (Rhea, CT, last alive at 24 HP):
            ("CT", [(2, "Rhea", "Blaze", "AWP", 100, True),
                    (3, "Drift", "Astra", "AK-47", 100, True),
                    (2, "Rhea", "Corvus", "AWP", 100, False),
                    (2, "Echo", "Nyx", "AK-47", 100, False),
                    (2, "Frost", "Quill", "AK-47", 100, True),
                    (2, "Drift", "Sol", "AK-47", 100, False),  # Rhea now last alive vs 3
                    (3.0, "Rhea", "Drift", "AWP", 24, True),    # clutch kill 1 (24 HP)
                    (1.3, "Rhea", "Echo", "AWP", 24, False),    # clutch kill 2
                    (1.1, "Rhea", "Frost", "AWP", 24, True)],   # clutch kill 3 -> 1v3 WON
             ),
            ("T", [(4, "Echo", "Sol", "AK-47", 100, False), (8, "Frost", "Astra", "AK-47", 70, False)]),
            ("CT", [(2, "Quill", "Blaze", "Knife", 100, False)]),  # knife kill
            ("T", [(3, "Drift", "Astra", "AK-47", 100, True), (2.5, "Drift", "Quill", "AK-47", 40, True),
                   (2.0, "Drift", "Nyx", "AK-47", 30, False), (2.2, "Drift", "Sol", "AK-47", 18, True)]),  # 4K
        ]

        ct_score = 0
        t_score = 0
        for rn, (winner, kills) in enumerate(scripted, start=1):
            events.append(GameEvent("ROUND_START", round(tick / self.tickrate, 2), tick, rn))
            # bomb plant mid-round on some rounds
            if rn in (2, 5, 8):
                pt = tick + secs(20)
                events.append(GameEvent("BOMB_PLANT", round(pt / self.tickrate, 2), pt, rn,
                                        player="Blaze", team="T"))
            ktick = tick + secs(8)
            for gap, atk, vic, wpn, hp, hs in kills:
                ktick += secs(gap)
                events.append(GameEvent(
                    "KILL", round(ktick / self.tickrate, 2), ktick, rn,
                    player=atk, team=team_of(atk),
                    metadata={"victim": vic, "victim_team": team_of(vic), "weapon": wpn,
                              "headshot": hs, "attacker_hp": hp, "assister": None, "noscope": False},
                ))
            etick = ktick + secs(3)
            if winner == "CT":
                ct_score += 1
            else:
                t_score += 1
            events.append(GameEvent("ROUND_END", round(etick / self.tickrate, 2), etick, rn,
                                    metadata={"winner": winner, "reason": 1,
                                              "ct_score": ct_score, "t_score": t_score}))
            tick = etick + secs(15)

        events.sort(key=lambda e: (e.tick, 0 if e.type == "ROUND_START" else 1))
        self._events = events
