<<<<<<< HEAD
# AI-First HCP CRM — Log Interaction Screen

An AI-first Log Interaction screen for a pharmaceutical CRM's Healthcare Professional (HCP)
module. Field reps can log a visit either through a **structured form** or by talking to an
**AI agent in a chat interface** — both paths write to the same database and go through the
same LLM-powered extraction logic.

Built for the Round 1 technical assignment: React + Redux frontend, FastAPI backend,
a LangGraph agent with 5 tools, and Groq (`gemma2-9b-it`, fallback `llama-3.3-70b-versatile`)
as the LLM.

---

## What this project understood the task to be

A CRM's "Log Interaction" screen is normally just a form. Making it **AI-first** means the
form is optional: a rep can instead just talk naturally ("logged a visit with Dr. Rao, she
was excited about the new trial data, gave her 2 samples") and an agent should:

1. figure out *what the rep is trying to do* (log something? edit something? look someone up?
   schedule a follow-up? report a safety issue?),
2. call the right backend action itself,
3. use an LLM to turn messy free text into clean structured data (topics, sentiment, samples),
4. reply in plain language confirming what it did.

That "decide intent → call the right tool → use the LLM inside the tool → summarize back"
loop is exactly what LangGraph is for, so the agent is modeled as a small graph rather than
a single prompt.

---

## Architecture

```
frontend (React + Redux)  <--REST-->  backend (FastAPI)  <--tool calls-->  LangGraph agent
                                              |                                    |
                                              v                                    v
                                        PostgreSQL                          Groq LLM API
```

### LangGraph agent

```
        START
          |
   classify_intent   <-- LLM decides: chit_chat vs tool_call (+ which tool + args)
      /        \
tool_call    chit_chat
    |             |
 agent_node   direct_reply_node
 (runs tool,   (conversational
  LLM phrases   reply, no DB
  reply)        side effects)
    \             /
        END
```

This is a genuine two-branch graph, not a single monolithic loop: a routing node decides
whether the message needs a real CRM action or is just conversation, so "hi, what can you
do?" doesn't accidentally create a database row.

### The 5 LangGraph tools (`backend/app/agent/tools.py`)

| Tool | Purpose | LLM used for |
|---|---|---|
| **`log_interaction_tool`** | Logs a new HCP interaction from free text | Summarization, topic/drug extraction, sentiment scoring, sample detection |
| **`edit_interaction_tool`** | Modifies a previously logged interaction from a natural-language instruction (e.g. *"change sentiment to negative"*) | Diffing the instruction against the current record to produce a minimal patch; also snapshots the prior version into `edit_history` |
| **`fetch_hcp_profile_tool`** | Retrieves an HCP's profile + last 5 interactions, so a rep has context before a visit | — (pure DB lookup, used to ground the agent's replies) |
| **`schedule_followup_tool`** | Creates a follow-up task tied to an HCP (and optionally a specific past interaction) | — |
| **`flag_adverse_event_tool`** | Detects and files an adverse event (AE) report — a pharmacovigilance/regulatory safety net for any patient side-effect mentioned during a conversation | Extracts the implicated drug name and severity from the description |

Both `log_interaction_tool` and `edit_interaction_tool` are wired into **both** the chat agent
and the structured form's backend routes, so typing into the form and typing into the chat
produce identically-shaped database records — the form is just a faster, no-LLM-round-trip
path for reps who already know exactly what they want to record.

### Why Groq + `gemma2-9b-it`

`gemma2-9b-it` is fast and cheap, which matters for a screen a rep uses dozens of times a day —
extraction and routing calls need to feel instant. `llama-3.3-70b-versatile` is used as an
automatic fallback if a `gemma2-9b-it` call fails (see `backend/app/agent/llm.py`), and could be
swapped in as the primary model for harder reasoning if extraction accuracy became an issue.

---

## Tech stack

- **Frontend:** React (CRA), Redux Toolkit, Axios, Google Inter
- **Backend:** FastAPI, SQLAlchemy
- **AI:** LangGraph, Groq (`gemma2-9b-it` / `llama-3.3-70b-versatile`)
- **Database:** PostgreSQL

---

## Project structure

```
hcp-crm/
├── backend/
│   ├── app/
│   │   ├── agent/
│   │   │   ├── llm.py        # Groq client wrapper (+ fallback model logic)
│   │   │   ├── tools.py      # the 5 LangGraph tools
│   │   │   └── graph.py      # the LangGraph StateGraph (routing + execution)
│   │   ├── db/session.py     # SQLAlchemy engine/session
│   │   ├── models/models.py  # HCP, Interaction, FollowUp, AdverseEvent tables
│   │   ├── schemas/schemas.py# Pydantic request/response models
│   │   ├── routers/          # hcps, interactions, chat, followups, adverse_events
│   │   ├── config.py
│   │   └── main.py           # FastAPI app + CORS + router registration
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── api/client.js          # Axios instance
    │   ├── redux/
    │   │   ├── store.js
    │   │   └── slices/            # hcpsSlice, interactionsSlice, chatSlice
    │   ├── components/
    │   │   ├── Header.js / Sidebar.js
    │   │   ├── LogInteractionScreen.js  # chat/form mode toggle
    │   │   ├── ChatInterface.js         # talks to /api/chat
    │   │   ├── StructuredForm.js        # talks to /api/interactions
    │   │   └── InteractionHistory.js    # list + inline natural-language edit
    │   ├── styles/                # design tokens (color/type/spacing)
    │   ├── App.js
    │   └── index.js
    ├── package.json
    └── .env.example
```

