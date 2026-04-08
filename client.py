# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Incident Triage Environment Client."""

from typing import Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult
try:
    from .models import IncidentTriageAction, IncidentTriageObservation, IncidentTriageState
except ImportError:
    from models import IncidentTriageAction, IncidentTriageObservation, IncidentTriageState  # type: ignore[no-redef]


class IncidentTriageEnv(
    EnvClient[IncidentTriageAction, IncidentTriageObservation, IncidentTriageState]
):
    """
    Client for the Incident Triage Environment.

    This client maintains a persistent WebSocket connection to the environment server,
    enabling efficient multi-step interactions with lower latency.
    Each client instance has its own dedicated environment session on the server.

    Example:
        >>> # Connect to a running server
        >>> with IncidentTriageEnv(base_url="http://localhost:8000") as client:
        ...     result = client.reset()
        ...     print(result.observation.echoed_message)
        ...
        ...     result = client.step(IncidentTriageAction(message="Hello!"))
        ...     print(result.observation.echoed_message)

    Example with Docker:
        >>> # Automatically start container and connect
        >>> client = IncidentTriageEnv.from_docker_image("incident_triage-env:latest")
        >>> try:
        ...     result = client.reset()
        ...     result = client.step(IncidentTriageAction(message="Test"))
        ... finally:
        ...     client.close()
    """

    def _step_payload(self, action: IncidentTriageAction) -> Dict:
        """
        Convert IncidentTriageAction to JSON payload for step message.

        Args:
            action: IncidentTriageAction instance

        Returns:
            Dictionary representation suitable for JSON encoding
        """
        return {
            "severity": action.severity,
            "root_cause": action.root_cause,
            "first_action": action.first_action,
            "escalate": action.escalate,
        }

    def _parse_result(self, payload: Dict) -> StepResult[IncidentTriageObservation]:
        """
        Parse server response into StepResult[IncidentTriageObservation].

        Args:
            payload: JSON response data from server

        Returns:
            StepResult with IncidentTriageObservation
        """
        obs_data = payload.get("observation", {})
        observation = IncidentTriageObservation(
            logs=obs_data.get("logs", []),
            alerts=obs_data.get("alerts", []),
            cpu_percent=obs_data.get("cpu_percent", 0.0),
            memory_percent=obs_data.get("memory_percent", 0.0),
            services_affected=obs_data.get("services_affected", []),
            recent_deployments=obs_data.get("recent_deployments", []),
            turn=obs_data.get("turn", 0),
            task_name=obs_data.get("task_name", ""),
            done=payload.get("done", False),
            reward=payload.get("reward"),
            metadata=obs_data.get("metadata", {}),
        )

        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict) -> IncidentTriageState:
        """
        Parse server response into IncidentTriageState.

        Args:
            payload: JSON response from state request

        Returns:
            IncidentTriageState with episode tracking fields
        """
        return IncidentTriageState(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
            task_name=payload.get("task_name", ""),
            done=payload.get("done", False),
            cumulative_reward=payload.get("cumulative_reward", 0.0),
        )
