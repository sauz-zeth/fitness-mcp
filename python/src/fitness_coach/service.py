from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from .db import connect, init_db
from .models import WorkoutInput


DOCUMENTS = {
    "athlete_profile": "athlete_profile.yaml",
    "trainer_persona": "trainer_persona.yaml",
    "decision_rules": "decision_rules.yaml",
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def json_loads(value: str | None) -> Any:
    if value is None:
        return None
    return json.loads(value)


class FitnessCoachService:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def init_db(self) -> None:
        init_db(self.db_path)

    def import_seeds(self, seed_dir: Path) -> None:
        self.init_db()
        with connect(self.db_path) as conn:
            for document_name, filename in DOCUMENTS.items():
                path = seed_dir / filename
                if path.exists():
                    data = self._read_yaml(path)
                    self._upsert_document(conn, document_name, data, "seed import")

            program_path = seed_dir / "training_program.yaml"
            if program_path.exists():
                self._create_program_version(
                    conn,
                    self._read_yaml(program_path),
                    reason="seed import",
                )

            active_program = self._get_current_program(conn)
            if active_program:
                self._seed_missing_working_weights(conn, active_program)

    def get_startup_context(self) -> dict[str, Any]:
        return {
            "athlete_profile": self.get_athlete_profile(),
            "trainer_persona": self.get_trainer_persona(),
            "current_program": self.get_current_program(),
            "next_training_day": self.get_next_training_day(),
            "working_weights": self.get_working_weights(),
            "recent_workouts": self.get_recent_workouts(limit=5),
            "decision_rules": self.get_decision_rules(),
        }

    def get_athlete_profile(self) -> dict[str, Any] | None:
        return self._get_document("athlete_profile")

    def update_athlete_profile(self, profile: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            old = self._get_document_with_conn(conn, "athlete_profile")
            self._upsert_document(conn, "athlete_profile", profile, reason)
            self._audit(conn, "athlete_profile", "athlete_profile", old, profile, reason)
        return profile

    def get_trainer_persona(self) -> dict[str, Any] | None:
        return self._get_document("trainer_persona")

    def get_decision_rules(self) -> dict[str, Any] | None:
        return self._get_document("decision_rules")

    def get_current_program(self) -> dict[str, Any] | None:
        with connect(self.db_path) as conn:
            return self._get_current_program(conn)

    def update_training_program(self, program: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            old = self._get_current_program(conn)
            version_id = self._create_program_version(conn, program, reason)
            self._seed_missing_working_weights(conn, program)
            self._audit(conn, "training_program", str(version_id), old, program, reason)
        return self.get_current_program() or program

    def log_workout(self, workout: dict[str, Any]) -> dict[str, Any]:
        parsed = WorkoutInput.model_validate(workout)
        created_at = now_iso()
        with connect(self.db_path) as conn:
            program_row = conn.execute(
                "SELECT id FROM program_versions WHERE active = 1 ORDER BY version DESC LIMIT 1"
            ).fetchone()
            cursor = conn.execute(
                """
                INSERT INTO workout_sessions (
                    workout_date, training_day, program_version_id, rpe,
                    user_comments, coach_recommendations, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    parsed.workout_date.isoformat(),
                    parsed.training_day,
                    program_row["id"] if program_row else None,
                    parsed.rpe,
                    parsed.user_comments,
                    parsed.coach_recommendations,
                    created_at,
                ),
            )
            session_id = cursor.lastrowid

            for position, exercise in enumerate(parsed.exercises, start=1):
                exercise_cursor = conn.execute(
                    """
                    INSERT INTO workout_exercises (session_id, exercise_name, position, notes)
                    VALUES (?, ?, ?, ?)
                    """,
                    (session_id, exercise.exercise_name, position, exercise.notes),
                )
                exercise_id = exercise_cursor.lastrowid
                for set_number, workout_set in enumerate(exercise.sets, start=1):
                    conn.execute(
                        """
                        INSERT INTO workout_sets (
                            workout_exercise_id, set_number, weight, reps, rpe, notes
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            exercise_id,
                            set_number,
                            workout_set.weight,
                            workout_set.reps,
                            workout_set.rpe,
                            workout_set.notes,
                        ),
                    )

            self._audit(conn, "workout_session", str(session_id), None, parsed.model_dump(mode="json"), None)
        return self._get_workout(session_id)

    def get_recent_workouts(self, limit: int = 10) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT id FROM workout_sessions
                ORDER BY workout_date DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._get_workout(row["id"]) for row in rows]

    def get_working_weights(self) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT exercise_name, weight, changed_at, reason FROM working_weights ORDER BY exercise_name"
            ).fetchall()
        return {
            row["exercise_name"]: {
                "weight": row["weight"],
                "changed_at": row["changed_at"],
                "reason": row["reason"],
            }
            for row in rows
        }

    def update_working_weight(
        self,
        exercise_name: str,
        weight: float,
        reason: str | None = None,
    ) -> dict[str, Any]:
        changed_at = now_iso()
        with connect(self.db_path) as conn:
            old_row = conn.execute(
                "SELECT weight, changed_at, reason FROM working_weights WHERE exercise_name = ?",
                (exercise_name,),
            ).fetchone()
            old_value = dict(old_row) if old_row else None
            conn.execute(
                """
                INSERT INTO working_weights (exercise_name, weight, changed_at, reason)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(exercise_name) DO UPDATE SET
                    weight = excluded.weight,
                    changed_at = excluded.changed_at,
                    reason = excluded.reason
                """,
                (exercise_name, weight, changed_at, reason),
            )
            conn.execute(
                """
                INSERT INTO working_weight_history (
                    exercise_name, old_weight, new_weight, changed_at, reason
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (exercise_name, old_row["weight"] if old_row else None, weight, changed_at, reason),
            )
            new_value = {"weight": weight, "changed_at": changed_at, "reason": reason}
            self._audit(conn, "working_weight", exercise_name, old_value, new_value, reason)
        return {"exercise_name": exercise_name, **new_value}

    def get_next_training_day(self) -> dict[str, Any]:
        program = self.get_current_program()
        days = self._program_days(program)
        if not days:
            return {
                "last_training_day": None,
                "last_workout_date": None,
                "next_training_day": None,
                "days_since_last_workout": None,
            }

        with connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT training_day, workout_date FROM workout_sessions
                ORDER BY workout_date DESC, id DESC LIMIT 1
                """
            ).fetchone()

        if row is None:
            return {
                "last_training_day": None,
                "last_workout_date": None,
                "next_training_day": days[0],
                "days_since_last_workout": None,
            }

        last_day = row["training_day"]
        try:
            next_day = days[(days.index(last_day) + 1) % len(days)]
        except ValueError:
            next_day = days[0]
        last_date = date.fromisoformat(row["workout_date"])
        return {
            "last_training_day": last_day,
            "last_workout_date": row["workout_date"],
            "next_training_day": next_day,
            "days_since_last_workout": (date.today() - last_date).days,
        }

    def get_progress_summary(self) -> dict[str, Any]:
        recent = self.get_recent_workouts(limit=20)
        weights = self.get_working_weights()
        with connect(self.db_path) as conn:
            weight_history_rows = conn.execute(
                """
                SELECT exercise_name, old_weight, new_weight, changed_at, reason
                FROM working_weight_history
                ORDER BY changed_at DESC, id DESC
                """
            ).fetchall()
            first_workout = conn.execute(
                "SELECT MIN(workout_date) AS first_date, MAX(workout_date) AS last_date, COUNT(*) AS count FROM workout_sessions"
            ).fetchone()

        rep_totals: dict[str, list[int]] = defaultdict(list)
        for workout in recent:
            for exercise in workout["exercises"]:
                reps = sum((workout_set.get("reps") or 0) for workout_set in exercise["sets"])
                rep_totals[exercise["exercise_name"]].append(reps)

        stale_exercises = []
        for exercise, values in rep_totals.items():
            if len(values) >= 3 and values[0] <= max(values[1:3]):
                stale_exercises.append(exercise)

        workout_count = first_workout["count"] if first_workout else 0
        frequency = None
        if first_workout and first_workout["first_date"] and first_workout["last_date"]:
            start = date.fromisoformat(first_workout["first_date"])
            end = date.fromisoformat(first_workout["last_date"])
            weeks = max((end - start).days / 7, 1 / 7)
            frequency = round(workout_count / weeks, 2)

        return {
            "current_working_weights": weights,
            "working_weight_changes": [dict(row) for row in weight_history_rows],
            "rep_trends_recent": dict(rep_totals),
            "training_frequency_per_week": frequency,
            "last_workout_date": first_workout["last_date"] if first_workout else None,
            "stale_or_no_progress_exercises": stale_exercises,
        }

    def get_change_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, entity_type, entity_id, old_value_json, new_value_json, reason, created_at
                FROM audit_log ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "old_value": json_loads(row["old_value_json"]),
                "new_value": json_loads(row["new_value_json"]),
                "reason": row["reason"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def _get_document(self, name: str) -> dict[str, Any] | None:
        with connect(self.db_path) as conn:
            return self._get_document_with_conn(conn, name)

    def _get_document_with_conn(self, conn, name: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT data_json FROM documents WHERE name = ?", (name,)).fetchone()
        return json_loads(row["data_json"]) if row else None

    def _upsert_document(self, conn, name: str, data: dict[str, Any], reason: str | None) -> None:
        conn.execute(
            """
            INSERT INTO documents (name, data_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                data_json = excluded.data_json,
                updated_at = excluded.updated_at
            """,
            (name, json_dumps(data), now_iso()),
        )

    def _create_program_version(self, conn, program: dict[str, Any], reason: str | None) -> int:
        row = conn.execute("SELECT COALESCE(MAX(version), 0) + 1 AS next_version FROM program_versions").fetchone()
        version = row["next_version"]
        conn.execute("UPDATE program_versions SET active = 0")
        cursor = conn.execute(
            """
            INSERT INTO program_versions (version, program_json, reason, created_at, active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (version, json_dumps(program), reason, now_iso()),
        )
        return cursor.lastrowid

    def _get_current_program(self, conn) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT id, version, program_json, reason, created_at
            FROM program_versions WHERE active = 1 ORDER BY version DESC LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        program = json_loads(row["program_json"])
        return {
            "id": row["id"],
            "version": row["version"],
            "reason": row["reason"],
            "created_at": row["created_at"],
            "program": program,
        }

    def _seed_missing_working_weights(self, conn, program_wrapper: dict[str, Any]) -> None:
        program = program_wrapper.get("program", program_wrapper)
        for day in program.get("days", []):
            for exercise in day.get("exercises", []):
                name = exercise.get("name")
                weight = exercise.get("working_weight")
                if not name or weight is None:
                    continue
                exists = conn.execute(
                    "SELECT 1 FROM working_weights WHERE exercise_name = ?",
                    (name,),
                ).fetchone()
                if exists:
                    continue
                changed_at = now_iso()
                conn.execute(
                    "INSERT INTO working_weights (exercise_name, weight, changed_at, reason) VALUES (?, ?, ?, ?)",
                    (name, weight, changed_at, "seed import"),
                )
                conn.execute(
                    """
                    INSERT INTO working_weight_history (
                        exercise_name, old_weight, new_weight, changed_at, reason
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (name, None, weight, changed_at, "seed import"),
                )

    def _get_workout(self, session_id: int) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            session = conn.execute(
                """
                SELECT id, workout_date, training_day, program_version_id, rpe,
                       user_comments, coach_recommendations, created_at
                FROM workout_sessions WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
            if session is None:
                raise ValueError(f"Workout session {session_id} not found")
            exercises = conn.execute(
                """
                SELECT id, exercise_name, position, notes
                FROM workout_exercises
                WHERE session_id = ?
                ORDER BY position
                """,
                (session_id,),
            ).fetchall()
            result_exercises = []
            for exercise in exercises:
                sets = conn.execute(
                    """
                    SELECT set_number, weight, reps, rpe, notes
                    FROM workout_sets
                    WHERE workout_exercise_id = ?
                    ORDER BY set_number
                    """,
                    (exercise["id"],),
                ).fetchall()
                result_exercises.append(
                    {
                        "exercise_name": exercise["exercise_name"],
                        "position": exercise["position"],
                        "notes": exercise["notes"],
                        "sets": [dict(row) for row in sets],
                    }
                )
        return {
            "id": session["id"],
            "workout_date": session["workout_date"],
            "training_day": session["training_day"],
            "program_version_id": session["program_version_id"],
            "rpe": session["rpe"],
            "user_comments": session["user_comments"],
            "coach_recommendations": session["coach_recommendations"],
            "created_at": session["created_at"],
            "exercises": result_exercises,
        }

    def _program_days(self, program_wrapper: dict[str, Any] | None) -> list[str]:
        if not program_wrapper:
            return []
        program = program_wrapper.get("program", program_wrapper)
        return [day["name"] for day in program.get("days", []) if day.get("name")]

    def _audit(
        self,
        conn,
        entity_type: str,
        entity_id: str | None,
        old_value: Any,
        new_value: Any,
        reason: str | None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO audit_log (
                entity_type, entity_id, old_value_json, new_value_json, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                entity_type,
                entity_id,
                json_dumps(old_value) if old_value is not None else None,
                json_dumps(new_value) if new_value is not None else None,
                reason,
                now_iso(),
            ),
        )

    def _read_yaml(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a YAML mapping")
        return data