---

## How to run it

### 1. Database

Create a Postgres database:

```bash
createdb hcp_crm
# or, inside psql:
# CREATE DATABASE hcp_crm;
```

Tables are created automatically on backend startup (`Base.metadata.create_all`) — no
migration step needed.

### 2. Backend

**macOS / Linux:**
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env:
#   GROQ_API_KEY=<your key from console.groq.com>
#   DATABASE_URL=postgresql://<user>:<password>@localhost:5432/hcp_crm

uvicorn app.main:app --reload --port 8000
```

**Windows (PowerShell):**
```powershell
cd backend
python -m venv venv

# If activation is blocked by execution policy, run this once first:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
# then edit .env in a text editor:
#   GROQ_API_KEY=<your key from console.groq.com>
#   DATABASE_URL=postgresql://<user>:<password>@localhost:5432/hcp_crm

uvicorn app.main:app --reload --port 8000
```

**Windows (Command Prompt):** same as above, but activate with `venv\Scripts\activate.bat` instead.

Visit `http://localhost:8000/docs` for the interactive OpenAPI docs.

### 3. Frontend

```bash
cd frontend
npm install
```

**macOS / Linux:**
```bash
cp .env.example .env
```

**Windows:**
```powershell
copy .env.example .env
```

Then edit `.env` so it contains:
```
REACT_APP_API_BASE_URL=http://localhost:8000
```

```bash
npm start
```

Visit `http://localhost:3000`.

### 4. Try it

- Pick or add an HCP in the sidebar (optional — you can also just say their name in chat).
- In **Chat with agent** mode, try one of the suggested prompts, e.g.:
  - *"Log a visit with Dr. Anita Rao — discussed Cardexil, she was positive about efficacy data"*
  - *"Schedule a follow-up with Dr. Rao in 5 days to send the new trial data"*
  - *"What's the recent history with Dr. Rao?"*
  - *"Dr. Mehta mentioned a patient had nausea after starting Glucera — flag this"*
- Switch to **Structured form** mode to log the same kind of interaction without the chat,
  either letting the AI extract fields from free text or entering them manually.
- Use **Edit this entry** on any past interaction to try a natural-language edit, e.g.
  *"change the sentiment to negative"*.

---

## UI layout

The Log Interaction screen is a single view with two panels side by side (not a toggle
between modes): a structured form on the left ("Log HCP Interaction") and an "AI Assistant"
chat panel on the right, so a rep can use either — or both — without switching screens. The
left form panel scrolls internally within a fixed-height container so the chat panel stays
in view. Below both panels, an **Interaction History** list shows everything logged so far,
with an inline natural-language **"Edit this entry"** control — this is where the Edit
Interaction tool is demoed.

Two small AI-assist features live only in the form (they call the LLM directly via
`/api/assist/*`, separate from the 5 mandatory LangGraph tools which are only reachable
through the chat panel):
- **"Summarize from Voice Note"** — paste a transcript, and the LLM turns it into clean
  Topics Discussed / Outcomes text (no live audio capture in this build).
- **"AI Suggested Follow-ups"** — after typing Topics Discussed or Outcomes, the LLM proposes
  a few concrete next steps you can add to Follow-up Actions with one click.

## Notes on design choices

- **Two input modes, one data model.** The task asked for both a form and a chat interface;
  rather than treating them as separate features, both call into the same tool functions so
  the resulting records are consistent regardless of how they were created.
- **Adverse event flagging as a 5th tool.** Beyond the two mandatory tools (Log/Edit
  Interaction), an AE-reporting tool was included deliberately: pharmacovigilance is a real
  regulatory obligation for pharma field reps, so a CRM built by "a life science expert" should
  treat any mention of a patient side effect as a first-class, trackable event rather than
  just freeform notes.
- **Edit history is preserved, not overwritten.** `edit_interaction_tool` snapshots the prior
  state of a record before applying a natural-language patch, so nothing is silently lost.
- **Font:** Google Inter is loaded globally per the task's font requirement.

## What we understood from the task (summary)

The assignment asks for an AI-first Log Interaction screen where the AI agent is not a
bolt-on chatbot but the thing actually doing the CRM work — logging, editing, looking up,
scheduling, and safety-flagging — while a structured form remains available for reps who
prefer it. LangGraph provides the routing + tool-execution structure, and Groq provides the
LLM reasoning inside each tool (summarization, entity/sentiment extraction, and
natural-language edit interpretation).
=======
# hcp_crm_ai
This repo implements an AI-assisted CRM for healthcare professionals (HCPs). It provides a React frontend and a FastAPI backend that together let field reps log interactions, search and edit past interactions, schedule follow-ups, and ask an embedded AI assistant to extract or summarize interaction details.
>>>>>>> 6670c3fc4043e4ebd423cf6569d6b92e4f8baccb
