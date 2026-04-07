import pytest

try:
    from incident_triage.models import IncidentTriageAction
    from incident_triage.server.incident_triage_environment import IncidentTriageEnvironment
except ImportError:
    from models import IncidentTriageAction
    from server.incident_triage_environment import IncidentTriageEnvironment


def _action(severity: str, root_cause: str, first_action: str, escalate: bool) -> IncidentTriageAction:
    return IncidentTriageAction(
        severity=severity,
        root_cause=root_cause,
        first_action=first_action,
        escalate=escalate,
    )


def test_single_service_down_perfect_score() -> None:
    env = IncidentTriageEnvironment()
    env.reset(task_name="single_service_down")
    result = env.step(
        _action(
            severity="high",
            root_cause="database",
            first_action="restart database and verify connectivity",
            escalate=False,
        )
    )

    assert result.done is True
    assert result.reward == pytest.approx(1.0)


def test_bad_deployment_partial_score_with_escalation_penalty() -> None:
    env = IncidentTriageEnvironment()
    env.reset(task_name="bad_deployment")
    result = env.step(
        _action(
            severity="high",
            root_cause="bad_deploy",
            first_action="rollback inventory-service to previous version",
            escalate=True,
        )
    )

    # +0.35 severity +0.35 root cause +0.20 rollback -0.10 escalation
    assert result.done is True
    assert result.reward == pytest.approx(0.8)


def test_cascading_failure_is_two_turn_episode() -> None:
    env = IncidentTriageEnvironment()
    first_obs = env.reset(task_name="cascading_failure")
    assert first_obs.turn == 0

    turn1 = env.step(
        _action(
            severity="critical",
            root_cause="database",
            first_action="increase connection pool to reduce timeouts",
            escalate=True,
        )
    )
    assert turn1.done is False
    assert turn1.turn == 1
    assert turn1.reward == pytest.approx(0.6)

    turn2 = env.step(
        _action(
            severity="high",
            root_cause="database",
            first_action="investigate order-service deadlock query",
            escalate=True,
        )
    )
    assert turn2.done is True
    assert turn2.reward == pytest.approx(1.0)  # capped cumulative reward


def test_reset_without_task_cycles_through_tasks() -> None:
    env = IncidentTriageEnvironment()
    obs1 = env.reset()
    obs2 = env.reset()
    obs3 = env.reset()

    assert obs1.task_name == "single_service_down"
    assert obs2.task_name == "bad_deployment"
    assert obs3.task_name == "cascading_failure"


def test_bad_deployment_accepts_roll_back_phrase() -> None:
    env = IncidentTriageEnvironment()
    env.reset(task_name="bad_deployment")
    result = env.step(
        _action(
            severity="high",
            root_cause="bad_deploy",
            first_action="roll back inventory-service to previous stable release",
            escalate=False,
        )
    )
    assert result.done is True
    assert result.reward == pytest.approx(1.0)


def test_single_service_down_accepts_db_reconnect_phrase() -> None:
    env = IncidentTriageEnvironment()
    env.reset(task_name="single_service_down")
    result = env.step(
        _action(
            severity="high",
            root_cause="database",
            first_action="reconnect db and verify postgres health",
            escalate=False,
        )
    )
    assert result.done is True
    assert result.reward == pytest.approx(1.0)


def test_task_specific_reset_rotates_variants() -> None:
    env = IncidentTriageEnvironment()
    first = env.reset(task_name="single_service_down")
    second = env.reset(task_name="single_service_down")
    assert first.logs != second.logs
