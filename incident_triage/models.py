# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Data models for the Incident Triage DevOps environment."""

from typing import Literal

from openenv.core.env_server.types import Action, Observation, State
from pydantic import Field


class IncidentTriageObservation(Observation):
    """Current snapshot of the system state presented to the agent."""

    logs: list[str] = Field(default_factory=list, description="Server log lines")
    alerts: list[str] = Field(default_factory=list, description="Active alert strings")
    cpu_percent: float = Field(default=0.0, description="Current CPU utilisation (0–100)")
    memory_percent: float = Field(default=0.0, description="Current memory utilisation (0–100)")
    services_affected: list[str] = Field(default_factory=list, description="Names of services currently down")
    recent_deployments: list[str] = Field(default_factory=list, description="Recent deployment events")
    turn: int = Field(default=0, description="Current turn number within the episode")
    task_name: str = Field(default="", description="Identifier for the active triage scenario")


class IncidentTriageAction(Action):
    """Agent decision: diagnosis and immediate response for an active incident."""

    severity: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="Agent's assessed severity of the incident"
    )
    root_cause: Literal["database", "memory", "network", "bad_deploy", "unknown"] = Field(
        ..., description="Agent's identified root cause"
    )
    first_action: str = Field(..., description="First remediation step the agent takes")
    escalate: bool = Field(..., description="Whether to page the on-call team")


class IncidentTriageState(State):
    """Internal environment state tracking episode progress and accumulated reward."""

    task_name: str = Field(default="", description="Name of the current triage scenario")
    done: bool = Field(default=False, description="Whether the episode has ended")
    cumulative_reward: float = Field(default=0.0, description="Total reward accumulated so far")
