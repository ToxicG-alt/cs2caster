"""Factual match memory. Never invented — derived only from detected data."""
from collections import defaultdict


class MatchMemory:
    def __init__(self, match):
        self.match = match
        self.player_kills = defaultdict(int)
        self.player_deaths = defaultdict(int)
        self.player_clutches = defaultdict(int)
        self.player_multikills = defaultdict(int)
        self.round_history = []

    def ingest(self, match, situations):
        for rnd in match.rounds:
            for k in rnd.kills:
                self.player_kills[k.player] += 1
                v = k.metadata.get("victim")
                if v:
                    self.player_deaths[v] += 1
            self.round_history.append({
                "round": rnd.number, "winner": rnd.winner,
                "kills": len(rnd.kills), "bomb": rnd.bomb_planted,
            })
        for s in situations:
            if s.get("clutch") and s["clutch"]["round_won"]:
                self.player_clutches[s["player"]] += 1
            if s["kills"] >= 3:
                self.player_multikills[s["player"]] += 1

    def context_for(self, situation):
        """Factual narrative context the analyst may use — nothing invented."""
        p = situation["player"]
        prior_clutches = self.player_clutches.get(p, 0)
        # count only clutches strictly before this round
        rnd = situation["round"]
        return {
            "player_total_kills": self.player_kills.get(p, 0),
            "player_total_deaths": self.player_deaths.get(p, 0),
            "player_prior_clutch_wins": prior_clutches,
            "player_prior_multikills": self.player_multikills.get(p, 0),
            "current_round": rnd,
            "score_ct": self.match.ct_score,
            "score_t": self.match.t_score,
        }

    def stats(self):
        return {
            "kills": dict(self.player_kills),
            "deaths": dict(self.player_deaths),
            "clutches": dict(self.player_clutches),
            "multikills": dict(self.player_multikills),
        }
