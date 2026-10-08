"""Central configuration. Scoring is configurable, never hardcoded permanently."""
import os
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
    "llm": {"provider": "openai", "model": os.environ.get("LLM_MODEL", "gpt-5.6-luna")},
    "events": {
        "scoring": {
            "opening": 20, "headshot": 5, "awp": 5, "wallbang": 8, "smoke": 8,
            "low_hp": 8, "rapid2": 20, "rapid3": 30, "rapid4": 40, "ace": 60,
            "clutch_1v2": 35, "clutch_1v3": 50, "clutch_1v4": 70, "clutch_1v5": 100,
            "clutch_kill": 20, "clutch_win": 40, "bomb_plant": 22, "round_end": 28,
            "round_start": 26, "trade": 4,
        },
        "windows": {"rapid2_s": 4.0, "rapid3_s": 6.0, "rapid4_s": 8.0, "low_hp": 40},
        "thresholds": {"comment_min": 25, "l1": 25, "l2": 40, "l3": 60, "l4": 80, "l5": 100},
        "cooldown_s": 2.5,
        "major_interrupt": 40,
        "llm_min_enemies": 3,   # only clutches of 1v3+ may use the LLM
        "llm_min_hype": 90,     # or any single moment this big
        "round_len_s": 115.0,
        "bomb_timer_s": 40.0,
        "analyst_interval_s": 7.0,      # cadence of analyst checks inside a quiet gap
        "analyst_gap_min_s": 6.0,       # only fill gaps longer than this
        "analyst_buffer_s": 2.5,        # a filler line must finish before the next event
        "analyst_llm_min_gap_s": 16.0,  # min demo-seconds between analyst LLM calls
        "filler_cooldown_s": 10.0,      # min demo-seconds between any analyst/filler lines
        "phase_early_s": 15.0,
        "phase_mid_s": 40.0,
    },
    "templates": {
        "opening": ["{p} draws first blood!", "{p} finds the opener!",
                    "First blood to {p}!", "{p} opens it up!"],
        "rapid2": ["And another! {p}'s got two!", "Quick second for {p}!",
                   "{p} doubles up!", "And he's got two!"],
        "rapid3": ["MAKE IT THREE!", "{p} is on a tear — THREE!", "Three for {p}!"],
        "rapid4": ["FOUR! {p} is unstoppable!", "{p} makes it FOUR!"],
        "ace": ["ACE! {p} takes the whole team!", "AN ACE FOR {p}!"],
        "clutch_1v2": ["{p} left to clutch it — 1v2!", "It's down to {p} — 1v2!"],
        "clutch_kill": ["{p} gets one back — 1v{n}!", "{p} answers! 1v{n} now!",
                        "One down for {p} — 1v{n}!"],
        "clutch_win": ["{p} HAS DONE IT! WHAT A CLUTCH!", "{p} CLUTCHES IT OUT!"],
        "bomb_plant": ["The bomb is DOWN!", "Plant goes down!", "Bomb is planted!"],
        "round_start": ["Round {r}, {ct}-{t}.", "Here we go — round {r}."],
        "round_end_ct": ["Huge hold from the CTs!", "CTs take it.", "And the CTs convert."],
        "round_end_t": ["The Ts take the round.", "Round goes to the T side.", "Ts get it done."],
        "round_end": ["And that's the round.", "Round over."],
        "filler": ["Still plenty of time on the clock.", "Both teams patient here.",
                   "Quiet for a moment.", "Nothing committed just yet."],
        "early_default": ["Both sides settling in.", "Early movement, nothing committed yet.",
                          "A patient start to this one."],
        "adv": ["The {lead} side has the man-advantage now.", "Numbers favour the {lead}s here.",
                "That's bodies on the board for the {lead} side."],
        "time_pressure": ["Clock's becoming a factor now.", "Time ticking away — they need to move.",
                          "Not long left on this one."],
        "post_plant": ["Bomb's down — it's all retake now.", "Now the retake is the story.",
                       "Post-plant, and the pressure flips."],
    },
    "tts": {"provider": "elevenlabs", "voice_id": "xtw8E1CXDMtNKx4sgP7u",
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
