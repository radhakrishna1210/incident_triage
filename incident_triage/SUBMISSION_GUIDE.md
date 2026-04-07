# Incident Triage - Hackathon Submission Guide

This document is a practical checklist for making the project submission-ready for Meta x OpenEnv hackathon judging.

## What Judges Expect (Round 1)

Round 1 asks for a mini RL environment with:
- clear task definitions,
- deterministic grader and reward logic,
- reproducible execution,
- measurable agent performance.

Reference: [Scaler hackathon page](https://www.scaler.com/school-of-technology/meta-pytorch-hackathon)

## Current Status in This Repo

- Environment API implemented (`reset`, `step`, typed state)
- 3 tasks implemented (`single_service_down`, `bad_deployment`, `cascading_failure`)
- reward functions implemented for each task
- multi-turn logic implemented for cascading failure
- local + Docker execution available
- baseline evaluation script available (`inference.py`)

## Run Locally

```bash
cd incident_triage
pip install -e ".[dev]"
pip install "openenv-core[core]>=0.2.2"
pytest -q
uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload
```

## Run Baseline Inference

```bash
cd incident_triage
export API_BASE_URL="https://api-inference.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"
export HF_TOKEN="hf_..."
export ENV_URL="http://localhost:8000"
python inference.py
```

## Submission Checklist

- [ ] README clearly explains environment objective and tasks
- [ ] `incident_triage/README.md` includes action/observation schemas + reward table
- [ ] tests pass locally (`pytest -q`)
- [ ] server runs locally (`uvicorn server.app:app`)
- [ ] Docker image builds (`docker build -t incident-triage:latest -f server/Dockerfile .`)
- [ ] baseline score output attached in submission notes
- [ ] no virtualenv or build artifacts tracked in git

## How To Improve Winning Chances

- Add more task variants per scenario (log template permutations)
- Add robustness tests for tricky wording/synonyms in `first_action`
- Tune system prompt in `inference.py` to reduce over-escalation
- Record before/after benchmark table for every prompt change
- Keep reward design aligned with real-world SRE priorities (fast recovery + correct escalation)

## Useful Links

- Hackathon details: [Scaler Meta x OpenEnv page](https://www.scaler.com/school-of-technology/meta-pytorch-hackathon)
- OpenEnv resources: [openenv-course](https://github.com/huggingface/openenv-course)
