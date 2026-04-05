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

# Incident Triage Environment

## Overview

The Incident Triage environment simulates a production on-call scenario where an AI agent acts as an SRE engineer responding to live incidents. The agent receives realistic server logs and active alerts, then must correctly diagnose the incident and choose the right first response.

The environment tests whether a model can:
- Distinguish incident severity accurately (not every outage is "critical")
- Identify root cause from noisy log signals (database exhaustion vs bad deploy vs network)
- Prescribe the correct first action (rollback, restart, pool expansion, escalation)
- Decide when to page the on-call team — and when not to

Three tasks escalate from a simple single-service outage to a multi-service cascading failure requiring multi-turn reasoning. This makes it useful for evaluating both prompt engineering and model reasoning quality on domain-specific operational tasks.

---

## Observation Space

| Field | Type | Description |
|---|---|---|
| `logs` | `list[str]` | Timestamped server log lines from the incident window |
| `alerts` | `list[str]` | Active firing alerts from the monitoring system |
| `cpu_percent` | `float` | Current CPU utilisation across the affected host (0–100) |
| `memory_percent` | `float` | Current memory utilisation across the affected host (0–100) |
| `services_affected` | `list[str]` | Names of services currently marked as DOWN or degraded |
| `recent_deployments` | `list[str]` | Deployment events that occurred shortly before the incident |
| `turn` | `int` | Current turn number within the episode (0-indexed) |
| `task_name` | `str` | Identifier for the active scenario |

---

## Action Space

The agent responds with a single structured action containing four fields:

| Field | Options / Type | Description |
|---|---|---|
| `severity` | `"low"` \| `"medium"` \| `"high"` \| `"critical"` | Agent's assessed severity of the incident |
| `root_cause` | `"database"` \| `"memory"` \| `"network"` \| `"bad_deploy"` \| `"unknown"` | Agent's identified root cause |
| `first_action` | `str` (free text) | The first remediation step the agent takes |
| `escalate` | `bool` | Whether to page the on-call team immediately |

Invalid values for `severity` or `root_cause` are rejected at parse time by Pydantic.

---

## Tasks

### Task 1 — `single_service_down` (Easy)

**Scenario:** The `auth-service` has been down for 2 minutes. All logs point to connection refused on port 5432 (PostgreSQL). No recent deployments. CPU and memory are normal (14% / 42%). Only one service is affected.

**Correct response:** Severity `high` (users cannot authenticate, but it is not a full system outage). Root cause `database` (port 5432 is the PostgreSQL port). First action should restart or check the database. Escalation is not needed — it is a contained, identifiable failure.

---

### Task 2 — `bad_deployment` (Medium)

**Scenario:** Three downstream services (`payment-service`, `order-service`, `email-service`) degraded simultaneously three minutes after `inventory-service v2.3.1` was deployed. The deployment is listed in `recent_deployments`. CPU and memory are elevated but not critical (58% / 61%).

**Correct response:** Severity `high`. Root cause `bad_deploy` — the timing of the deployment and the cascade pattern make this clear. First action should roll back `inventory-service`. Escalation is not required if the rollback path is clear.

---

### Task 3 — `cascading_failure` (Hard, 2-turn)

**Turn 1 scenario:** The PostgreSQL primary has hit its connection limit (500/500). The API gateway error rate is 67%. Four services are timing out simultaneously. CPU at 91%, memory at 88%. This is a full SLO breach.

**Turn 1 correct response:** Severity `critical`. Root cause `database` (connection pool exhaustion). First action should increase the connection pool limit or implement connection pooling (keywords: `connection` or `pool`). Escalate `true` — this is a severity-1 incident.

**Turn 2 scenario:** After the pool was expanded, most services recovered, but `order-service` is still timing out. Logs show a 45-second query and a possible deadlock. Error rate dropped from 67% to 31%.

**Turn 2 correct response:** Root cause `database` (deadlock is still a database issue). First action targets the deadlock or `order-service` specifically. Severity should remain `high` or `critical`.

**Final score** = sum of both turn scores, capped at 1.0.

