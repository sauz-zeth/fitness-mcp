from __future__ import annotations

from pathlib import Path

import pytest

from fitness_coach.service import FitnessCoachService


def make_service(tmp_path: Path) -> FitnessCoachService:
    service = FitnessCoachService(tmp_path / "fitness.sqlite")
    service.import_seeds(Path("seeds"))
    return service


def test_seed_import_loads_documents_program_and_weights(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    assert service.get_athlete_profile()["goals"]
    assert service.get_trainer_persona()["communication_style"]
    assert service.get_current_program()["program"]["name"] == "Starter A/B/C Hypertrophy"
    assert service.get_working_weights()["Squat"]["weight"] == 40


def test_next_training_day_defaults_to_first_program_day(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    result = service.get_next_training_day()

    assert result["last_training_day"] is None
    assert result["next_training_day"] == "A"


def test_next_training_day_rotates_after_logged_workout(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.log_workout(
        {
            "workout_date": "2026-07-01",
            "training_day": "A",
            "exercises": [
                {
                    "exercise_name": "Squat",
                    "sets": [
                        {"weight": 40, "reps": 10, "rpe": 8},
                        {"weight": 40, "reps": 9, "rpe": 8},
                    ],
                }
            ],
            "rpe": 8,
            "user_comments": "solid",
            "coach_recommendations": "continue",
        }
    )

    result = service.get_next_training_day()

    assert result["last_training_day"] == "A"
    assert result["last_workout_date"] == "2026-07-01"
    assert result["next_training_day"] == "B"
    assert isinstance(result["days_since_last_workout"], int)


def test_log_workout_persists_exercises_sets_and_audit(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    workout = service.log_workout(
        {
            "workout_date": "2026-07-02",
            "training_day": "B",
            "exercises": [
                {
                    "exercise_name": "Deadlift",
                    "notes": "controlled",
                    "sets": [
                        {"weight": 50, "reps": 8, "rpe": 8},
                        {"weight": 50, "reps": 8, "rpe": 8.5},
                        {"weight": 50, "reps": 7, "rpe": 9},
                    ],
                }
            ],
            "coach_recommendations": "keep load",
        }
    )

    assert workout["training_day"] == "B"
    assert workout["exercises"][0]["exercise_name"] == "Deadlift"
    assert len(workout["exercises"][0]["sets"]) == 3
    assert service.get_change_history(limit=1)[0]["entity_type"] == "workout_session"


def test_working_weight_update_writes_history_and_audit(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    result = service.update_working_weight("Squat", 42.5, "hit top reps")

    assert result["weight"] == 42.5
    assert service.get_working_weights()["Squat"]["weight"] == 42.5
    history = service.get_change_history(limit=1)[0]
    assert history["entity_type"] == "working_weight"
    assert history["reason"] == "hit top reps"


def test_program_update_versions_program_and_audits(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    current = service.get_current_program()["program"]
    updated = {**current, "name": "Updated Program"}

    result = service.update_training_program(updated, "test change")

    assert result["version"] == 2
    assert result["program"]["name"] == "Updated Program"
    assert service.get_change_history(limit=1)[0]["entity_type"] == "training_program"


def test_profile_update_audits_change(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    service.update_athlete_profile({"age": 30, "goals": ["strength"]}, "profile correction")

    assert service.get_athlete_profile()["age"] == 30
    history = service.get_change_history(limit=1)[0]
    assert history["entity_type"] == "athlete_profile"
    assert history["reason"] == "profile correction"


def test_progress_summary_reports_frequency_and_rep_trends(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.log_workout(
        {
            "workout_date": "2026-07-01",
            "training_day": "A",
            "exercises": [
                {"exercise_name": "Squat", "sets": [{"weight": 40, "reps": 10, "rpe": 8}]}
            ],
        }
    )
    service.log_workout(
        {
            "workout_date": "2026-07-08",
            "training_day": "B",
            "exercises": [
                {"exercise_name": "Deadlift", "sets": [{"weight": 50, "reps": 8, "rpe": 8}]}
            ],
        }
    )

    summary = service.get_progress_summary()

    assert summary["last_workout_date"] == "2026-07-08"
    assert summary["training_frequency_per_week"] == 2
    assert summary["rep_trends_recent"]["Squat"] == [10]


def test_mcp_server_can_be_built(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    from fitness_coach.mcp_server import build_server

    service = FitnessCoachService(tmp_path / "fitness.sqlite")
    service.import_seeds(Path("seeds"))

    assert build_server(tmp_path / "fitness.sqlite") is not None
