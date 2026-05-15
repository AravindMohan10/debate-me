"""
Mem0 integration layer for DebateMe.

Persists per-user argumentation patterns and session summaries so future
debates can exploit how a specific user argues, not just the opposing stance.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Literal, TypedDict

from dotenv import load_dotenv

# Load .env from the project root (same directory as this module).
_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(_PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

# Pattern taxonomy used when analyzing how a user argues.
PatternType = Literal["weakness", "tendency", "blind_spot", "rhetorical_habit"]
VALID_PATTERN_TYPES: frozenset[str] = frozenset(
    {"weakness", "tendency", "blind_spot", "rhetorical_habit"}
)

# Metadata keys — keep stable so retrieval filters stay reliable.
_KIND_DEBATE_PATTERN = "debate_pattern"
_KIND_SESSION_SUMMARY = "session_summary"

# Strip legacy "(observed Nx on topic: …)" and new "(observed Nx across M sessions)" suffixes.
_OBSERVED_SUFFIX = re.compile(
    r"\s*\(observed\s+\d+x(?:\s+on\s+topic:.*?|\s+across\s+\d+\s+sessions?)\)\s*$",
    re.IGNORECASE,
)


class DebatePattern(TypedDict):
    id: str
    pattern_type: str
    content: str
    created_at: str | None


class MemoryUnavailableError(Exception):
    """Mem0 is missing, misconfigured, or unreachable."""


def _get_api_key() -> str | None:
    return os.getenv("MEM0_API_KEY")


_client = None
_client_init_failed = False


def _get_client():
    """
    Return the Mem0 client, initializing on first use.

    Lazy init ensures keys from .env or the shell are visible even if they
    were not set before this module was imported.
    """
    global _client, _client_init_failed

    if _client is not None:
        return _client
    if _client_init_failed:
        return None

    # Re-read .env in case it was created after import.
    load_dotenv(_PROJECT_ROOT / ".env", override=False)

    api_key = _get_api_key()
    if not api_key:
        logger.warning(
            "MEM0_API_KEY is not set; memory features are disabled. "
            "Add MEM0_API_KEY to .env in the project root or export it in your shell."
        )
        _client_init_failed = True
        return None

    try:
        from mem0 import MemoryClient

        _client = MemoryClient(api_key=api_key)
        return _client
    except Exception as exc:
        logger.error("Failed to initialize Mem0 client: %s", exc)
        _client_init_failed = True
        return None


def _require_client():
    client = _get_client()
    if client is None:
        raise MemoryUnavailableError(
            "Mem0 is not available. Set MEM0_API_KEY in .env or your environment "
            "and ensure the mem0ai package is installed."
        )
    return client


def _mem0_call(operation: str, fn, default: Any):
    """
    Run a Mem0 API call with consistent error handling.

    Logs a clear message and returns `default` instead of crashing the app.
    """
    try:
        client = _require_client()
    except MemoryUnavailableError as exc:
        logger.error("[%s] %s", operation, exc)
        return default

    try:
        return fn(client)
    except MemoryUnavailableError:
        raise
    except Exception as exc:
        logger.error(
            "[%s] Mem0 request failed — %s: %s",
            operation,
            type(exc).__name__,
            exc,
        )
        return default


def _normalize_pattern_type(raw: str | None) -> str | None:
    if raw in VALID_PATTERN_TYPES:
        return raw
    return None


def _base_content(text: str) -> str:
    """Canonical pattern text without observation suffixes."""
    return _OBSERVED_SUFFIX.sub("", text.strip()).strip()


def _normalize_for_match(text: str) -> str:
    return " ".join(_base_content(text).lower().split())


def _contents_match(a: str, b: str) -> bool:
    na, nb = _normalize_for_match(a), _normalize_for_match(b)
    return bool(na) and na == nb


def _parse_counts(metadata: dict[str, Any], memory_text: str) -> tuple[int, int, str]:
    """Return (observation_count, session_count, base_content)."""
    base = _base_content(metadata.get("content") or memory_text)
    obs = metadata.get("observation_count")
    sessions = metadata.get("session_count")

    if obs is None:
        m = re.search(r"observed\s+(\d+)x", memory_text, re.IGNORECASE)
        obs = int(m.group(1)) if m else 1
    if sessions is None:
        m = re.search(r"across\s+(\d+)\s+sessions?", memory_text, re.IGNORECASE)
        sessions = int(m.group(1)) if m else 1

    return int(obs), int(sessions), base


def _format_display(base: str, observations: int, sessions: int) -> str:
    if observations <= 1 and sessions <= 1:
        return base
    session_word = "session" if sessions == 1 else "sessions"
    return f"{base} (observed {observations}x across {sessions} {session_word})"


def _fetch_pattern_records(client, user_id: str) -> list[dict[str, Any]]:
    response = client.get_all(
        filters={"user_id": user_id},
        page=1,
        page_size=200,
    )
    records = response.get("results", []) if isinstance(response, dict) else []
    return [
        r
        for r in records
        if (r.get("metadata") or {}).get("kind") == _KIND_DEBATE_PATTERN
    ]


def _consolidate_records(records: list[dict[str, Any]]) -> list[DebatePattern]:
    """Merge duplicate patterns (same type + base content) into one entry."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}

    for record in records:
        metadata = record.get("metadata") or {}
        pattern_type = _normalize_pattern_type(metadata.get("pattern_type"))
        if not pattern_type:
            continue

        memory_text = record.get("memory", "")
        obs, sessions, base = _parse_counts(metadata, memory_text)
        if not base:
            continue

        key = (pattern_type, _normalize_for_match(base))
        if key not in groups:
            groups[key] = {
                "id": record.get("id", ""),
                "pattern_type": pattern_type,
                "base": base,
                "observation_count": obs,
                "session_count": sessions,
                "created_at": record.get("created_at"),
            }
        else:
            g = groups[key]
            g["observation_count"] += obs
            g["session_count"] += sessions

    return [
        DebatePattern(
            id=g["id"],
            pattern_type=g["pattern_type"],
            content=_format_display(
                g["base"], g["observation_count"], g["session_count"]
            ),
            created_at=g["created_at"],
        )
        for g in groups.values()
    ]


