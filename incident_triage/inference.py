#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Inference script for the Incident Triage environment.

Runs all three tasks in sequence using an LLM agent via an OpenAI-compatible
API endpoint and reports per-task reward scores.

Required environment variables:
  API_BASE_URL  — Base URL of the OpenAI-compatible inference endpoint
  MODEL_NAME    — Model identifier to pass to the API
  HF_TOKEN      — Bearer token (Hugging Face or other provider)
  ENV_URL       — Base URL of the running IncidentTriage env server
                  (default: http://localhost:8000)
"""

import json
import os
import re

from openai import OpenAI

try:
    from client import IncidentTriageEnv
    from models import IncidentTriageAction
except ImportError:
    from incident_triage.client import IncidentTriageEnv  # type: ignore[no-redef]
    from incident_triage.models import IncidentTriageAction  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE_URL = os.environ["API_BASE_URL"]
MODEL_NAME = os.environ["MODEL_NAME"]
HF_TOKEN = os.environ["HF_TOKEN"]
ENV_URL = os.environ.get("ENV_URL", "http://localhost:8000")

TASKS = ["single_service_down", "bad_deployment", "cascading_failure"]

SYSTEM_PROMPT = (
    "You are an expert SRE engineer doing incident triage.\n"
    "You will receive server logs and alerts.\n"
    "Respond ONLY with a JSON object with these exact fields:\n"
    "{\n"
    '  "severity": one of [low, medium, high, critical],\n'
    '  "root_cause": one of [database, memory, network, bad_deploy, unknown],\n'
    '  "first_action": string describing what you do first,\n'
    '  "escalate": true or false\n'
    "}\n"
    "No explanation. JSON only."
)

_FALLBACK_ACTION = IncidentTriageAction(
    severity="low",
    root_cause="unknown",
    first_action="no action",
    escalate=False,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

llm = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)


def _obs_to_prompt(obs) -> str:
    """Format an observation into a human-readable prompt for the LLM."""
    lines = ["=== Incident Report ==="]
    lines.append(f"Task: {obs.task_name}  |  Turn: {obs.turn}")
    lines.append(f"CPU: {obs.cpu_percent}%  |  Memory: {obs.memory_percent}%")
    if obs.services_affected:
        lines.append(f"Services DOWN: {', '.join(obs.services_affected)}")
    if obs.recent_deployments:
        lines.append(f"Recent deployments: {'; '.join(obs.recent_deployments)}")
    if obs.alerts:
        lines.append("\n--- Active Alerts ---")
        for alert in obs.alerts:
            lines.append(f"  * {alert}")
    if obs.logs:
        lines.append("\n--- Server Logs ---")
        for log in obs.logs:
            lines.append(f"  {log}")
    return "\n".join(lines)


def _call_llm(user_content: str) -> IncidentTriageAction:
    """Call the LLM and parse its response into an IncidentTriageAction."""
    response = llm.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.0,
        max_tokens=256,
    )
    raw = response.choices[0].message.content or ""

    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()

    try:
        data = json.loads(cleaned)
        action = IncidentTriageAction(
            severity=data["severity"],
            root_cause=data["root_cause"],
            first_action=str(data.get("first_action", "no action")),
            escalate=bool(data.get("escalate", False)),
        )
        return action
    except Exception as exc:
        print(f"  [WARN] Failed to parse LLM response ({exc!r}). Using fallback action.")
        return _FALLBACK_ACTION


def _run_task(env, task_name: str) -> float:
    """Run a single task to completion and return the final reward."""
    print(f"\n{'=' * 60}")
    print(f"Task: {task_name}")
    print("=" * 60)

    step_result = env.reset(task_name=task_name)
    obs = step_result.observation
    final_reward = 0.0

    # Episode loop — cascading_failure needs 2 turns; others need 1
    while True:
        prompt = _obs_to_prompt(obs)
        print(f"\n[Turn {obs.turn}] Querying LLM...")
        action = _call_llm(prompt)
        print(
            f"  severity={action.severity!r}  root_cause={action.root_cause!r}  "
            f"escalate={action.escalate}"
        )
        print(f"  first_action: {action.first_action}")

        result = env.step(action)
        final_reward = result.reward if result.reward is not None else 0.0
        print(f"  => reward: {final_reward:.3f}  done: {result.done}")

        if result.done:
            break

        obs = result.observation

    print(f"\nFinal score for '{task_name}': {final_reward:.3f}")
    return final_reward


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    scores: dict[str, float] = {}

    async_env = IncidentTriageEnv(base_url=ENV_URL)
    with async_env.sync() as env:
        for task_name in TASKS:
            scores[task_name] = _run_task(env, task_name)

    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    total = 0.0
    for task, score in scores.items():
        print(f"  {task:<30} {score:.3f}")
        total += score
    print(f"  {'AVERAGE':<30} {total / len(scores):.3f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
