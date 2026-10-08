"""LLM provider abstraction (swappable: OpenAI / Gemini / Claude via Emergent key).
Two-stage system: Stage A Analyst (structured JSON) + Stage B Caster (natural line).
Fails gracefully to deterministic templates so the pipeline never crashes."""
import json
import logging
import os
import re
import uuid

log = logging.getLogger("cs2.llm")


class LLMProvider:
    async def analyze(self, situation: dict) -> dict:  # Stage A
        raise NotImplementedError

    async def cast(self, analyst: dict, situation: dict) -> str:  # Stage B
        raise NotImplementedError


def _fallback_analyst(situation):
    hype = situation["hype_level"]
    return {
        "should_comment": hype >= 1,
        "importance": min(100, situation["hype_score"] * 3),
        "hype_level": hype,
        "situation_type": situation["situation_type"],
        "facts": situation["reasons"],
        "analysis": "Deterministic fallback analysis.",
        "commentary_angle": "describe the play factually",
        "confidence": situation["confidence"].lower(),
    }


def _fallback_cast(situation):
    p = situation["player"]
    n = situation["kills"]
    cl = situation.get("clutch")
    if cl and cl["round_won"]:
        return f"{p} is the last one standing... and HE CLUTCHES IT! A one-versus-{cl['enemies']}!"
    if n >= 5:
        return f"ACE! {p} takes down the entire team!"
    if n == 4:
        return f"{p} is tearing through them — that's FOUR!"
    if n == 3:
        return f"{p} finds a triple! Huge round for {p}."
    if n == 2:
        return f"{p} picks up two quick kills."
    return f"{p} finds the opening."


class EmergentLLMProvider(LLMProvider):
    def __init__(self, cfg):
        self.cfg = cfg
        self.model = cfg["llm"]["model"]
        self.provider = cfg["llm"]["provider"]
        self.key = os.environ.get("EMERGENT_LLM_KEY")
        self.caster = cfg["caster"]

    def _chat(self, system):
        from emergentintegrations.llm.chat import LlmChat
        return LlmChat(api_key=self.key, session_id=f"cs2-{uuid.uuid4()}",
                       system_message=system).with_model(self.provider, self.model)

    @staticmethod
    def _extract_json(text):
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None

    async def analyze(self, situation):
        if not self.key:
            return _fallback_analyst(situation)
        system = (
            "You are a deterministic CS2 esports ANALYST. You receive a structured, "
            "pre-computed game situation. You MUST NOT invent kills, HP, weapons, timings, "
            "positions, score or history. Only interpret the facts given. "
            "Respond with ONLY valid JSON matching: {should_comment:bool, importance:int(0-100), "
            "hype_level:int(0-5), situation_type:str, facts:[str], analysis:str, "
            "commentary_angle:str, confidence:'low'|'medium'|'high'}."
        )
        from emergentintegrations.llm.chat import UserMessage
        try:
            payload = {k: situation[k] for k in (
                "round", "player", "team", "situation_type", "kills", "gaps_s",
                "weapons", "min_hp", "bomb_planted", "round_won", "sequence_duration",
                "hype_score", "hype_level", "reasons", "confidence", "clutch",
                "score_ct", "score_t")}
            payload["memory"] = situation.get("memory", {})
            resp = await self._chat(system).send_message(
                UserMessage(text="SITUATION:\n" + json.dumps(payload, default=str)))
            out = self._extract_json(resp) or _fallback_analyst(situation)
            out.setdefault("hype_level", situation["hype_level"])
            return out
        except Exception as e:  # noqa
            log.warning("analyst LLM failed: %s", e)
            return _fallback_analyst(situation)

    async def cast(self, analyst, situation):
        if not self.key:
            return _fallback_cast(situation)
        c = self.caster
        lvl = analyst.get("hype_level", situation["hype_level"])
        system = (
            f"You are {c['name']}, a professional CS2 esports CASTER. Personality: "
            f"{c['personality']}, vocabulary: {c['vocabulary']}, humor: {c['humor']}, "
            f"profanity: {c['profanity']}. Output ONE natural spoken commentary line only "
            "(no quotes, no stage directions). NEVER invent facts beyond what is given. "
            f"Match the energy to hype_level={lvl} on a 0-5 scale (0 calm/informational, "
            "5 explosive). Keep it concise and broadcastable."
        )
        from emergentintegrations.llm.chat import UserMessage
        try:
            msg = {"analysis": analyst.get("analysis"),
                   "angle": analyst.get("commentary_angle"),
                   "facts": analyst.get("facts", situation["reasons"]),
                   "player": situation["player"], "situation": situation["situation_type"],
                   "hype_level": lvl}
            resp = await self._chat(system).send_message(
                UserMessage(text="Generate the caster line for:\n" + json.dumps(msg, default=str)))
            line = resp.strip().strip('"').split("\n")[0]
            return line or _fallback_cast(situation)
        except Exception as e:  # noqa
            log.warning("caster LLM failed: %s", e)
            return _fallback_cast(situation)

    async def comment_event(self, payload):
        """Tiny, short LLM call for complex live moments. Returns {'commentary','hype'} or None.
        The payload contains ONLY current + past facts — never future events."""
        if not self.key:
            return None
        c = self.caster
        system = (
            f"You are {c['name']}, a LIVE CS2 esports caster. You are given ONE current game "
            "event and you do NOT know the future. Reply with ONLY JSON "
            '{"commentary":"...","hype":0-5}. Commentary = 5-18 words, spoken live, present '
            "tense, ONLY the given facts, no future events, no markdown, no explanation."
        )
        from emergentintegrations.llm.chat import UserMessage
        try:
            resp = await self._chat(system).send_message(
                UserMessage(text=json.dumps(payload, default=str)))
            data = self._extract_json(resp)
            if data and data.get("commentary"):
                return {"commentary": str(data["commentary"]).strip().strip('"'),
                        "hype": int(data.get("hype", 4))}
        except Exception as e:  # noqa
            log.warning("comment_event LLM failed: %s", str(e)[:100])
        return None


def get_llm_provider(cfg):
    return EmergentLLMProvider(cfg)