def _memory_to_pattern(record: dict[str, Any]) -> DebatePattern | None:
    """Map a Mem0 memory record to a structured debate pattern."""
    metadata = record.get("metadata") or {}
    if metadata.get("kind") != _KIND_DEBATE_PATTERN:
        return None

    pattern_type = _normalize_pattern_type(metadata.get("pattern_type"))
    memory_text = record.get("memory", "")
    obs, sessions, base = _parse_counts(metadata, memory_text)
    if not pattern_type or not base:
        return None

    return DebatePattern(
        id=record.get("id", ""),
        pattern_type=pattern_type,
        content=_format_display(base, obs, sessions),
        created_at=record.get("created_at"),
    )


def store_debate_pattern(
    user_id: str,
    pattern_type: str,
    content: str,
    observations: int = 1,
) -> dict[str, Any] | None:
    """
    Store an observed argumentation pattern about the user.

    If the same pattern_type + base content already exists, increments the
    observation and session counts instead of creating a duplicate memory.

    Pattern types: weakness, tendency, blind_spot, rhetorical_habit.
    """
    if pattern_type not in VALID_PATTERN_TYPES:
        logger.error(
            "Invalid pattern_type %r; expected one of %s",
            pattern_type,
            ", ".join(sorted(VALID_PATTERN_TYPES)),
        )
        return None

    if not user_id or not content.strip():
        logger.error("store_debate_pattern requires non-empty user_id and content")
        return None

    observations = max(1, observations)
    base = _base_content(content)
    label = pattern_type.replace("_", " ")

    def _store_or_update(client):
        for record in _fetch_pattern_records(client, user_id):
            meta = record.get("metadata") or {}
            existing_type = _normalize_pattern_type(meta.get("pattern_type"))
            if existing_type != pattern_type:
                continue

            _, _, existing_base = _parse_counts(meta, record.get("memory", ""))
            if _contents_match(base, existing_base):
                old_obs, old_sessions, _ = _parse_counts(meta, record.get("memory", ""))
                new_obs = old_obs + observations
                new_sessions = old_sessions + 1
                display = _format_display(base, new_obs, new_sessions)
                return client.update(
                    record["id"],
                    text=f"Debate pattern ({label}): {display}",
                    metadata={
                        "kind": _KIND_DEBATE_PATTERN,
                        "pattern_type": pattern_type,
                        "content": base,
                        "observation_count": new_obs,
                        "session_count": new_sessions,
                    },
                )

        display = _format_display(base, observations, 1)
        return client.add(
            messages=[{"role": "user", "content": f"Debate pattern ({label}): {display}"}],
            user_id=user_id,
            metadata={
                "kind": _KIND_DEBATE_PATTERN,
                "pattern_type": pattern_type,
                "content": base,
                "observation_count": observations,
                "session_count": 1,
            },
            infer=False,
        )

    return _mem0_call("store_debate_pattern", _store_or_update, default=None)


