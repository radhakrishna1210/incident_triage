# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Incident Triage Environment Implementation.

A DevOps incident response environment where an agent must diagnose
and triage realistic production incidents across three tasks of
increasing difficulty.
"""

import pathlib
from copy import deepcopy
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import EnvironmentMetadata

try:
    from ..models import IncidentTriageAction, IncidentTriageObservation, IncidentTriageState
except (ImportError, ModuleNotFoundError):
    from models import IncidentTriageAction, IncidentTriageObservation, IncidentTriageState

_README_PATH = pathlib.Path(__file__).parent.parent / "README.md"


# ---------------------------------------------------------------------------
# Shared state for HTTP REST endpoints
#
# The openenv HTTP server creates a fresh Environment instance per request,
# so /reset and /step would otherwise never share state.  This dict lives at
# module level and is loaded/saved on every reset() / step() call, making the
# HTTP REST API stateful for single-user development use.
# ---------------------------------------------------------------------------

_SHARED: dict = {
    "task_cycle_index": 0,
    "current_task": "",
    "current_turn": 0,
    "cumulative_reward": 0.0,
    "state": None,
    "task_variant_counter": {},
}


# ---------------------------------------------------------------------------
# Static scenario data
# ---------------------------------------------------------------------------

_TASK_ORDER = ["single_service_down", "bad_deployment", "cascading_failure"]

_INITIAL_OBS_VARIANTS: dict[str, list[dict]] = {
    "single_service_down": [
        dict(
        logs=[
            "[02:14:11] ERROR auth-service: connection refused port 5432",
            "[02:14:12] ERROR auth-service: health check failed (attempt 1/3)",
            "[02:14:15] ERROR auth-service: health check failed (attempt 2/3)",
            "[02:14:18] CRITICAL auth-service: health check failed (attempt 3/3)",
            "[02:14:19] ALERT auth-service marked as DOWN",
        ],
        alerts=["auth-service DOWN for 2 minutes"],
        cpu_percent=14.0,
        memory_percent=42.0,
        services_affected=["auth-service"],
        recent_deployments=[],
        task_name="single_service_down",
        turn=0,
    ),
        dict(
        logs=[
            "[02:17:11] ERROR auth-service: DB connect timeout 5432",
            "[02:17:12] WARN auth-service: readiness probe failed",
            "[02:17:15] WARN auth-service: readiness probe failed",
            "[02:17:18] CRITICAL auth-service: instance unhealthy",
            "[02:17:19] ALERT auth-service unavailable",
        ],
        alerts=["auth-service unavailable for 90s"],
        cpu_percent=18.0,
        memory_percent=39.0,
        services_affected=["auth-service"],
        recent_deployments=[],
        task_name="single_service_down",
        turn=0,
    ),
    ],
    "bad_deployment": [
        dict(
        logs=[
            "[03:22:01] INFO inventory-service: deployed v2.3.1",
            "[03:22:45] WARN payment-service: upstream timeout (inventory)",
            "[03:23:01] ERROR payment-service: 503 from inventory-service",
            "[03:23:10] WARN email-service: queue backed up (4200 items)",
            "[03:23:15] ERROR order-service: failed to confirm inventory",
            "[03:23:20] ALERT 3 services degraded",
            "[03:23:21] INFO auth-service: healthy",
            "[03:23:22] INFO user-service: healthy",
        ],
        alerts=["payment-service degraded", "order-service degraded", "email-service queue critical"],
        cpu_percent=58.0,
        memory_percent=61.0,
        services_affected=["payment-service", "order-service", "email-service"],
        recent_deployments=["inventory-service v2.3.1 deployed 3 mins ago"],
        task_name="bad_deployment",
        turn=0,
    ),
        dict(
        logs=[
            "[03:40:01] INFO inventory-service: rollout started v2.4.0",
            "[03:41:06] WARN payment-service: upstream latency spike inventory-service",
            "[03:41:21] ERROR order-service: inventory dependency returned 503",
            "[03:41:24] ERROR email-service: queue processing blocked by inventory sync",
            "[03:41:26] ALERT 3 downstream services degraded",
            "[03:41:27] INFO auth-service: healthy",
        ],
        alerts=["order-service degraded", "payment-service degraded", "email-service lag high"],
        cpu_percent=63.0,
        memory_percent=57.0,
        services_affected=["payment-service", "order-service", "email-service"],
        recent_deployments=["inventory-service v2.4.0 deployed 2 mins ago"],
        task_name="bad_deployment",
        turn=0,
    ),
    ],
    "cascading_failure": [
        dict(
        logs=[
            "[04:01:00] CRITICAL api-gateway: error rate 67%",
            "[04:01:01] ERROR auth-service: DB connection timeout",
            "[04:01:01] ERROR payment-service: DB connection timeout",
            "[04:01:02] ERROR order-service: DB connection timeout",
            "[04:01:03] CRITICAL postgres-primary: max_connections=500 reached",
            "[04:01:04] ERROR payment-service: pq: too many clients",
            "[04:01:05] WARN k8s: pod payment-service restarting (attempt 2)",
            "[04:01:06] ALERT SLO breach: error_rate=0.67 threshold=0.01",
        ],
        alerts=["api-gateway SLO breach", "postgres connection pool full", "3 services timing out"],
        cpu_percent=91.0,
        memory_percent=88.0,
        services_affected=["api-gateway", "auth-service", "payment-service", "order-service", "postgres-primary"],
        recent_deployments=[],
        task_name="cascading_failure",
        turn=0,
    ),
        dict(
        logs=[
            "[04:11:00] CRITICAL edge-gateway: 5xx rate 61%",
            "[04:11:01] ERROR auth-service: database timeout",
            "[04:11:01] ERROR order-service: waiting for postgres client",
            "[04:11:02] ERROR payment-service: unable to acquire DB handle",
            "[04:11:03] CRITICAL postgres-primary: max_connections limit reached",
            "[04:11:04] ALERT global SLO breach detected",
        ],
        alerts=["edge-gateway SLO breach", "postgres saturation", "multiple services timing out"],
        cpu_percent=89.0,
        memory_percent=85.0,
        services_affected=["edge-gateway", "auth-service", "payment-service", "order-service", "postgres-primary"],
        recent_deployments=[],
        task_name="cascading_failure",
        turn=0,
    ),
    ],
}

_CASCADING_TURN2_OBS = dict(
    logs=[
        "[04:01:10] INFO You increased DB connection pool to 1000",
        "[04:01:11] WARN postgres-primary: connections now 820/1000",
        "[04:01:12] INFO payment-service: reconnecting...",
        "[04:01:13] INFO auth-service: reconnecting...",
        "[04:01:14] ERROR order-service: still timing out",
        "[04:01:15] WARN api-gateway: error rate now 31%",
        "[04:01:16] ERROR order-service: query taking 45s (deadlock?)",
    ],
    alerts=["order-service still degraded", "possible deadlock detected"],
    cpu_percent=74.0,
    memory_percent=79.0,
    services_affected=["order-service", "postgres-primary"],
    recent_deployments=[],
    task_name="cascading_failure",
    turn=1,
)


# ---------------------------------------------------------------------------
# Graders
# ---------------------------------------------------------------------------

_REWARD_FLOOR = 0.01
_REWARD_CEIL = 0.99


def _clamp(score: float) -> float:
    """Clamp reward to the open interval (0, 1) as required by the OpenEnv spec."""
    return max(_REWARD_FLOOR, min(_REWARD_CEIL, score))


def _grade_single_service_down(action: IncidentTriageAction) -> float:
    score = 0.0
    if action.severity == "high":
        score += 0.35
    if action.root_cause == "database":
        score += 0.35
    fa = action.first_action.lower()
    if ("restart" in fa or "reconnect" in fa) and (
        "database" in fa or "db" in fa or "postgres" in fa
    ):
        score += 0.20
    if action.escalate is False:
        score += 0.10
    if action.escalate is True:
        score -= 0.15
    return _clamp(score)


def _grade_bad_deployment(action: IncidentTriageAction) -> float:
    score = 0.0
    if action.severity == "high":
        score += 0.35
    if action.root_cause == "bad_deploy":
        score += 0.35
    fa = action.first_action.lower()
    if "rollback" in fa or "roll back" in fa or "revert" in fa:
        score += 0.20
    if action.escalate is False:
        score += 0.10
    if action.escalate is True:
        score -= 0.10
    return _clamp(score)


def _grade_cascading_turn1(action: IncidentTriageAction) -> float:
    score = 0.0
    if action.severity == "critical":
        score += 0.20
    if action.root_cause == "database":
        score += 0.20
    fa = action.first_action.lower()
    if "connection" in fa or "pool" in fa or "max_connections" in fa:
        score += 0.10
    if action.escalate is True:
        score += 0.10
    return _clamp(score)


def _grade_cascading_turn2(action: IncidentTriageAction) -> float:
    score = 0.0
    if action.root_cause == "database":
        score += 0.25
    fa = action.first_action.lower()
    if "deadlock" in fa or "order" in fa:
        score += 0.25
    if action.severity in ("high", "critical"):
        score += 0.10
    return _clamp(score)


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

class IncidentTriageEnvironment(Environment):
    """DevOps incident triage environment with three production-style scenarios."""

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self) -> None:
        self._task_cycle_index: int = _SHARED["task_cycle_index"]
        self._current_task: str = _SHARED["current_task"]
        self._current_turn: int = _SHARED["current_turn"]
        self._cumulative_reward: float = _SHARED["cumulative_reward"]
        self._state: IncidentTriageState = _SHARED["state"] or IncidentTriageState()
        self._task_variant_counter: dict[str, int] = _SHARED["task_variant_counter"] or {}

    def _persist(self) -> None:
        """Write instance state back to the module-level shared dict."""
        _SHARED["task_cycle_index"] = self._task_cycle_index
        _SHARED["current_task"] = self._current_task
        _SHARED["current_turn"] = self._current_turn
        _SHARED["cumulative_reward"] = self._cumulative_reward
        _SHARED["state"] = self._state
        _SHARED["task_variant_counter"] = self._task_variant_counter

    def _initial_obs_for_task(self, task_name: str) -> dict:
        variants = _INITIAL_OBS_VARIANTS[task_name]
        idx = self._task_variant_counter.get(task_name, 0) % len(variants)
        self._task_variant_counter[task_name] = self._task_variant_counter.get(task_name, 0) + 1
        return deepcopy(variants[idx])

    def get_metadata(self) -> EnvironmentMetadata:
        readme = _README_PATH.read_text(encoding="utf-8") if _README_PATH.exists() else None
        return EnvironmentMetadata(
            name="incident_triage",
            description=(
                "DevOps Incident Response Triage environment. An AI agent acts as an "
                "on-call SRE engineer — reads server logs and alerts, then diagnoses "
                "severity, root cause, and first response action."
            ),
            readme_content=readme,
            version="1.0.0",
            author="OpenEnv / Mission Bangalore",
            documentation_url="https://github.com/meta-pytorch/OpenEnv",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self, task_name: str | None = None) -> IncidentTriageObservation:
        """Reset the environment, optionally selecting a specific task."""
        if task_name is None:
            task_name = _TASK_ORDER[self._task_cycle_index % len(_TASK_ORDER)]
            self._task_cycle_index += 1

        if task_name not in _INITIAL_OBS_VARIANTS:
            raise ValueError(f"Unknown task: {task_name!r}. Choose from {_TASK_ORDER}")

        self._current_task = task_name
        self._current_turn = 0
        self._cumulative_reward = 0.0
        self._state = IncidentTriageState(
            episode_id=str(uuid4()),
            step_count=0,
            task_name=task_name,
            done=False,
            cumulative_reward=0.0,
        )

        obs = IncidentTriageObservation(**self._initial_obs_for_task(task_name), done=False, reward=None)
        self._persist()
        return obs

    def step(self, action: IncidentTriageAction) -> IncidentTriageObservation:  # type: ignore[override]
        """Grade the agent's action and advance the episode."""
        if self._state.done:
            raise RuntimeError("Episode is already done. Call reset() to start a new episode.")

        turn_reward, episode_done = self._grade(action)
        self._cumulative_reward = min(_REWARD_CEIL, self._cumulative_reward + turn_reward)
        self._current_turn += 1
        self._state = IncidentTriageState(
            episode_id=self._state.episode_id,
            step_count=self._current_turn,
            task_name=self._current_task,
            done=episode_done,
            cumulative_reward=self._cumulative_reward,
        )

        self._persist()

        # Multi-turn: return the turn-2 observation after turn 1 of cascading_failure
        if self._current_task == "cascading_failure" and not episode_done:
            return IncidentTriageObservation(
                **_CASCADING_TURN2_OBS,
                done=False,
                reward=turn_reward,
            )

        # Terminal observation for all completed episodes
        return IncidentTriageObservation(
            logs=[],
            alerts=[],
            cpu_percent=0.0,
            memory_percent=0.0,
            services_affected=[],
            recent_deployments=[],
            task_name=self._current_task,
            turn=self._current_turn,
            done=True,
            reward=self._cumulative_reward,
        )

    @property
    def state(self) -> IncidentTriageState:  # type: ignore[override]
        """Return the current episode state."""
        return self._state

    # ------------------------------------------------------------------
    # Internal grading dispatch
    # ------------------------------------------------------------------

    def _grade(self, action: IncidentTriageAction) -> tuple[float, bool]:
        """Return (turn_reward, episode_done) for the current task and turn."""
        task = self._current_task
        turn = self._current_turn  # 0-indexed, before increment

        if task == "single_service_down":
            return _grade_single_service_down(action), True

        if task == "bad_deployment":
            return _grade_bad_deployment(action), True

        if task == "cascading_failure":
            if turn == 0:
                return _grade_cascading_turn1(action), False
            else:
                return _grade_cascading_turn2(action), True

        raise ValueError(f"Unknown task: {task!r}")
