# Incident Triage — OpenEnv RL Environment

**Can your LLM survive a 3 AM production outage?**

A reinforcement-learning environment that drops an AI agent into the seat of an on-call SRE engineer. The agent receives real server logs, firing alerts, CPU/memory metrics, and degraded service lists — then must make the right call under pressure: classify severity, pinpoint root cause, decide a first action, and determine whether to escalate.

**3 scenarios | 2 difficulty tiers | Multi-turn episodes | Deterministic grading | Scores 0.0 - 1.0**

| | |
|---|---|
| **Live Environment** | [HuggingFace Space](https://huggingface.co/spaces/radhakrishna1210/incident-triage) |
| **Framework** | Meta OpenEnv |
| **Hackathon** | Meta x Scaler School of Technology — OpenEnv Hackathon |
| **Team** | Mission Bangalore |

---

## Benchmark Results at a Glance

### LLM Baseline — Qwen2.5-72B-Instruct

| Task | Score | Result |
|---|---|---|
| `single_service_down` | **0.55 / 1.00** | Partial — over-escalation penalty |
| `bad_deployment` | **0.60 / 1.00** | Partial — weak action keywords |
| `cascading_failure` | **1.00 / 1.00** | Perfect |
| **Benchmark Average** | **0.717 / 1.00** | |

### Deterministic Oracle Agent (rubric ceiling)

| Task | Score | Result |
|---|---|---|
| `single_service_down` | **1.00 / 1.00** | Perfect |
| `bad_deployment` | **1.00 / 1.00** | Perfect |
| `cascading_failure` | **1.00 / 1.00** | Perfect |
| **Benchmark Average** | **1.000 / 1.00** | |

### Evaluation Targets

| Metric | Formula | Target |
|---|---|---|
| Per-task reward | Final `reward` from environment (0.0 - 1.0) | **>= 0.80** |
| Benchmark average | `(task1 + task2 + task3) / 3` | **>= 0.85** |
| Perfect-task count | Tasks scoring exactly `1.0` | **>= 2** |

---

## Architecture

```
                     ┌──────────────────────────────────┐
                     │        AI Model / Agent           │
                     └───────────────┬──────────────────┘
                                     │
                  receives: server logs, active alerts,
                  CPU/memory metrics (0-100%), affected
                  services, recent deployments
                                     │
                                     v
                     ┌──────────────────────────────────┐
                     │  Responds with structured JSON:   │
                     │  {                                │
                     │    "severity":    low|med|high|   │
                     │                   critical       │
                     │    "root_cause":  database|      │
                     │       memory|network|bad_deploy|  │
                     │       unknown                    │
                     │    "first_action": free text     │
                     │    "escalate":    true|false     │
                     │  }                               │
                     └───────────────┬──────────────────┘
                                     │
                                     v
                     ┌──────────────────────────────────┐
                     │  Environment grades each field:   │
                     │  severity   -> 0.10 - 0.35 pts  │
                     │  root_cause -> 0.20 - 0.35 pts  │
                     │  action     -> 0.10 - 0.25 pts  │
                     │  escalation -> 0.10 pts / -0.15  │
                     │  ─────────────────────────────   │
                     │  reward: 0.0 - 1.0 (capped)     │
                     └──────────────────────────────────┘
```

---

## The Three Tasks — Full Scoring Rubrics

### Task 1: `single_service_down` — Easy | 1 Turn

**Scenario:** `auth-service` is down. Logs show `connection refused on port 5432` (PostgreSQL). CPU 14%, Memory 42%. No recent deployments.

**Expected answer:** severity=`high`, root_cause=`database`, first_action contains restart/reconnect + db keyword, escalate=`false`

| Component | Points | Criteria | Weight |
|---|---|---|---|
| Severity | **+0.35** | Exactly `high` | 35% |
| Root cause | **+0.35** | Exactly `database` | 35% |
| First action | **+0.20** | Contains (`restart` OR `reconnect`) AND (`database` OR `db` OR `postgres`) | 20% |
| Escalation correct | **+0.10** | `false` — contained, fixable issue | 10% |
| Escalation penalty | **-0.15** | If `true` — over-escalation punished | -15% |

**Max score: 1.00 | Min possible: 0.00 | Penalty floor: -0.15 (clamped to 0.0)**

**2 scenario variants** — alternate log templates prevent keyword overfitting.

---

### Task 2: `bad_deployment` — Medium | 1 Turn

**Scenario:** 3 services (`payment`, `order`, `email`) degraded simultaneously — 3 minutes after `inventory-service v2.3.1` deployed. CPU 58%, Memory 61%.

**Expected answer:** severity=`high`, root_cause=`bad_deploy`, first_action contains rollback/revert, escalate=`false`

| Component | Points | Criteria | Weight |
|---|---|---|---|
| Severity | **+0.35** | Exactly `high` | 35% |
| Root cause | **+0.35** | Exactly `bad_deploy` | 35% |
| First action | **+0.20** | Contains `rollback` OR `roll back` OR `revert` | 20% |
| Escalation correct | **+0.10** | `false` — rollback is a clear contained fix | 10% |
| Escalation penalty | **-0.10** | If `true` — unnecessary escalation | -10% |

**Max score: 1.00 | Min possible: 0.00 | Penalty floor: -0.10 (clamped to 0.0)**

**2 scenario variants** — different deployment versions and log timestamps.

---

### Task 3: `cascading_failure` — Hard | 2 Turns (Multi-Turn)

A multi-turn episode. The agent must adapt its diagnosis based on new information after its first intervention.

#### Turn 1 — System Meltdown

**Scenario:** PostgreSQL hit max connections (500/500). API gateway error rate 67%. 4 services timing out. CPU **91%**, Memory **88%**. Full SLO breach.

| Component | Points | Criteria | Weight |
|---|---|---|---|
| Severity | **+0.20** | Exactly `critical` | 20% |
| Root cause | **+0.20** | Exactly `database` | 20% |
| First action | **+0.10** | Contains `connection` OR `pool` | 10% |
| Escalation | **+0.10** | `true` — broad incident, escalation is correct | 10% |

**Turn 1 max: 0.60**

#### Turn 2 — Partial Recovery + Deadlock

**Scenario:** Connection pool expanded to 1000. Most services recovered. `order-service` still timing out — logs reveal 45-second query and possible deadlock. Error rate dropped from **67% to 31%**. CPU **74%**, Memory **79%**.

| Component | Points | Criteria | Weight |
|---|---|---|---|
| Root cause | **+0.25** | Exactly `database` (still DB — deadlock) | 25% |
| First action | **+0.25** | Contains `deadlock` OR `order` | 25% |
| Severity | **+0.10** | `high` OR `critical` | 10% |

**Turn 2 max: 0.60**

**Cumulative reward capped at 1.00.** Both turns must contribute meaningfully.

**2 scenario variants** — different gateway names and alert phrasing.

---

## Score Breakdown Summary

| Task | Severity | Root Cause | First Action | Escalation | Penalty | Max |
|---|---|---|---|---|---|---|
| `single_service_down` | 0.35 | 0.35 | 0.20 | 0.10 | -0.15 | **1.00** |
| `bad_deployment` | 0.35 | 0.35 | 0.20 | 0.10 | -0.10 | **1.00** |
| `cascading_failure` T1 | 0.20 | 0.20 | 0.10 | 0.10 | — | 0.60 |
| `cascading_failure` T2 | 0.10 | 0.25 | 0.25 | — | — | 0.60 |
| **Total possible per task** | | | | | | **1.00** |
| **Total across 3 tasks** | | | | | | **3.00** |

---

## Reward Design Philosophy

| Principle | How It Works |
|---|---|
| **Partial credit** | Each field scored independently — a model that nails severity + root cause but uses weak keywords still earns **0.70** |
| **Over-escalation penalties** | Paging on-call for a contained issue **loses 0.10 - 0.15 points** — caution without precision is penalized |
| **Keyword-grounded actions** | `first_action` must contain operationally meaningful keywords (restart, rollback, pool, deadlock) — vague answers score 0 |
| **Multi-turn adaptation** | Task 3 requires updating diagnosis after new information — copy-paste answers from Turn 1 will fail Turn 2 |
| **Scenario variants** | 2 log/alert templates per task alternate between runs — prevents keyword overfitting while keeping grading deterministic |
| **Cumulative cap at 1.0** | Multi-turn tasks don't inflate scores — both turns must contribute meaningfully |

---

## Observation Space — 8 Fields

| Field | Type | Example Values | Description |
|---|---|---|---|
| `task_name` | `string` | `single_service_down`, `bad_deployment`, `cascading_failure` | Scenario identifier |
| `turn` | `int` | `0`, `1` | Current turn (0-indexed) |
| `logs` | `list[str]` | `"[02:14:11] ERROR auth-service: connection refused port 5432"` | Raw server log lines |
| `alerts` | `list[str]` | `"auth-service DOWN for 2 minutes"` | Active monitoring alerts |
| `cpu_percent` | `float` | `14.0` - `91.0` | CPU utilization (0 - 100) |
| `memory_percent` | `float` | `39.0` - `88.0` | Memory utilization (0 - 100) |
| `services_affected` | `list[str]` | `["auth-service"]`, `["payment-service", "order-service", "email-service"]` | Currently degraded services |
| `recent_deployments` | `list[str]` | `["inventory-service v2.3.1 deployed 3 mins ago"]` | Recent deployment events |

All fields are typed Pydantic models (`IncidentTriageObservation`).

## Action Space — 4 Fields

| Field | Type | Valid Values | What It Tests |
|---|---|---|---|
| `severity` | `Literal` | `low`, `medium`, `high`, `critical` | Threat assessment calibration |
| `root_cause` | `Literal` | `database`, `memory`, `network`, `bad_deploy`, `unknown` | Diagnostic reasoning |
| `first_action` | `string` | Free text (keyword-graded) | Operational knowledge |
| `escalate` | `bool` | `true` / `false` | Escalation judgment — over-escalation is penalized |

All fields are typed Pydantic models (`IncidentTriageAction`).

---

## Scenario Data — Key Metrics

| Scenario | CPU % | Memory % | Services Affected | Deployments | Turns |
|---|---|---|---|---|---|
| `single_service_down` | 14 - 18 | 39 - 42 | 1 (auth-service) | 0 | 1 |
| `bad_deployment` | 58 - 63 | 57 - 61 | 3 (payment, order, email) | 1 (inventory-service) | 1 |
| `cascading_failure` T1 | 89 - 91 | 85 - 88 | 5 (api-gateway + 4 services) | 0 | 2 |
| `cascading_failure` T2 | 74 | 79 | 2 (order-service, postgres) | 0 | — |

---

## API Reference — 9 Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/reset` | Start a new episode. Accepts optional `task_name`. Returns first observation |
| `POST` | `/step` | Submit action (JSON). Returns reward (0.0 - 1.0), next observation, done flag |
| `GET` | `/state` | Current episode state — task, done, cumulative reward |
| `GET` | `/schema` | Full JSON schemas for Action and Observation models |
| `GET` | `/health` | Health check: `{"status": "ok"}` |
| `GET` | `/metadata` | Environment metadata — name, description, task list |
| `GET` | `/docs` | Interactive Swagger UI |
| `GET` | `/demo` | Interactive demo UI — manually reset tasks and submit actions |
| `GET` | `/scoreboard` | Runs deterministic oracle agent and displays scores |

### Example: Full Episode (Reset + Step)

```bash
# Start task 1
curl -X POST http://localhost:8000/reset \
  -H "Content-Type: application/json" \
  -d '{"task_name": "single_service_down"}'

# Submit perfect action -> reward: 1.0
curl -X POST http://localhost:8000/step \
  -H "Content-Type: application/json" \
  -d '{
    "severity": "high",
    "root_cause": "database",
    "first_action": "restart database and verify connectivity",
    "escalate": false
  }'
# -> {"reward": 1.0, "done": true, ...}
```

---

## Project Structure

```
incident_triage/
├── models.py                              # Pydantic Action, Observation, State models
├── client.py                              # HTTP/WebSocket client (IncidentTriageEnv)
├── openenv.yaml                           # OpenEnv metadata (name, tasks, tags)
├── pyproject.toml                         # Package config; entry point: uv run server
├── server/
│   ├── app.py                             # FastAPI app — 9 endpoints, 10 concurrent sessions
│   ├── incident_triage_environment.py     # Core: 3 scenarios, 6 variants, 4 graders, episode state
│   ├── demo.html                          # Interactive testing UI
│   ├── scoreboard.html                    # Oracle agent benchmark dashboard
│   └── Dockerfile                         # Multi-stage Docker build
├── tests/
│   ├── conftest.py                        # Offline test stubs (no openenv dependency needed)
│   └── test_incident_triage_environment.py # 7 unit tests covering all tasks + variants
└── inference.py                           # LLM inference runner (per-task scoring)

inference.py  (repo root)                  # Hackathon inference script with [START]/[STEP]/[END] logs
```

---

## Quick Start

### Run Locally

```bash
cd incident_triage
uv sync
uv run server
# Server at http://localhost:8000
# Swagger at http://localhost:8000/docs
# Demo UI at http://localhost:8000/demo
# Scoreboard at http://localhost:8000/scoreboard
```

### Run LLM Inference

```bash
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"
export HF_TOKEN="hf_..."
export ENV_URL="http://localhost:8000"

python inference.py
```

**Inference output format:**
```
[START] task=single_service_down env=incident_triage model=Qwen/Qwen2.5-72B-Instruct
[STEP]  step=1 action={...} reward=0.55 done=true error=null
[END]   success=true steps=1 score=0.550 rewards=0.55
```

### Run Tests

```bash
cd incident_triage
python -m pytest tests/ -v
# 7 tests: perfect scores, partial scores, penalty paths, multi-turn, variant rotation
```

### Docker (build & run manually)

```bash
cd incident_triage
docker build -t incident-triage:latest -f server/Dockerfile .
docker run -p 8000:8000 \
  -e API_BASE_URL=https://router.huggingface.co/v1 \
  -e MODEL_NAME=Qwen/Qwen2.5-72B-Instruct \
  -e HF_TOKEN=hf_... \
  incident-triage:latest
# HEALTHCHECK: curl http://localhost:8000/health every 30s
```

### Docker Compose (recommended for local dev)

```bash
cd incident_triage
# Optional: set env vars for LLM inference
export HF_TOKEN=hf_...
export MODEL_NAME=Qwen/Qwen2.5-72B-Instruct

docker compose up --build
# Server at http://localhost:8000
# Stop: docker compose down
```

### HuggingFace Space (live deployment)

The environment is deployed as a Docker container on HuggingFace Spaces. Any push to the repo triggers a rebuild:

```bash
# Push triggers HF to rebuild and redeploy the Docker container
git push origin master
# Live at: https://huggingface.co/spaces/radhakrishna1210/incident-triage
```

---

## Technical Design Decisions

| Decision | Rationale |
|---|---|
| **Stateful HTTP via module-level `_SHARED` dict** | OpenEnv creates fresh Environment instances per request. Module-level dict persists episode state across `/reset` and `/step` without external storage |
| **2 scenario variants per task (6 total)** | Logs and alert text alternate between runs — prevents models from overfitting to specific strings while keeping grading deterministic |
| **Keyword-based action grading** | Free-text `first_action` graded by presence of operational keywords (`restart`, `rollback`, `pool`, `deadlock`). Rewards domain-appropriate language without requiring exact matches |
| **Escalation as a scored boolean with penalties** | Escalation is not always correct. Contained failures should NOT be escalated (-0.15). Cascading failures SHOULD (+0.10). Tests calibrated judgment, not a bias toward caution |
| **Multi-turn only for Task 3** | Cascading failure naturally requires adaptation — system state changes after first intervention. Single-service and bad-deploy are one-shot diagnoses |
| **Cumulative reward capped at 1.0** | Prevents reward inflation on multi-turn tasks. Both turns must contribute meaningfully |
| **10 concurrent WebSocket sessions** | Parallel evaluation support for benchmarking multiple models simultaneously |

---

## OpenEnv Compliance

| Spec Requirement | Status | Implementation |
|---|---|---|
| Typed Observation model | Done | `IncidentTriageObservation` — 8 fields, Pydantic validated |
| Typed Action model | Done | `IncidentTriageAction` — 4 fields, Literal-constrained |
| Typed State model | Done | `IncidentTriageState` — episode_id, step_count, cumulative_reward |
| `step(action)` returns reward | Done | Returns observation, reward (0.0 - 1.0), done, info |
| `reset(task_name?)` | Done | Returns initial observation; auto-cycles if no name given |
| `state()` | Done | Returns current episode state |
| `openenv.yaml` | Done | Name, description, 5 tags, task list |
| HF Space deployment | Done | Docker SDK, `app_port: 8000`, tagged `openenv` |
| Dockerfile | Done | Multi-stage build, healthcheck, minimal runtime image |
| Inference script | Done | Structured `[START]/[STEP]/[END]` stdout logging |
| Unit tests | Done | 7 tests — perfect scores, penalties, multi-turn, variants |

---

## Numbers at a Glance

| Metric | Value |
|---|---|
| Tasks | **3** |
| Difficulty levels | **Easy, Medium, Hard** |
| Scenario variants | **6** (2 per task) |
| Max turns per episode | **2** (cascading_failure) |
| Observation fields | **8** |
| Action fields | **4** |
| Severity levels | **4** (low, medium, high, critical) |
| Root cause options | **5** (database, memory, network, bad_deploy, unknown) |
| Score range | **0.0 - 1.0** per task |
| Total possible score | **3.0** across all tasks |
| Scoring components | **4** (severity, root_cause, first_action, escalate) |
| Penalty range | **-0.10 to -0.15** for over-escalation |
| API endpoints | **9** |
| Concurrent sessions | **10** (WebSocket) |
| Unit tests | **7** |
| LLM baseline average | **0.717** |
| Oracle agent average | **1.000** |
| Docker healthcheck | Every **30s**, timeout **5s** |

---

## Built For

**OpenEnv Hackathon** — Meta x Scaler School of Technology

OpenEnv is a framework by Meta for building standardized AI evaluation environments. This submission puts LLMs through real-world SRE scenarios and scores their operational reasoning with deterministic, partial-credit reward functions.

**Team: Merge Conflict**
