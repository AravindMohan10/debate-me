"""
main.py — DebateMe CLI entry point.
"""

from __future__ import annotations

import sys
import textwrap
import time

from debate_engine import analyze_argument, end_debate, get_opponent_response, initialize_debate

_DIVIDER = "─" * 60
_THIN = "·" * 60

_PATTERN_LABELS = {
    "avoiding_emotion": "avoiding emotion",
    "conceding_too_fast": "conceding too fast",
    "only_using_data": "data-only argument",
    "repeating_points": "repeating a prior point",
}

_PATTERN_TYPE_LABELS = {
    "weakness": "WEAKNESS",
    "tendency": "TENDENCY",
    "blind_spot": "BLIND SPOT",
    "rhetorical_habit": "HABIT",
}


def _p(text: str = "") -> None:
    print(text)


def _prompt(label: str) -> str:
    return input(f"  {label}: ").strip()


def _wrap(text: str, indent: str = "  ") -> None:
    for line in text.split("\n"):
        if line.strip():
            for wrapped in textwrap.wrap(
                line, width=70, initial_indent=indent, subsequent_indent=indent
            ):
                _p(wrapped)
        else:
            _p()


def _header() -> None:
    _p()
    _p("  D E B A T E   M E")
    _p("  argue. lose. improve.")
    _p()


def _reveal_memory(patterns) -> None:
    _p()
    _p(_DIVIDER)
    _p()
    _p("  Before we begin...")
    _p()
    time.sleep(1.2)

    _p("  I remember you.")
    _p()
    time.sleep(0.8)

    grouped: dict[str, list[str]] = {}
    for p in patterns:
        label = _PATTERN_TYPE_LABELS.get(p["pattern_type"], p["pattern_type"].upper())
        grouped.setdefault(label, []).append(p["content"])

    for label, contents in grouped.items():
        for content in contents:
            _p(f"  [{label}]  {content}")

    _p()
    time.sleep(1.0)

    _p("  Your opponent has already read this file.")
    _p("  It will exploit every pattern listed above.")
    _p()
    _p(_DIVIDER)
    _p()


def _first_session_intro() -> None:
    _p()
    _p("  No prior record found. This is your first session.")
    _p("  Argue well. Patterns accumulate.")
    _p()


def _print_opponent(response: str) -> None:
    _p()
    _p("  OPPONENT")
    _p(_THIN)
    _wrap(response)
    _p()


def _show_turn_hint(detected: dict[str, bool]) -> None:
    active = [_PATTERN_LABELS[k] for k, v in detected.items() if v]
    if active:
        _p(f"  ↳ detected: {', '.join(active)}")


def _print_coach_summary(summary: dict) -> None:
    _p()
    _p(_DIVIDER)
    _p("  POST-SESSION DEBRIEF")
    _p(_DIVIDER)
    _p()
    _p(f"  Topic:  {summary['topic']}")
    _p(f"  Stance: {summary['user_stance']}")
    _p(f"  Turns:  {summary['turns']}")
    _p()

    if summary["patterns_detected"]:
        _p("  Patterns detected this session:")
        for key, count in summary["patterns_detected"].items():
            label = _PATTERN_LABELS.get(key, key.replace("_", " "))
            _p(f"    {label}  ×{count}")
        _p()

    _p("  Coach says:")
    _wrap(summary["coach_summary"])
    _p()


def main() -> None:
    _header()

    user_id = _prompt("Your name")
    if not user_id:
        user_id = "anonymous"

    _p()
    topic = _prompt("Debate topic")
    if not topic:
        _p("  No topic given. Exiting.")
        sys.exit(0)

    _p()
    _p(f'  What is YOUR stance on "{topic}"?')
    stance = _prompt("Your position")
    if not stance:
        _p("  No stance given. Exiting.")
        sys.exit(0)

    _p()
    _p("  Initializing...")

    session = initialize_debate(topic, stance, user_id)

    if session["patterns"]:
        _reveal_memory(session["patterns"])
    else:
        _first_session_intro()

    _p("  Type your argument and press Enter.")
    _p("  Type 'quit' to end the debate.")
    _p()
    _p(_DIVIDER)
    _p()

    while True:
        try:
            user_input = input("  YOU: ").strip()
        except (EOFError, KeyboardInterrupt):
            _p()
            _p("  [interrupted]")
            break

        if not user_input:
            continue

        if user_input.lower() in {"quit", "exit", "q"}:
            break

        detected = analyze_argument(session, user_input)
        response = get_opponent_response(session, user_input)

        _print_opponent(response)
        _show_turn_hint(detected)
        _p()

    turn_count = sum(1 for m in session["history"] if m["role"] == "user")
    if turn_count == 0:
        _p()
        _p("  No arguments made. Session not saved.")
        _p()
        return

    _p()
    _p("  Generating debrief...")
    summary = end_debate(session, user_id)

    _print_coach_summary(summary)

    _p(_DIVIDER)
    _p(f"  Patterns saved for next session, {user_id}.")
    _p("  It will remember.")
    _p(_DIVIDER)
    _p()


if __name__ == "__main__":
    main()
