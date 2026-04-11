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

API_BASE_URL = os.environ.get("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
HF_TOKEN = os.environ.get("HF_TOKEN", "")
ENV_URL = os.environ.get("ENV_URL", "http://localhost:8000")

TASKS = ["single_service_down", "bad_deployment", "cascading_failure"]

SYSTEM_PROMPT = (
    "You are an expert SRE engineer doing incident triage.\n"
    "You will receive server logs, alerts, CPU/memory metrics, and affected services.\n"
    "Analyze carefully and respond ONLY with a JSON object with these exact fields:\n"
    "{\n"
    '  "severity": one of [low, medium, high, critical],\n'
    '  "root_cause": one of [database, memory, network, bad_deploy, unknown],\n'
    '  "first_action": string describing the first remediation step,\n'
    '  "escalate": true or false\n'
    "}\n"
    "Decision rules:\n"
    "- If logs show DB connection refused / timeout / max_connections → root_cause=database\n"
    "- If a recent deployment correlates with service degradation → root_cause=bad_deploy\n"
    "- severity=high for single-service or contained failures; severity=critical for SLO breaches or multi-service cascades\n"
    "- escalate=false for contained issues you can fix (DB restart, rollback); escalate=true for broad multi-service SEV1 incidents\n"
    "- For DB connection failures: first_action MUST include 'restart' or 'reconnect' AND 'database' or 'postgres' or 'db'\n"
    "  Example: 'restart database connection pool and verify postgres connectivity'\n"
    "- For bad deployments: first_action MUST include 'rollback' or 'revert'\n"
    "  Example: 'rollback inventory-service to previous version'\n"
    "- For cascading DB failures (turn 1): first_action MUST include 'connection pool' or 'max_connections'\n"
    "  Example: 'increase postgres connection pool limit and escalate to on-call'\n"
    "- For cascading DB failures (turn 2, deadlock): first_action MUST include 'deadlock' or 'order-service'\n"
    "  Example: 'kill deadlock query in order-service and restart the service'\n"
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

llm: OpenAI | None = None


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
    response = llm.chat.completions.create(  # type: ignore[union-attr]
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
    print(f"[START] task={task_name} env=incident_triage model={MODEL_NAME}", flush=True)

    step_result = env.reset(task_name=task_name)
    obs = step_result.observation
    final_reward = 0.0
    step_num = 0
    all_rewards: list[float] = []

    # Episode loop — cascading_failure needs 2 turns; others need 1
    while True:
        prompt = _obs_to_prompt(obs)
        action = _call_llm(prompt)
        action_str = (
            f'{{"severity":"{action.severity}",'
            f'"root_cause":"{action.root_cause}",'
            f'"first_action":"{action.first_action}",'
            f'"escalate":{str(action.escalate).lower()}}}'
        )

        result = env.step(action)
        step_num += 1
        turn_reward = result.reward if result.reward is not None else 0.0
        final_reward = turn_reward
        all_rewards.append(turn_reward)
        done_str = "true" if result.done else "false"
        print(
            f"[STEP] step={step_num} action={action_str} reward={turn_reward:.2f}"
            f" done={done_str} error=null",
            flush=True,
        )

        if result.done:
            break

        obs = result.observation

    rewards_str = ",".join(f"{r:.2f}" for r in all_rewards)
    success_str = "true" if final_reward > 0.0 else "false"
    print(
        f"[END] success={success_str} steps={step_num} score={final_reward:.2f}"
        f" rewards={rewards_str}",
        flush=True,
    )
    return final_reward


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    global llm
    llm = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

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
