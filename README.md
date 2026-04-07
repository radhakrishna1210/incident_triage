# Incident Triage OpenEnv Environment

This repository contains a Meta OpenEnv-style RL environment for incident response triage.

An agent plays the role of an on-call SRE and must:
- read logs + alerts,
- estimate incident severity,
- identify root cause,
- choose the best immediate action,
- decide whether to escalate.

The environment is designed for the Meta x OpenEnv hackathon Round 1 requirement: a mini RL environment with clear tasks, grading, and reward logic.

## What Is Already Implemented

- OpenEnv-compatible environment API (`reset`, `step`, state tracking)
- 3 graded tasks: `single_service_down`, `bad_deployment`, `cascading_failure`
- multi-turn scenario support (`cascading_failure` has 2 turns)
- deterministic reward functions for each task
- FastAPI/OpenEnv server wrapper for local and Docker execution
- inference script to benchmark LLMs against the environment

Core code lives in `incident_triage/`.

## Repo Layout

- `incident_triage/server/incident_triage_environment.py`: task scenarios + graders + episode logic
- `incident_triage/models.py`: typed action/observation/state schemas
- `incident_triage/server/app.py`: HTTP server app creation
- `incident_triage/inference.py`: LLM evaluation runner
- `incident_triage/openenv.yaml`: environment metadata
- `incident_triage/README.md`: detailed environment/task documentation

## Quick Start

```bash
cd incident_triage
pip install "openenv-core[core]>=0.2.2"
uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload
```

- Web UI: `http://localhost:8000/web`
- API docs: `http://localhost:8000/docs`

## Hackathon Alignment

This project aligns with the challenge expectation to build a mini RL environment with:
- explicit task definitions,
- programmatic grading,
- reward-based evaluation,
- reproducible local execution.

For deeper details on tasks, scores, and runtime usage, see `incident_triage/README.md`.