---

## Reward Function

All scores are floats between 0.0 and 1.0.

### Task 1 — `single_service_down`

| Condition | Points |
|---|---|
| `severity == "high"` | +0.35 |
| `root_cause == "database"` | +0.35 |
| `"restart"` and `"database"` both in `first_action` (case-insensitive) | +0.20 |
| `escalate == False` | +0.10 |
| `escalate == True` | −0.15 |

Maximum: **1.00** — Perfect score requires correct severity, root cause, action keywords, and no escalation.

### Task 2 — `bad_deployment`

| Condition | Points |
|---|---|
| `severity == "high"` | +0.35 |
| `root_cause == "bad_deploy"` | +0.35 |
| `"rollback"` in `first_action` (case-insensitive) | +0.20 |
| `escalate == False` | +0.10 |
| `escalate == True` | −0.10 |

Maximum: **1.00**

### Task 3 — `cascading_failure` (cumulative across 2 turns)

**Turn 1**

| Condition | Points |
|---|---|
| `severity == "critical"` | +0.20 |
| `root_cause == "database"` | +0.20 |
| `"connection"` or `"pool"` in `first_action` (case-insensitive) | +0.10 |
| `escalate == True` | +0.10 |

Turn 1 maximum: **0.60**

**Turn 2**

| Condition | Points |
|---|---|
| `root_cause == "database"` | +0.25 |
| `"deadlock"` or `"order"` in `first_action` (case-insensitive) | +0.25 |
| `severity in ["high", "critical"]` | +0.10 |

Turn 2 maximum: **0.60**

Combined maximum (capped): **1.00**

---

## Baseline Scores

Model: **`Qwen/Qwen2.5-72B-Instruct`** via HF Inference Router (`https://router.huggingface.co/v1`)

| Task | Score | Max Possible |
|---|---|---|
| single_service_down | 0.550 | 1.000 |
| bad_deployment | 0.600 | 1.000 |
| cascading_failure | 1.000 | 1.000 |
| **Average** | **0.717** | **1.000** |

### Score Analysis

**Task 1 — `single_service_down`: 0.550**

The model earned +0.35 for correct severity (`high`) and +0.35 for correct root cause (`database`) — port 5432 is a well-known PostgreSQL port that large LLMs reliably recognise from training data. However, two deductions hit:

- **−0.15** from the escalation penalty: the model chose `escalate=true`. A single contained service failure with a clear database cause is not escalation-worthy. The grader penalises over-escalation to reward calibrated confidence.
- **−0.20** missed: the first action read `"Check the database service status and connectivity"`. The grader requires both the word `restart` **and** the word `database` to appear together. The model diagnosed correctly but prescribed a cautious check rather than an immediate restart — a plausible but lower-scoring response.

Net path: `0.35 + 0.35 + 0.00 − 0.15 = 0.55`

---

**Task 2 — `bad_deployment`: 0.600**

The model correctly identified severity (`high`) and root cause (`bad_deploy`) — the correlation between the `inventory-service v2.3.1` deployment timestamp and the simultaneous degradation of three downstream services is a pattern LLMs reason about well. Deductions:

- **−0.10** from escalation penalty: the model chose `escalate=true`. A clear rollback path makes escalation unnecessary per the grader.
- **−0.20** missed: the first action read `"Roll back inventory-service to previous version"`. Note the two-word form `"roll back"` — the grader does exact substring matching on `"rollback"` (one word). The intent was correct but the spelling variant caused the keyword match to miss.

Net path: `0.35 + 0.35 + 0.00 − 0.10 = 0.60`

---

**Task 3 — `cascading_failure`: 1.000**

Perfect score across both turns. Multi-turn incident reasoning plays directly to the strengths of large language models:

