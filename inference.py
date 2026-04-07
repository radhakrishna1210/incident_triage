#!/usr/bin/env python3
"""
Inference Script for Incident Triage Environment
===================================

MANDATORY - Before submitting, ensure the following variables are defined
in your environment configuration:

  API_BASE_URL   The API endpoint for the LLM.
  MODEL_NAME     The model identifier to use for inference.
  HF_TOKEN       Your Hugging Face / API key.
  LOCAL_IMAGE_NAME  The name of the local Docker image for the environment
                    (used with from_docker_image(); omit to connect via ENV_URL).

STDOUT FORMAT
  The script emits exactly three line types to stdout:

  [START] task=<task_name> env=<benchmark> model=<model_name>
  [STEP]  step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
  [END]   success=<true|false> steps=<n> score=<0.000> rewards=<r1,r2,...,rn>

Rules:
  - One [START] line at episode begin.
  - One [STEP] line per step, immediately after env.step() returns.
  - One [END] line after the task completes, always emitted (even on exception).
  - reward and rewards are formatted to 2 decimal places.
  - done and success are lowercase booleans: true or false.
  - error is the raw error string, or null if none.
  - All fields on a single line with no newlines within a line.
  - Each task should return score in [0, 1].
"""

import asyncio
import json
import os
import re
import textwrap
from typing import List, Optional

from openai import OpenAI

from incident_triage.client import IncidentTriageEnv
from incident_triage.models import IncidentTriageAction

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY")
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME") or os.getenv("IMAGE_NAME")
ENV_URL = os.getenv("ENV_URL", "http://localhost:8000")

BENCHMARK = "incident_triage"
TASKS = ["single_service_down", "bad_deployment", "cascading_failure"]

SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert SRE engineer doing incident triage.
    You will receive server logs and alerts.
    Prioritize root-cause precision and calibrated escalation.
    Escalate=true only for broad/sev1 incidents or unclear containment.
    If a recent deployment strongly correlates with breakage, prefer bad_deploy and rollback.
    Use concise first_action text with operational keywords (restart/reconnect/rollback/pool/deadlock).
    Respond ONLY with a JSON object with these exact fields:
    {
      "severity": one of [low, medium, high, critical],
      "root_cause": one of [database, memory, network, bad_deploy, unknown],
      "first_action": string describing what you do first,
      "escalate": true or false
    }
    No explanation. JSON only.
""").strip()

_FALLBACK_ACTION = IncidentTriageAction(
    severity="low",
    root_cause="unknown",
    first_action="no action",
    escalate=False,
)


# ---------------------------------------------------------------------------
# Structured stdout logging — [START] / [STEP] / [END]
# ---------------------------------------------------------------------------

def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

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


def _call_llm(client: OpenAI, user_content: str) -> IncidentTriageAction:
    """Call the LLM and parse its JSON response into an IncidentTriageAction."""
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.0,
        max_tokens=256,
    )
    raw = response.choices[0].message.content or ""
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()

    try:
        data = json.loads(cleaned)
        return IncidentTriageAction(
            severity=data["severity"],
            root_cause=data["root_cause"],
            first_action=str(data.get("first_action", "no action")),
            escalate=bool(data.get("escalate", False)),
        )
    except Exception as exc:
        print(f"[DEBUG] Failed to parse LLM response ({exc!r}). Using fallback.", flush=True)
        return _FALLBACK_ACTION


def _action_to_str(action: IncidentTriageAction) -> str:
    """Compact JSON representation of an action for the [STEP] log line."""
    return json.dumps(
        {
            "severity": action.severity,
            "root_cause": action.root_cause,
            "first_action": action.first_action,
            "escalate": action.escalate,
        },
        separators=(",", ":"),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    llm = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    if IMAGE_NAME:
        env = await IncidentTriageEnv.from_docker_image(IMAGE_NAME)
    else:
        env = IncidentTriageEnv(base_url=ENV_URL)

    try:
        for task in TASKS:
            rewards: List[float] = []
            steps_taken = 0
            score = 0.0
            success = False

            log_start(task=task, env=BENCHMARK, model=MODEL_NAME)

            try:
                result = await env.reset(task_name=task)
                obs = result.observation

                while not result.done:
                    step_num = steps_taken + 1
                    prompt = _obs_to_prompt(obs)
                    action = _call_llm(llm, prompt)
                    action_str = _action_to_str(action)

                    result = await env.step(action)
                    reward = result.reward if result.reward is not None else 0.0
                    done = result.done
                    error = None

                    rewards.append(reward)
                    steps_taken = step_num

                    log_step(
                        step=step_num,
                        action=action_str,
                        reward=reward,
                        done=done,
                        error=error,
                    )

                    if done:
                        break
                    obs = result.observation

                # Final score is the last reward (cumulative for multi-turn tasks)
                score = rewards[-1] if rewards else 0.0
                score = min(max(score, 0.0), 1.0)
                success = score >= 0.5

            except Exception as exc:
                print(f"[DEBUG] Task {task} error: {exc}", flush=True)

            finally:
                log_end(
                    success=success,
                    steps=steps_taken,
                    score=score,
                    rewards=rewards,
                )

    finally:
        try:
            await env.close()
        except Exception as e:
            print(f"[DEBUG] env.close() error: {e}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
