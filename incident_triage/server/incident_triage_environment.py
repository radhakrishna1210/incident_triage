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

from uuid import uuid4

from openenv.core.env_server.interfaces import Environment

try:
    from ..models import IncidentTriageAction, IncidentTriageObservation, IncidentTriageState
except (ImportError, ModuleNotFoundError):
    from models import IncidentTriageAction, IncidentTriageObservation, IncidentTriageState


# ---------------------------------------------------------------------------
# Static scenario data
# ---------------------------------------------------------------------------

_TASK_ORDER = ["single_service_down", "bad_deployment", "cascading_failure"]

_INITIAL_OBS: dict[str, dict] = {
    "single_service_down": dict(
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
    "bad_deployment": dict(
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
    "cascading_failure": dict(
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

def _grade_single_service_down(action: IncidentTriageAction) -> float:
    score = 0.0
    if action.severity == "high":
        score += 0.35
    if action.root_cause == "database":
        score += 0.35
    fa = action.first_action.lower()
    if "restart" in fa and "database" in fa:
        score += 0.20
    if action.escalate is False:
        score += 0.10
    if action.escalate is True:
        score -= 0.15
    return max(0.0, min(1.0, score))


def _grade_bad_deployment(action: IncidentTriageAction) -> float:
    score = 0.0
    if action.severity == "high":
        score += 0.35
    if action.root_cause == "bad_deploy":
        score += 0.35
    if "rollback" in action.first_action.lower():
        score += 0.20
    if action.escalate is False:
        score += 0.10
    if action.escalate is True:
        score -= 0.10
    return max(0.0, min(1.0, score))


def _grade_cascading_turn1(action: IncidentTriageAction) -> float:
    score = 0.0
    if action.severity == "critical":
        score += 0.20
    if action.root_cause == "database":
        score += 0.20
    fa = action.first_action.lower()
    if "connection" in fa or "pool" in fa:
        score += 0.10
    if action.escalate is True:
        score += 0.10
    return max(0.0, min(1.0, score))


def _grade_cascading_turn2(action: IncidentTriageAction) -> float:
    score = 0.0
    if action.root_cause == "database":
        score += 0.25
    fa = action.first_action.lower()
    if "deadlock" in fa or "order" in fa:
        score += 0.25
    if action.severity in ("high", "critical"):
        score += 0.10
    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

class IncidentTriageEnvironment(Environment):
    """DevOps incident triage environment with three production-style scenarios."""

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self) -> None:
        self._task_cycle_index: int = 0
        self._current_task: str = ""
        self._current_turn: int = 0
        self._cumulative_reward: float = 0.0
        self._state = IncidentTriageState()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self, task_name: str | None = None) -> IncidentTriageObservation:
        """Reset the environment, optionally selecting a specific task."""
        if task_name is None:
            task_name = _TASK_ORDER[self._task_cycle_index % len(_TASK_ORDER)]
            self._task_cycle_index += 1

        if task_name not in _INITIAL_OBS:
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

        return IncidentTriageObservation(
            **_INITIAL_OBS[task_name],
            done=False,
            reward=0.0,
        )

    def step(self, action: IncidentTriageAction) -> IncidentTriageObservation:  # type: ignore[override]
        """Grade the agent's action and advance the episode."""
        if self._state.done:
            raise RuntimeError("Episode is already done. Call reset() to start a new episode.")

        turn_reward, episode_done = self._grade(action)
        self._cumulative_reward = min(1.0, self._cumulative_reward + turn_reward)
        self._current_turn += 1
        self._state = IncidentTriageState(
            episode_id=self._state.episode_id,
            step_count=self._current_turn,
            task_name=self._current_task,
            done=episode_done,
            cumulative_reward=self._cumulative_reward,
        )

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
