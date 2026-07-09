from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import get_db_path
from .service import FitnessCoachService


def build_server(db_path: Path | None = None) -> FastMCP:
    service = FitnessCoachService(db_path or get_db_path())
    mcp = FastMCP("AI Fitness Coach")

    @mcp.tool()
    def get_startup_context() -> dict[str, Any]:
        """Return all context a new chat needs to continue coaching."""
        return service.get_startup_context()

    @mcp.tool()
    def get_athlete_profile() -> dict[str, Any] | None:
        """Return the stored athlete profile."""
        return service.get_athlete_profile()

    @mcp.tool()
    def update_athlete_profile(profile: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
        """Replace the athlete profile and write an audit entry."""
        return service.update_athlete_profile(profile, reason)

    @mcp.tool()
    def get_trainer_persona() -> dict[str, Any] | None:
        """Return the trainer persona and coaching style."""
        return service.get_trainer_persona()

    @mcp.tool()
    def get_current_program() -> dict[str, Any] | None:
        """Return the active versioned training program."""
        return service.get_current_program()

    @mcp.tool()
    def update_training_program(program: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
        """Create a new active training-program version."""
        return service.update_training_program(program, reason)

    @mcp.tool()
    def log_workout(workout: dict[str, Any]) -> dict[str, Any]:
        """Persist a completed workout with exercises, sets, RPE, and notes."""
        return service.log_workout(workout)

    @mcp.tool()
    def get_recent_workouts(limit: int = 10) -> list[dict[str, Any]]:
        """Return recent logged workouts."""
        return service.get_recent_workouts(limit)

    @mcp.tool()
    def get_working_weights() -> dict[str, Any]:
        """Return current working weights by exercise."""
        return service.get_working_weights()

    @mcp.tool()
    def update_working_weight(
        exercise_name: str,
        weight: float,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Update one working weight and append weight/audit history."""
        return service.update_working_weight(exercise_name, weight, reason)

    @mcp.tool()
    def get_next_training_day() -> dict[str, Any]:
        """Derive the next training day from the active program and workout log."""
        return service.get_next_training_day()

    @mcp.tool()
    def get_progress_summary() -> dict[str, Any]:
        """Return deterministic progress metrics calculated from stored history."""
        return service.get_progress_summary()

    @mcp.tool()
    def get_change_history(limit: int = 50) -> list[dict[str, Any]]:
        """Return audit-log entries ordered newest first."""
        return service.get_change_history(limit)

    @mcp.resource("fitness://startup-context")
    def startup_context_resource() -> str:
        return _resource_json(service.get_startup_context())

    @mcp.resource("fitness://athlete-profile")
    def athlete_profile_resource() -> str:
        return _resource_json(service.get_athlete_profile())

    @mcp.resource("fitness://trainer-persona")
    def trainer_persona_resource() -> str:
        return _resource_json(service.get_trainer_persona())

    @mcp.resource("fitness://current-program")
    def current_program_resource() -> str:
        return _resource_json(service.get_current_program())

    @mcp.resource("fitness://decision-rules")
    def decision_rules_resource() -> str:
        return _resource_json(service.get_decision_rules())

    return mcp


def run(db_path: Path | None = None) -> None:
    build_server(db_path).run()


def _resource_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    run()