def get_user_patterns(user_id: str) -> list[DebatePattern]:
    """Return all stored debate patterns for a user, with their types."""
    if not user_id:
        logger.error("get_user_patterns requires a non-empty user_id")
        return []

    def _fetch(client):
        return _consolidate_records(_fetch_pattern_records(client, user_id))

    result = _mem0_call("get_user_patterns", _fetch, default=[])
    return result if result is not None else []


def get_relevant_patterns(user_id: str, topic: str) -> list[DebatePattern]:
    """
    Semantic search over stored patterns for those most relevant to `topic`.

    Example: topic="climate policy" surfaces patterns about data-heavy arguments.
    """
    if not user_id or not topic.strip():
        logger.error("get_relevant_patterns requires non-empty user_id and topic")
        return []

    query = (
        f"How does this user argue about topics like: {topic.strip()}? "
        "Include weaknesses, tendencies, blind spots, and rhetorical habits."
    )

    def _search(client):
        response = client.search(
            query=query,
            filters={"user_id": user_id},
            top_k=15,
        )
        records = response.get("results", []) if isinstance(response, dict) else []
        debate_records = [
            r
            for r in records
            if (r.get("metadata") or {}).get("kind") == _KIND_DEBATE_PATTERN
        ]
        if not debate_records:
            debate_records = _fetch_pattern_records(client, user_id)

        return _consolidate_records(debate_records)

    result = _mem0_call("get_relevant_patterns", _search, default=[])
    return result if result is not None else []


def store_session_summary(
    user_id: str,
    topic: str,
    stance: str,
    patterns_observed: list[str],
) -> dict[str, Any] | None:
    """
    Persist a full session summary after a debate ends.

    `patterns_observed` is the list of patterns detected during that session.
    """
    if not user_id or not topic.strip():
        logger.error("store_session_summary requires non-empty user_id and topic")
        return None

    observed = [p.strip() for p in patterns_observed if p and p.strip()]
    bullets = "\n".join(f"- {p}" for p in observed) if observed else "- (none noted)"
    message_content = (
        f"Debate session summary\n"
        f"Topic: {topic.strip()}\n"
        f"User stance: {stance.strip()}\n"
        f"Patterns observed this session:\n{bullets}"
    )

    def _add(client):
        return client.add(
            messages=[{"role": "user", "content": message_content}],
            user_id=user_id,
            metadata={
                "kind": _KIND_SESSION_SUMMARY,
                "topic": topic.strip(),
                "stance": stance.strip(),
                "patterns_observed": observed,
            },
            infer=False,
        )

    return _mem0_call("store_session_summary", _add, default=None)
