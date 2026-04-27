---
title: Incident Triage Environment
emoji: 🚨
colorFrom: red
colorTo: gray
sdk: docker
pinned: false
app_port: 8000
base_path: /demo
tags:
  - openenv
---

# Incident Triage — OpenEnv Environment.

**Can your LLM handle a production outage at 3 AM?**

This environment drops an AI agent into the seat of an on-call SRE engineer. It receives real server logs, firing alerts, CPU/memory metrics, and a list of affected services — then must make the right call under pressure: classify severity, pinpoint the root cause, decide on a first action, and determine whether to escalate.

Three scenarios. Increasing difficulty. Deterministic grading. Scores between 0.0 and 1.0.

**Live Environment:** [HF Space](https://huggingface.co/spaces/radhakrishna1210/incident-triage)

---

## Why Incident Triage?

Production systems break. When they do, an on-call engineer gets paged with a wall of logs, firing alerts, and seconds to make the right call:

- **How bad is this?** (severity classification)
- **What actually broke?** (root cause analysis)
- **What do I do first?** (action planning)
- **Do I wake up my manager?** (escalation judgment)

These are decisions real SREs make every day. Getting them wrong costs money, reputation, and sleep. This environment benchmarks whether an AI model can reason through ambiguous, high-stakes operational scenarios — not trivia, not toy problems.

It tests **calibrated judgment**: over-escalating a contained database restart is penalized just like missing a critical cascading failure. The model must be precise, not just cautious.

---

## How It Works

```
                        ┌─────────────────────────────┐
                        │      AI Model / Agent        │
                        └──────────────┬──────────────┘
                                       │
                    receives: server logs, active alerts,
                    CPU/memory metrics, affected services,
                    recent deployments
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │  Responds with structured JSON:      │
                    │  {                                   │
                    │    "severity":    low|med|high|crit  │
                    │    "root_cause":  database|memory|   │
                    │                  network|bad_deploy| │
                    │                  unknown             │
                    │    "first_action": "restart db..."   │
                    │    "escalate":    true|false          │
                    │  }                                   │
                    └──────────────────┬──────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │  Environment grades it:              │
                    │  reward score 0.0 – 1.0              │
                    │  (per-field partial credit)          │
                    └─────────────────────────────────────┘
```

The environment runs as an HTTP server following the OpenEnv spec. Any evaluator connects, calls `POST /reset` to start a scenario, calls `POST /step` with the model's action, and receives a reward.

---

## Observation Space

Each observation represents the state of a production system during an incident:

| Field | Type | Description |
|---|---|---|
| `task_name` | `string` | Scenario identifier |
| `turn` | `int` | Current turn (0-indexed) |
| `logs` | `list[str]` | Raw server log lines (error traces, connection failures, timeouts) |
| `alerts` | `list[str]` | Active monitoring alerts (PagerDuty-style) |
| `cpu_percent` | `float` | Current CPU utilization (0–100) |
| `memory_percent` | `float` | Current memory utilization (0–100) |
| `services_affected` | `list[str]` | Services currently degraded or down |
| `recent_deployments` | `list[str]` | Deployments in the last 24 hours |

All fields are typed Pydantic models (`IncidentTriageObservation`).

## Action Space

The agent must respond with a structured triage decision:

| Field | Type | Values | What it tests |
|---|---|---|---|
| `severity` | `string` | `low`, `medium`, `high`, `critical` | Threat assessment calibration |
| `root_cause` | `string` | `database`, `memory`, `network`, `bad_deploy`, `unknown` | Diagnostic reasoning |
| `first_action` | `string` | Free text | Operational knowledge (graded by keyword match) |
| `escalate` | `bool` | `true` / `false` | Escalation judgment — over-escalation is penalized |

All fields are typed Pydantic models (`IncidentTriageAction`).

---

## The Three Tasks

### Task 1 — `single_service_down` (Easy, 1 turn)

**Scenario:** The `auth-service` is down. All logs point to `connection refused on port 5432` — that's PostgreSQL. CPU and memory are normal. No recent deployments.

**What a good model does:** Identifies `database` as root cause, says restart/reconnect the database, marks severity as `high`, does NOT escalate (it's a contained, fixable issue).

**Scoring rubric:**

| Component | Points | Criteria |
|---|---|---|
| Severity | +0.35 | `high` |
| Root cause | +0.35 | `database` |
| First action | +0.20 | Contains (`restart` or `reconnect`) **AND** (`database` or `db` or `postgres`) |
| Escalation | +0.10 | `false` (no escalation needed) |
| Escalation penalty | -0.15 | If `true` (over-escalation) |

**Max score: 1.0**

---

### Task 2 — `bad_deployment` (Medium, 1 turn)

**Scenario:** Three services (`payment`, `order`, `email`) degraded simultaneously — three minutes after `inventory-service v2.3.1` was deployed. The deployment timestamp is in the recent deployments list.

**What a good model does:** Connects the timing correlation, identifies `bad_deploy` as root cause, says rollback the deployment, does NOT escalate (rollback is a clear contained fix).

**Scoring rubric:**

| Component | Points | Criteria |
|---|---|---|
| Severity | +0.35 | `high` |
| Root cause | +0.35 | `bad_deploy` |
| First action | +0.20 | Contains: `rollback`, `roll back`, or `revert` |
| Escalation | +0.10 | `false` |
| Escalation penalty | -0.10 | If `true` |

**Max score: 1.0**

---

### Task 3 — `cascading_failure` (Hard, 2 turns)

This is a multi-turn episode. The agent must adapt its response based on what happened after its first action.

**Turn 1:** PostgreSQL has hit its max connection limit (500/500). API gateway error rate is at 67%. Four services are timing out. CPU at 91%, memory at 88%. Full SLO breach.

| Component | Points | Criteria |
|---|---|---|
| Severity | +0.20 | `critical` |
| Root cause | +0.20 | `database` |
| First action | +0.10 | Contains: `connection` or `pool` |
| Escalation | +0.10 | `true` (this is a broad incident — escalation is correct) |

**Turn 2:** Connection pool has been expanded. Most services recovered — but `order-service` is still timing out. Logs reveal a 45-second query and a possible deadlock. Error rate dropped from 67% to 31%.

| Component | Points | Criteria |
|---|---|---|
| Root cause | +0.25 | `database` (still a DB issue — deadlock) |
| First action | +0.25 | Contains: `deadlock` or `order` (targeting the specific problem) |
| Severity | +0.10 | `high` or `critical` |

**Cumulative reward is capped at 1.0.** The model must reason across turns — the second observation changes based on the first action.

**Max score: 1.0**

---

## Reward Design Philosophy

Every field in the action is scored independently. This creates **partial credit** — a model that gets severity and root cause right but uses weak action keywords still earns 0.70. This is intentional:

- **Partial progress signals** over full trajectory, not binary pass/fail
- **Over-escalation penalties** — paging on-call for a contained issue loses points
- **Keyword-grounded actions** — the model must use operationally meaningful language, not vague responses
- **Multi-turn adaptation** — Task 3 requires the model to update its diagnosis after new information
- **Scenario variants** — each task has 2 log/alert variants that alternate, preventing keyword overfitting

The reward function tests **calibrated, precise SRE reasoning** — not just pattern matching.

---

## Evaluation Metrics

| Metric | Formula | Target |
|---|---|---|
| Per-task reward | Final `reward` returned by environment (0.0–1.0) | >= 0.80 |
| Benchmark average | `(task1 + task2 + task3) / 3` | >= 0.85 |
| Perfect-task count | Number of tasks scoring `1.0` | 2+ |

---

## Baseline Scores

### LLM Baseline (Qwen2.5-72B-Instruct, optimised prompt)

| Task | Score |
|---|---|
| single_service_down | 0.99 |
| bad_deployment | 0.99 |
| cascading_failure | 0.99 |
| **Average** | **0.990** |

The inference script uses a structured system prompt with explicit keyword guidance that aligns with the grading rubric.  
*Without keyword guidance the same model scored 0.55 / 0.60 / 1.00 (avg 0.717) due to weak first-action phrasing.*

### Deterministic Oracle Agent (rubric sanity check)

| Task | Score |
|---|---|
| single_service_down | 1.00 |
| bad_deployment | 1.00 |
| cascading_failure | 1.00 |
| **Average** | **1.000** |

A rule-based agent that submits perfect answers. Runs automatically via `GET /scoreboard`. Use this as a regression guard — your target LLM should approach this ceiling.

---

## API Reference

The environment follows the **OpenEnv standard HTTP interface**:

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/reset` | Start a new episode. Accepts optional `task_name`. Returns first observation. |
| `POST` | `/step` | Submit an action (JSON body). Returns reward, next observation, done flag. |
| `GET` | `/state` | Current episode state (task, done, cumulative reward). |
| `GET` | `/schema` | Full JSON schemas for Action and Observation models. |
| `GET` | `/health` | Health check. Returns `{"status": "healthy"}`. |
| `GET` | `/metadata` | Environment metadata (name, description, tasks). |
| `GET` | `/docs` | Interactive Swagger UI for all endpoints. |

### Additional Routes

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/demo` | Interactive demo UI — manually reset tasks and submit actions. |
| `GET` | `/scoreboard` | Runs the deterministic oracle agent in-browser and displays scores. |

### Example: Reset + Step

```bash
# Start task 1
curl -X POST http://localhost:8000/reset \
  -H "Content-Type: application/json" \
  -d '{"task_name": "single_service_down"}'

# Submit an action — action fields must be wrapped in an "action" key
curl -X POST http://localhost:8000/step \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "severity": "high",
      "root_cause": "database",
      "first_action": "restart database connection pool and verify postgres connectivity",
      "escalate": false
    }
  }'
# → {"reward": 0.99, "done": true, "observation": {...}}
```

---

## Project Structure

```
incident_triage/            ← repo root
├── inference.py            # Hackathon inference script — [START]/[STEP]/[END] stdout logs
├── models.py               # Pydantic Action, Observation, State models
├── client.py               # HTTP client (IncidentTriageEnv)
├── openenv.yaml            # OpenEnv metadata: name, version, tags, tasks list
├── Dockerfile              # Root Dockerfile — used by HF Spaces (Docker SDK)
├── pyproject.toml          # Package config + dependencies (openenv-core, openai)
├── server/
│   ├── app.py              # FastAPI app — OpenEnv + /demo + /scoreboard
│   ├── incident_triage_environment.py  # Core: 3 scenarios, graders, episode state
│   ├── demo.html           # Interactive testing UI
│   ├── scoreboard.html     # Oracle agent benchmark dashboard
│   ├── requirements.txt    # Server dependencies
│   └── Dockerfile          # Standalone multi-stage Docker build
├── tests/
│   ├── conftest.py         # Offline test stubs (no openenv dependency)
│   └── test_incident_triage_environment.py  # 7 unit tests covering all tasks + variants
└── README.md               # This file — also serves as HF Space description
```

---

## Running Locally

### Quick Start

```bash
cd incident_triage
uv sync
uv run server
# Server at http://localhost:8000
# Swagger at http://localhost:8000/docs
# Demo UI at http://localhost:8000/demo
# Scoreboard at http://localhost:8000/scoreboard
```

### Run Inference Against Any LLM

```bash
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"
export HF_TOKEN="hf_..."
export ENV_URL="http://localhost:8000"

python inference.py
```

The script emits structured stdout logs for each task in the required format:

```
[START] task=single_service_down env=incident_triage model=Qwen/Qwen2.5-72B-Instruct
[STEP] step=1 action={"severity":"high",...} reward=0.99 done=true error=null
[END] success=true steps=1 score=0.99 rewards=0.99

[START] task=cascading_failure env=incident_triage model=Qwen/Qwen2.5-72B-Instruct
[STEP] step=1 action={...} reward=0.60 done=false error=null
[STEP] step=2 action={...} reward=0.99 done=true error=null
[END] success=true steps=2 score=0.99 rewards=0.60,0.99
```

### Docker

```bash
# Using the root Dockerfile (same as HF Spaces)
docker build -t incident-triage:latest .
docker run -p 8000:8000 incident-triage:latest

# Or using the server/Dockerfile explicitly
docker build -t incident-triage:latest -f server/Dockerfile .
docker run -p 8000:8000 incident-triage:latest
```

### Run Tests

```bash
cd incident_triage
python -m pytest tests/ -v
```

---

## Technical Design Decisions

| Decision | Rationale |
|---|---|
| **Stateful HTTP via module-level `_SHARED` dict** | OpenEnv creates a fresh Environment instance per HTTP request. A module-level dict persists episode state across `/reset` and `/step` calls without external storage. |
| **2 scenario variants per task** | Logs and alert text alternate between runs, preventing models from overfitting to specific string patterns while keeping grading deterministic. |
| **Keyword-based action grading** | Free-text `first_action` is graded by presence of operational keywords (restart, rollback, pool, deadlock). This rewards domain-appropriate language without requiring exact string matches. |
| **Escalation as a scored boolean** | Escalation is not always correct. Contained single-service failures should NOT be escalated. Broad cascading failures SHOULD be. This tests calibrated judgment, not a bias toward caution. |
| **Multi-turn for Task 3 only** | The cascading failure scenario naturally requires adaptation — the system state changes after the first intervention. Single-service and bad-deploy are diagnosed in one shot. |
| **Cumulative reward capped at 1.0** | Prevents reward inflation on multi-turn tasks. Both turns must contribute meaningfully. |

---

## OpenEnv Compliance

| Spec Requirement | Implementation |
|---|---|
| Typed Observation model | `IncidentTriageObservation` (Pydantic) — logs, alerts, cpu, memory, services, deployments, turn, task_name |
| Typed Action model | `IncidentTriageAction` (Pydantic) — severity, root_cause, first_action, escalate |
| Typed State model | `IncidentTriageState` (Pydantic) — task_name, done, cumulative_reward |
| `step(action)` | Returns observation, reward (0.0–1.0), done, info |
| `reset(task_name?)` | Returns initial observation; cycles tasks if no name given |
| `state()` | Returns current episode state |
| `openenv.yaml` | Name, description, tags, tasks list (3 tasks with difficulty + reward\_range) |
| HF Space deployment | Docker SDK, `app_port: 8000`, tagged `openenv` |
| Dockerfile | Multi-stage build, runs on minimal resources |

---

## Built For

**OpenEnv Hackathon** — Meta x Scaler School of Technology

OpenEnv is a framework by Meta for building standardized AI evaluation environments. This submission puts LLMs through real-world SRE scenarios and scores their operational reasoning.

**Team:** Mission Bangalore
