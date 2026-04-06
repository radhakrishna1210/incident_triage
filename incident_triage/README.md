---
title: Incident Triage Environment
emoji: 🚨
colorFrom: red
colorTo: gray
sdk: docker
pinned: false
app_port: 8000
base_path: /web
tags:
  - openenv
---

# Incident Triage — OpenEnv Hackathon Submission

> **Can your LLM handle a production outage at 3am?**
> This environment puts any AI model in the seat of an on-call SRE engineer and scores how well it triages real incidents.

---

## The Idea

Production systems break. When they do, an on-call engineer gets paged with a wall of logs, firing alerts, and seconds to make the right call:

- How bad is this?
- What actually broke?
- What do I do first?
- Do I wake up my manager?

This environment simulates exactly that — three realistic incident scenarios of increasing difficulty — and automatically scores an AI model's response. Plug in any LLM, run all three tasks, get a score between 0 and 1.

It's a benchmark for **real-world SRE reasoning**, not trivia.

---

## How It Works

```
AI model
   │
   │  receives: server logs, active alerts, CPU/memory metrics, affected services
   ▼
responds with a structured JSON action:
   {
     "severity":    "low" | "medium" | "high" | "critical",
     "root_cause":  "database" | "memory" | "network" | "bad_deploy" | "unknown",
     "first_action": "<free text describing what to do>",
     "escalate":    true | false
   }
   │
   ▼
environment grades it → reward score 0.0 – 1.0
```

The environment runs as an HTTP server. Any evaluator connects, calls `/reset` to start a scenario, calls `/step` with the model's action, and receives a reward.

---

## The Three Tasks

### Task 1 — `single_service_down` (Easy)

The `auth-service` is down. All logs point to `connection refused port 5432` — that's PostgreSQL. CPU and memory are normal. No recent deployments.

**What a good model does:** Identifies database as root cause, says restart the database, marks severity as high, does NOT escalate (it's a contained, fixable issue).

**Max score: 1.0**

---

### Task 2 — `bad_deployment` (Medium)

Three services (`payment`, `order`, `email`) degraded simultaneously — three minutes after `inventory-service v2.3.1` was deployed. The deployment is in the recent deployments list.

**What a good model does:** Connects the timing, identifies `bad_deploy` as root cause, says rollback the deployment, does NOT escalate (rollback is a clear contained fix).

**Max score: 1.0**

---

### Task 3 — `cascading_failure` (Hard — 2 turns)

**Turn 1:** PostgreSQL hit its connection limit (500/500). API gateway error rate at 67%. Four services timing out. CPU 91%, memory 88%. Full SLO breach.

→ Good response: `critical` severity, `database` root cause, expand the connection pool, escalate immediately.

**Turn 2:** Pool expanded. Most services recovered — but `order-service` is still timing out. Logs show a 45-second query and a possible deadlock. Error rate dropped from 67% to 31%.

→ Good response: Still `database`, target the deadlock on `order-service`, kill the blocking query.

This is the only task that requires multi-turn reasoning — the model must adapt based on what happened after its first action.

**Max score: 1.0 (capped sum of both turns)**

---

## Scoring

Every field in the action is scored separately. The model has to get severity, root cause, the keywords in the action text, and the escalation decision all right to score full marks.

Over-escalating (paging on-call for a contained issue) is penalised. Correct diagnosis with wrong action keywords also loses points. This is intentional — it rewards calibrated, precise thinking, not just pattern matching.

| Task | Max Score |
|---|---|
| single_service_down | 1.0 |
| bad_deployment | 1.0 |
| cascading_failure | 1.0 |
| **Average** | **1.0** |

---

## Baseline Results

Tested with **Qwen2.5-72B-Instruct** via HuggingFace Inference Router:

| Task | Score |
|---|---|
| single_service_down | 0.55 |
| bad_deployment | 0.60 |
| cascading_failure | 1.00 |
| **Average** | **0.717** |

Interesting pattern: the hard multi-turn task scored highest. The model nailed cascading failure reasoning but lost points on the easier tasks due to over-escalation and synonym mismatches (`"roll back"` vs `"rollback"`). This shows the benchmark is sensitive to precision, not just general knowledge.

---

## Running It

### Start the server locally

```bash
cd incident_triage
uv run server
# Server running at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### Run inference against any LLM

```bash
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"
export HF_TOKEN="hf_..."
export ENV_URL="http://localhost:8000"

python inference.py
```

### Run with Docker

```bash
docker build -t incident-triage:latest -f server/Dockerfile .
docker run -p 8000:8000 incident-triage:latest
```

---

## API Reference

| Method | Endpoint | What it does |
|---|---|---|
| `POST` | `/reset` | Start a new episode, get the first observation |
| `POST` | `/step` | Submit an action, get reward + next observation |
| `GET` | `/state` | Check current episode state |
| `GET` | `/schema` | Get full JSON schemas for action and observation |
| `GET` | `/health` | Health check |
| `GET` | `/metadata` | Environment info |
| `GET` | `/docs` | Interactive Swagger UI |

---

## Project Structure

```
incident_triage/
├── models.py                          # Action, Observation, State data models
├── client.py                          # WebSocket client for connecting to the server
├── inference.py                       # Run any LLM against all 3 tasks
├── server/
│   ├── app.py                         # FastAPI app entry point
│   └── incident_triage_environment.py # The 3 scenarios + grading logic
└── pyproject.toml
```

---

## Built For

**OpenEnv Hackathon** — a competition to build standardised AI evaluation environments.
OpenEnv is a framework by Meta that lets anyone build, host, and benchmark AI agents against structured environments over a standard HTTP API.

This submission: **Mission Bangalore**
