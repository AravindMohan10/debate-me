"""
Debate engine — opponent responses, argument analysis, session lifecycle.

Typical call order per turn:
    patterns  = analyze_argument(session, user_arg)   # before or after opponent
    response  = get_opponent_response(session, user_arg)

End of session:
    summary   = end_debate(session, user_id)
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from groq import Groq

from memory import (
    DebatePattern,
    get_relevant_patterns,
    store_debate_pattern,
    store_session_summary,
)

_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(_PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

_MODEL = "llama-3.3-70b-versatile"
_groq_client: Groq | None = None


def _get_groq() -> Groq:
    global _groq_client
    if _groq_client is None:
        load_dotenv(_PROJECT_ROOT / ".env", override=False)
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to .env or export it in your shell."
            )
        _groq_client = Groq(api_key=api_key)
    return _groq_client


# ---------------------------------------------------------------------------
# System prompt construction
# ---------------------------------------------------------------------------

def _build_system_prompt(
    topic: str, user_stance: str, patterns: list[DebatePattern]
) -> str:
    prompt = (
        f'You are a sharp, aggressive debate opponent on the topic: "{topic}".\n'
        f'You ALWAYS argue the OPPOSITE of "{user_stance}". '
        f"Never agree with the user. Never soften your position.\n"
        f"Be direct, use concrete evidence, and attack the weakest points in "
        f"the user's argument. Keep responses to 2–4 sentences unless the "
        f"argument demands more depth.\n"
    )

    if patterns:
        grouped: dict[str, list[str]] = {}
        for p in patterns:
            grouped.setdefault(p["pattern_type"], []).append(p["content"])

        lines = []
        for ptype, contents in grouped.items():
            label = ptype.replace("_", " ").title()
            for c in contents:
                lines.append(f"  [{label}] {c}")

        prompt += (
            "\nYou have studied how this specific user argues. "
            "Exploit these known patterns ruthlessly:\n"
            + "\n".join(lines)
            + "\n\nStrategic guidance: if they avoid emotion, raise the human stakes. "
            "If they over-rely on data, challenge the methodology. "
            "If they repeat themselves, call it out directly."
        )

    return prompt


# ---------------------------------------------------------------------------
# Session structure (plain dict):
# {
#   "topic":              str,
#   "user_stance":        str,
#   "history":            list[{"role": str, "content": str}],
#   "patterns":           list[DebatePattern],   # loaded from memory at start
#   "detected_patterns":  list[dict],            # accumulated this session
#   "system_prompt":      str,
# }
# ---------------------------------------------------------------------------


def initialize_debate(
    topic: str, user_stance: str, user_id: str
) -> dict[str, Any]:
    """
    Pull existing patterns for this user and return a fresh session object.

    The system prompt is personalised: if memory holds prior weaknesses the
    opponent will know to target them from the first exchange.
    """
    patterns = get_relevant_patterns(user_id, topic)
    system_prompt = _build_system_prompt(topic, user_stance, patterns)

    return {
        "topic": topic,
        "user_stance": user_stance,
        "history": [],
        "patterns": patterns,
        "detected_patterns": [],
        "system_prompt": system_prompt,
    }


# ---------------------------------------------------------------------------
# Opponent response
# ---------------------------------------------------------------------------

def get_opponent_response(session: dict[str, Any], user_argument: str) -> str:
    """
    Append the user's argument to history, get the opponent's reply from Groq,
    append that too, and return it as a string.
    """
    client = _get_groq()

    session["history"].append({"role": "user", "content": user_argument})

    messages = [{"role": "system", "content": session["system_prompt"]}] + session["history"]

    completion = client.chat.completions.create(
        model=_MODEL,
        messages=messages,
        temperature=0.8,
        max_tokens=512,
    )

    opponent_text = completion.choices[0].message.content.strip()
    session["history"].append({"role": "assistant", "content": opponent_text})

    return opponent_text


# ---------------------------------------------------------------------------
# Argument analysis
# ---------------------------------------------------------------------------

_ANALYSIS_SYSTEM = """\
You are an expert debate coach. Analyse the debater's single argument and detect \
these four patterns. Return ONLY a JSON object — no prose, no markdown.

Keys and what makes each true:
  "avoiding_emotion"   — argument relies solely on logic or data; no emotional \
appeal, no stakes raised
  "conceding_too_fast" — debater hedges, qualifies unnecessarily, or admits the \
opposing side may be right without being pressed
  "only_using_data"    — argument consists almost entirely of statistics or cited \
facts, no reasoning layer
  "repeating_points"   — argument restates a point already made earlier in this \
debate without adding new substance

