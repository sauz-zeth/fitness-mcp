from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class WorkoutSetInput(BaseModel):
    weight: float | None = None
    reps: int | None = None
    rpe: float | None = None
    notes: str | None = None


class WorkoutExerciseInput(BaseModel):
    exercise_name: str
    sets: list[WorkoutSetInput] = Field(default_factory=list)
    notes: str | None = None


class WorkoutInput(BaseModel):
    workout_date: date
    training_day: str
    exercises: list[WorkoutExerciseInput]
    rpe: float | None = None
    user_comments: str | None = None
    coach_recommendations: str | None = None


class WorkingWeightUpdate(BaseModel):
    exercise_name: str
    weight: float
    reason: str | None = None


JsonDict = dict[str, Any]