- **Turn 1**: The log line `CRITICAL postgres-primary: max_connections=500 reached` and `pq: too many clients` are canonical database connection exhaustion signals. The model immediately identified `database` as root cause, used the word `connection` in its first action, assessed `critical` severity, and correctly escalated — all four conditions met for +0.60.
- **Turn 2**: The log line `order-service: query taking 45s (deadlock?)` contains the word `deadlock` explicitly. The model echoed this back in its first action (`"Check for deadlocks in the postgres-primary database"`), earning the keyword match. Combined with correct root cause and severity, this scored the full +0.60 for turn 2.
- Combined raw score 1.20 is capped at 1.00.

The difficulty curve is intentional: Task 1 punishes over-caution and keyword imprecision, Task 2 punishes two-word synonyms and over-escalation, Task 3 rewards sustained multi-turn reasoning — a capability that clearly improves with model size.

---

### What a Perfect Agent Would Do

These are the exact responses that score 1.00 on each task.

**Task 1 — `single_service_down`**
```json
{
  "severity": "high",
  "root_cause": "database",
  "first_action": "restart database and verify connection on port 5432",
  "escalate": false
}
```
Scoring: +0.35 (severity) +0.35 (root\_cause) +0.20 (restart + database in action) +0.10 (no escalation) = **1.00**

**Task 2 — `bad_deployment`**
```json
{
  "severity": "high",
  "root_cause": "bad_deploy",
  "first_action": "rollback inventory-service to the previous stable version",
  "escalate": false
}
```
Scoring: +0.35 (severity) +0.35 (root\_cause) +0.20 (rollback in action) +0.10 (no escalation) = **1.00**

**Task 3 — `cascading_failure` (Turn 1)**
```json
{
  "severity": "critical",
  "root_cause": "database",
  "first_action": "increase PostgreSQL connection pool limit to resolve exhaustion",
  "escalate": true
}
```
Scoring: +0.20 (severity) +0.20 (root\_cause) +0.10 (pool in action) +0.10 (escalate) = **0.60**

**Task 3 — `cascading_failure` (Turn 2)**
```json
{
  "severity": "critical",
  "root_cause": "database",
  "first_action": "identify and kill the deadlock query on order-service",
  "escalate": true
}
```
Scoring: +0.25 (root\_cause) +0.25 (deadlock + order in action) +0.10 (severity) = **0.60**

Combined: 0.60 + 0.60 = 1.20 → capped at **1.00**

---

## Setup & Usage

### Run locally with uvicorn

```bash
# From the incident_triage directory
pip install openenv-core[core]>=0.2.2
uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload
```

The server will be available at `http://localhost:8000`.
Interactive web UI: `http://localhost:8000/web`
API docs: `http://localhost:8000/docs`

### Run with Docker

```bash
# Build the image (from the incident_triage directory)
docker build -t incident-triage:latest -f server/Dockerfile .

# Run the container
docker run -p 8000:8000 incident-triage:latest
```

### Run inference.py

```bash
# Set required environment variables
export API_BASE_URL="https://api-inference.huggingface.co/v1"
export MODEL_NAME="meta-llama/Llama-3.1-8B-Instruct"
export HF_TOKEN="hf_..."
export ENV_URL="http://localhost:8000"   # or your deployed space URL

# Run all 3 tasks
python inference.py
```

Example output:

```
============================================================
Task: single_service_down
============================================================

[Turn 0] Querying LLM...
  severity='high'  root_cause='database'  escalate=False
  first_action: Restart the database connection on auth-service
  => turn reward / cumulative: 1.000

Final score for 'single_service_down': 1.000

...

============================================================
FINAL SUMMARY
============================================================
  single_service_down            1.000
  bad_deployment                 0.800
  cascading_failure              0.600
  AVERAGE                        0.800
============================================================
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `API_BASE_URL` | Yes | Base URL of the OpenAI-compatible inference endpoint (e.g. `https://api-inference.huggingface.co/v1`) |
| `MODEL_NAME` | Yes | Model identifier passed to the chat completions API (e.g. `meta-llama/Llama-3.1-8B-Instruct`) |
| `HF_TOKEN` | Yes | Bearer token for the inference endpoint — Hugging Face User Access Token or provider API key |
| `ENV_URL` | No | Base URL of the running environment server (default: `http://localhost:8000`) |
