# DebateMe
 
**argue. lose. improve.**
 
A CLI debate partner that argues the opposite of whatever position you take — and gets smarter about how *you specifically* argue over multiple sessions.
 
---
 
## What it does
 
DebateMe is not a chatbot. It is an adversarial opponent that studies you.
 
Every session it detects patterns in how you argue — whether you avoid emotional appeals, rely too heavily on data, concede too fast, or repeat the same points. It stores these patterns in Mem0 across sessions. Next time you debate, it already knows your weaknesses before you say a word.
 
```
Before we begin...
 
I remember you.
 
[TENDENCY]  Avoids emotional appeals — argues purely with logic/data (observed 6x across 3 sessions)
[HABIT]     Restates earlier points instead of advancing the argument (observed 3x across 1 session)
 
Your opponent has already read this file.
It will exploit every pattern listed above.
```
 
---
 
## Stack
 
- **Groq** — llama-3.3-70b-versatile for fast, aggressive opponent responses
- **Mem0** — persistent memory layer, stores argumentation patterns across sessions
- **Python** — pure CLI, no frontend
---
 
## Setup
 
### 1. Clone the repo
 
```bash
git clone https://github.com/AravindMohan10/debate-me.git
cd debate-me
```
 
### 2. Install dependencies
 
```bash
pip install mem0ai groq python-dotenv
```
 
### 3. Add your API keys
 
Create a `.env` file in the root:
 
```
GROQ_API_KEY=your_groq_key_here
MEM0_API_KEY=your_mem0_key_here
```
 
Get your keys at:
- Groq: https://console.groq.com
- Mem0: https://app.mem0.ai
### 4. Run
 
```bash
python main.py
```
 
---
 
## How it works
 
### Session flow
 
1. Enter your name, debate topic, and stance
2. If you have debated before, your known patterns are revealed before the first argument
3. Debate — the opponent analyzes each argument and detects patterns in real time
4. On quit, a coach summary is generated and patterns are saved to Mem0
5. Next session, the opponent already knows how you argue
### Pattern detection
 
Four patterns are tracked per turn:
 
| Pattern | What it means |
|---|---|
| Avoiding emotion | Arguing purely with logic and data, no emotional stakes raised |
| Conceding too fast | Hedging or admitting the other side may be right without being pressed |
| Data-only argument | Statistics and citations without a reasoning layer |
| Repeating points | Restating earlier arguments without advancing them |
 
### Memory
 
Mem0 stores patterns across sessions and topics. A pattern observed while debating immigration carries over to a debate about remote work. The opponent builds a model of how you think, not just what you said.
 
---
 
## File map
 
| File | Role |
|---|---|
| `main.py` | CLI loop, display, flow control |
| `debate_engine.py` | Groq calls: opponent response, argument analysis, session lifecycle |
| `memory.py` | Mem0 integration — store and retrieve argumentation patterns |
| `claude.md` | Project context for AI agents working in this repo |
 
---
 
## Built with
 
- [Groq](https://groq.com)
- [Mem0](https://mem0.ai)
- [Entire](https://entire.io) — agent session capture across all commits
---
 
## Notes
 
- Free tier: Mem0 free tier allows 10K memories and 1K retrievals per month — more than enough for personal use
- The opponent is intentionally aggressive. It will not soften its position.
- Patterns accumulate across topics. Debate enough and it will know you better than you know yourself.
