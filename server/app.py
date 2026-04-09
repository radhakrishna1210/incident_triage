# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
FastAPI application for the Incident Triage Environment.

This module creates an HTTP server that exposes the IncidentTriageEnvironment
over HTTP and WebSocket endpoints, compatible with EnvClient.

Endpoints:
    - POST /reset: Reset the environment
    - POST /step: Execute an action
    - GET /state: Get current environment state
    - GET /schema: Get action/observation schemas
    - WS /ws: WebSocket endpoint for persistent sessions

Usage:
    # Development (with auto-reload):
    uvicorn server.app:app --reload --host 0.0.0.0 --port 8000

    # Production:
    uvicorn server.app:app --host 0.0.0.0 --port 8000 --workers 4

    # Or run directly:
    python -m server.app
"""
import pathlib

try:
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import RedirectResponse
    from fastapi.responses import HTMLResponse
    from openenv.core.env_server.http_server import create_app
except Exception as e:  # pragma: no cover
    raise ImportError(
        "openenv is required for the web interface. Install dependencies with '\n    uv sync\n'"
    ) from e

try:
    from ..models import IncidentTriageAction, IncidentTriageObservation
    from .incident_triage_environment import IncidentTriageEnvironment
except ImportError:
    from models import IncidentTriageAction, IncidentTriageObservation
    from server.incident_triage_environment import IncidentTriageEnvironment


# Create the app with web interface and README integration
app = create_app(
    IncidentTriageEnvironment,
    IncidentTriageAction,
    IncidentTriageObservation,
    env_name="incident_triage",
    max_concurrent_envs=10,  # allow up to 10 concurrent WebSocket sessions for parallel evaluation
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_DEMO_HTML = pathlib.Path(__file__).with_name("demo.html")
_SCOREBOARD_HTML = pathlib.Path(__file__).with_name("scoreboard.html")
_SCHEMA_HTML = pathlib.Path(__file__).with_name("schema.html")
_HEALTH_HTML = pathlib.Path(__file__).with_name("health.html")
_STATE_HTML = pathlib.Path(__file__).with_name("state.html")
_METADATA_HTML = pathlib.Path(__file__).with_name("metadata.html")


@app.get("/")
def root_redirect() -> RedirectResponse:
    """Redirect root requests to the demo page."""
    return RedirectResponse(url="/demo")


@app.get("/demo", response_class=HTMLResponse)
def demo_page() -> HTMLResponse:
    """Minimal UI to manually run task/reset/step loops."""
    return HTMLResponse(_DEMO_HTML.read_text(encoding="utf-8"))


@app.get("/scoreboard", response_class=HTMLResponse)
def scoreboard_page() -> HTMLResponse:
    """Scoreboard UI to run all benchmark tasks."""
    return HTMLResponse(_SCOREBOARD_HTML.read_text(encoding="utf-8"))


@app.get("/schema-ui", response_class=HTMLResponse)
def schema_ui_page() -> HTMLResponse:
    """Human-readable schema viewer."""
    return HTMLResponse(_SCHEMA_HTML.read_text(encoding="utf-8"))


@app.get("/health-ui", response_class=HTMLResponse)
def health_ui_page() -> HTMLResponse:
    """Live health status page."""
    return HTMLResponse(_HEALTH_HTML.read_text(encoding="utf-8"))


@app.get("/state-ui", response_class=HTMLResponse)
def state_ui_page() -> HTMLResponse:
    """Live episode state viewer."""
    return HTMLResponse(_STATE_HTML.read_text(encoding="utf-8"))


@app.get("/metadata-ui", response_class=HTMLResponse)
def metadata_ui_page() -> HTMLResponse:
    """Environment metadata viewer."""
    return HTMLResponse(_METADATA_HTML.read_text(encoding="utf-8"))


def main(host: str = "0.0.0.0", port: int = 8000):
    """
    Entry point for direct execution via uv run or python -m.

    This function enables running the server without Docker:
        uv run --project . server
        uv run --project . server --port 8001
        python -m incident_triage.server.app

    Args:
        host: Host address to bind to (default: "0.0.0.0")
        port: Port number to listen on (default: 8000)

    For production deployments, consider using uvicorn directly with
    multiple workers:
        uvicorn incident_triage.server.app:app --workers 4
    """
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