Be strict: only set true when the pattern is clearly present."""


def analyze_argument(
    session: dict[str, Any], user_argument: str
) -> dict[str, bool]:
    """
    Detect argumentation patterns in a single user turn.

    Returns a dict with boolean flags for each pattern. Positive findings are
    accumulated in session["detected_patterns"] for end-of-session storage.

    Can be called before or after get_opponent_response — history ordering
    does not affect analysis correctness.
    """
    client = _get_groq()

    # Build prior-turn context for repetition detection — use only the user's
    # prior arguments, excluding the current one to avoid false repetition flags.
    prior_user_turns = [
        m["content"]
        for m in session["history"]
        if m["role"] == "user" and m["content"] != user_argument
    ]

    if prior_user_turns:
        prior_block = "\n---\n".join(prior_user_turns)
        user_msg = (
            f"[User's prior arguments in this debate]\n{prior_block}\n\n"
            f"[Argument to analyse now]\n{user_argument}"
        )
    else:
        user_msg = f"[Argument to analyse (first turn)]\n{user_argument}"

    completion = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": _ANALYSIS_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
        max_tokens=128,
    )

    raw = completion.choices[0].message.content.strip()

    try:
        result: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[^}]+\}", raw, re.DOTALL)
        try:
            result = json.loads(match.group()) if match else {}
        except json.JSONDecodeError:
            logger.warning("analyze_argument: could not parse Groq JSON response: %r", raw)
            result = {}

    detected = {
        "avoiding_emotion": bool(result.get("avoiding_emotion", False)),
        "conceding_too_fast": bool(result.get("conceding_too_fast", False)),
        "only_using_data": bool(result.get("only_using_data", False)),
        "repeating_points": bool(result.get("repeating_points", False)),
    }

    active = {k: v for k, v in detected.items() if v}
    if active:
        turn_number = sum(1 for m in session["history"] if m["role"] == "user")
        session["detected_patterns"].append({
            "turn": turn_number,
            "snippet": user_argument[:120],
            "patterns": active,
        })

    return detected


# ---------------------------------------------------------------------------
# End of session
# ---------------------------------------------------------------------------

_SUMMARY_SYSTEM = """\
You are a debate coach writing a post-session analysis. Given the full transcript \
and the debater's stance, write a concise critique (under 150 words) covering:
1. Overall argument quality
2. Recurring weaknesses
3. One concrete thing to improve next time
Be direct and specific — no filler."""

# Maps detect-key → (memory pattern_type, human-readable content)
_PATTERN_LABELS: dict[str, tuple[str, str]] = {
    "avoiding_emotion": (
        "tendency",
        "Avoids emotional appeals — argues purely with logic/data",
    ),
    "conceding_too_fast": (
        "weakness",
        "Concedes ground or hedges prematurely before being pressed",
    ),
    "only_using_data": (
        "tendency",
        "Over-relies on statistics and citations without a reasoning layer",
    ),
    "repeating_points": (
        "rhetorical_habit",
        "Restates earlier points instead of advancing the argument",
    ),
}


def end_debate(session: dict[str, Any], user_id: str) -> dict[str, Any]:
    """
    Generate a coach summary, persist patterns and session summary to memory,
    and return a structured summary dict.
    """
    client = _get_groq()

    # --- Coach summary via Groq ---
    if session["history"]:
        transcript = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in session["history"]
        )
        summary_prompt = (
            f"Topic: {session['topic']}\n"
            f"User stance: {session['user_stance']}\n\n"
            f"Transcript:\n{transcript}"
        )
        completion = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _SUMMARY_SYSTEM},
                {"role": "user", "content": summary_prompt},
            ],
            temperature=0.4,
            max_tokens=256,
        )
        coach_summary = completion.choices[0].message.content.strip()
    else:
        coach_summary = "No arguments were exchanged this session."

    # --- Aggregate pattern counts across all turns ---
    pattern_counts: dict[str, int] = {}
    for entry in session["detected_patterns"]:
        for pname in entry["patterns"]:
            pattern_counts[pname] = pattern_counts.get(pname, 0) + 1

    # --- Persist each observed pattern to memory ---
    patterns_observed_text: list[str] = []
    for key, count in pattern_counts.items():
        if key not in _PATTERN_LABELS:
            continue
        ptype, base_content = _PATTERN_LABELS[key]
        full_content = (
            f"{base_content} "
            f"(observed {count}x on topic: {session['topic']})"
        )
        store_debate_pattern(user_id, ptype, full_content)
        patterns_observed_text.append(full_content)

    # --- Persist session summary ---
    store_session_summary(
        user_id=user_id,
        topic=session["topic"],
        stance=session["user_stance"],
        patterns_observed=patterns_observed_text,
    )

    return {
        "topic": session["topic"],
        "user_stance": session["user_stance"],
        "turns": sum(1 for m in session["history"] if m["role"] == "user"),
        "patterns_detected": pattern_counts,
        "coach_summary": coach_summary,
    }
