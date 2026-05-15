# DebateMe — Project Context

## What this is
A CLI debate app that argues the opposite of whatever position you take,
and gets smarter about how *you specifically* argue over multiple sessions.

## Stack
- Groq API — llama-3.3-70b-versatile
- Mem0 — persistent memory across sessions
- Python CLI
- python-dotenv

## What's built
- `memory.py` — Mem0 integration, fully working
  - store_debate_pattern(user_id, pattern_type, content)
  - get_user_patterns(user_id)
  - get_relevant_patterns(user_id, topic)
  - store_session_summary(user_id, topic, stance, patterns_observed)

## Rules for all agents
- Never touch memory.py unless explicitly asked
- Use GROQ_API_KEY and MEM0_API_KEY from .env
- No frontend — pure CLI