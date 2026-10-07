"""Central configuration. Scoring is configurable, never hardcoded permanently."""
from copy import deepcopy

DEFAULT_CONFIG = {
    "tickrate": 64,  # CS2 GOTV demos are typically 64 tick
    "scoring": {
        "normal_kill": 1,
        "opening_kill": 3,
        "low_hp_kill": 3,          # attacker survives a kill at low HP
        "double_rapid": 5,         # 2 kills in rapid succession
        "triple": 8,               # 3K
        "quad": 12,                # 4K
        "ace": 20,                 # 5K
        "clutch_1v2": 12,
        "clutch_1v3": 18,
        "clutch_1v4": 25,
        "clutch_1v5": 35,
        "fast_awp_multi": 5,
        "knife_kill": 8,
        "very_low_hp_survival": 4,
        "round_winning_kill": 3,
        "bomb_critical_kill": 3,
        "huge_disadvantage": 5,
    },
    "timing": {
        "fast_double_s": 2.0,       # <= => fast double
        "fast_triple_s": 4.0,       # 3 kills within this window
        "rapid_multi_s": 1.5,       # between consecutive kills
        "extremely_fast_s": 1.1,    # mechanical sequence threshold
        "low_hp_threshold": 40,
        "very_low_hp_threshold": 20,
    },
    "clustering": {
        "window_s": 6.0,            # events within this window merge into one situation
    },
    "hype_thresholds": {            # map highlight score -> hype level
        "level_1": 1,
        "level_2": 6,
        "level_3": 12,
        "level_4": 20,
        "level_5": 30,
    },
    "commentary": {
        "min_interval_s": 4.0,      # minimum gap between spoken lines
        "max_situations": 14,       # cap LLM/TTS calls per match for cost control
        "comment_min_hype": 1,
    },
    "caster": {
        "name": "Vox",
        "personality": "energetic",
        "hype": "high",
        "vocabulary": "professional",
        "humor": "low",
        "analysis_depth": "medium",
        "profanity": False,
    },
    "llm": {"provider": "openai", "model": "gpt-5.4"},
    "tts": {"provider": "elevenlabs", "voice_id": "JBFqnCBsd6RMkjVDRZzb",
            "model_id": "eleven_multilingual_v2",
            "openai_voice": "onyx", "openai_model": "tts-1-hd"},
}


def get_config(overrides=None):
    cfg = deepcopy(DEFAULT_CONFIG)
    if overrides:
        for k, v in overrides.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def hype_level_from_score(score, cfg):
    t = cfg["hype_thresholds"]
    if score >= t["level_5"]:
        return 5
    if score >= t["level_4"]:
        return 4
    if score >= t["level_3"]:
        return 3
    if score >= t["level_2"]:
        return 2
    if score >= t["level_1"]:
        return 1
    return 0
