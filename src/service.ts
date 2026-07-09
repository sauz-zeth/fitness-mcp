export type JsonObject = Record<string, unknown>;

type WorkoutSetInput = {
  weight?: number | null;
  reps?: number | null;
  rpe?: number | null;
  notes?: string | null;
};

type WorkoutExerciseInput = {
  exercise_name: string;
  sets?: WorkoutSetInput[];
  notes?: string | null;
};

type WorkoutInput = {
  workout_date: string;
  training_day: string;
  exercises: WorkoutExerciseInput[];
  rpe?: number | null;
  user_comments?: string | null;
  coach_recommendations?: string | null;
};

type Row = Record<string, unknown>;

export class FitnessCoachService {
  constructor(private readonly db: D1Database) {}

  async getStartupContext() {
    return {
      athlete_profile: await this.getAthleteProfile(),
      trainer_persona: await this.getTrainerPersona(),
      current_program: await this.getCurrentProgram(),
      next_training_day: await this.getNextTrainingDay(),
      working_weights: await this.getWorkingWeights(),
      recent_workouts: await this.getRecentWorkouts(5),
      decision_rules: await this.getDecisionRules(),
    };
  }

  async getAthleteProfile() {
    return this.getDocument("athlete_profile");
  }

  async updateAthleteProfile(profile: JsonObject, reason?: string | null) {
    const oldValue = await this.getAthleteProfile();
    await this.upsertDocument("athlete_profile", profile);
    await this.audit("athlete_profile", "athlete_profile", oldValue, profile, reason);
    return profile;
  }

  async getTrainerPersona() {
    return this.getDocument("trainer_persona");
  }

  async getDecisionRules() {
    return this.getDocument("decision_rules");
  }

  async getCurrentProgram() {
    const row = await this.db
      .prepare(
        `
        SELECT id, version, program_json, reason, created_at
        FROM program_versions
        WHERE active = 1
        ORDER BY version DESC
        LIMIT 1
        `,
      )
      .first<Row>();

    if (!row) return null;
    return {
      id: row.id,
      version: row.version,
      reason: row.reason,
      created_at: row.created_at,
      program: parseJson(row.program_json),
    };
  }

  async updateTrainingProgram(program: JsonObject, reason?: string | null) {
    const oldValue = await this.getCurrentProgram();
    const versionId = await this.createProgramVersion(program, reason);
    await this.seedMissingWorkingWeights(program);
    await this.audit("training_program", String(versionId), oldValue, program, reason);
    return this.getCurrentProgram();
  }

  async logWorkout(workout: WorkoutInput) {
    validateWorkout(workout);
    const createdAt = nowIso();
    const programRow = await this.db
      .prepare("SELECT id FROM program_versions WHERE active = 1 ORDER BY version DESC LIMIT 1")
      .first<Row>();

    const sessionResult = await this.db
      .prepare(
        `
        INSERT INTO workout_sessions (
          workout_date, training_day, program_version_id, rpe,
          user_comments, coach_recommendations, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        `,
      )
      .bind(
        workout.workout_date,
        workout.training_day,
        programRow?.id ?? null,
        workout.rpe ?? null,
        workout.user_comments ?? null,
        workout.coach_recommendations ?? null,
        createdAt,
      )
      .run();
    const sessionId = sessionResult.meta.last_row_id;

    for (const [exerciseIndex, exercise] of workout.exercises.entries()) {
      const exerciseResult = await this.db
        .prepare(
          `
          INSERT INTO workout_exercises (session_id, exercise_name, position, notes)
          VALUES (?, ?, ?, ?)
          `,
        )
        .bind(sessionId, exercise.exercise_name, exerciseIndex + 1, exercise.notes ?? null)
        .run();
      const exerciseId = exerciseResult.meta.last_row_id;

      for (const [setIndex, set] of (exercise.sets ?? []).entries()) {
        await this.db
          .prepare(
            `
            INSERT INTO workout_sets (
              workout_exercise_id, set_number, weight, reps, rpe, notes
            ) VALUES (?, ?, ?, ?, ?, ?)
            `,
          )
          .bind(
            exerciseId,
            setIndex + 1,
            set.weight ?? null,
            set.reps ?? null,
            set.rpe ?? null,
            set.notes ?? null,
          )
          .run();
      }
    }

    await this.audit("workout_session", String(sessionId), null, workout, null);
    return this.getWorkout(sessionId);
  }

  async getRecentWorkouts(limit = 10) {
    const rows = await this.db
      .prepare(
        `
        SELECT id
        FROM workout_sessions
        ORDER BY workout_date DESC, id DESC
        LIMIT ?
        `,
      )
      .bind(limit)
      .all<Row>();
    return Promise.all(rows.results.map((row) => this.getWorkout(Number(row.id))));
  }

  async getWorkingWeights() {
    const rows = await this.db
      .prepare(
        "SELECT exercise_name, weight, changed_at, reason FROM working_weights ORDER BY exercise_name",
      )
      .all<Row>();

    const result: Record<string, unknown> = {};
    for (const row of rows.results) {
      result[String(row.exercise_name)] = {
        weight: row.weight,
        changed_at: row.changed_at,
        reason: row.reason,
      };
    }
    return result;
  }

  async updateWorkingWeight(exerciseName: string, weight: number, reason?: string | null) {
    if (!exerciseName) throw new Error("exercise_name is required");
    if (typeof weight !== "number" || Number.isNaN(weight)) throw new Error("weight must be a number");

    const changedAt = nowIso();
    const oldRow = await this.db
      .prepare("SELECT weight, changed_at, reason FROM working_weights WHERE exercise_name = ?")
      .bind(exerciseName)
      .first<Row>();
    const oldValue = oldRow ? { ...oldRow } : null;

    await this.db
      .prepare(
        `
        INSERT INTO working_weights (exercise_name, weight, changed_at, reason)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(exercise_name) DO UPDATE SET
          weight = excluded.weight,
          changed_at = excluded.changed_at,
          reason = excluded.reason
        `,
      )
      .bind(exerciseName, weight, changedAt, reason ?? null)
      .run();

    await this.db
      .prepare(
        `
        INSERT INTO working_weight_history (
          exercise_name, old_weight, new_weight, changed_at, reason
        ) VALUES (?, ?, ?, ?, ?)
        `,
      )
      .bind(exerciseName, oldRow?.weight ?? null, weight, changedAt, reason ?? null)
      .run();

    const newValue = { weight, changed_at: changedAt, reason: reason ?? null };
    await this.audit("working_weight", exerciseName, oldValue, newValue, reason);
    return { exercise_name: exerciseName, ...newValue };
  }

  async getNextTrainingDay() {
    const programWrapper = await this.getCurrentProgram();
    const days = programDays(programWrapper);
    if (days.length === 0) {
      return {
        last_training_day: null,
        last_workout_date: null,
        next_training_day: null,
        days_since_last_workout: null,
      };
    }

    const row = await this.db
      .prepare(
        `
        SELECT training_day, workout_date
        FROM workout_sessions
        ORDER BY workout_date DESC, id DESC
        LIMIT 1
        `,
      )
      .first<Row>();

    if (!row) {
      return {
        last_training_day: null,
        last_workout_date: null,
        next_training_day: days[0],
        days_since_last_workout: null,
      };
    }

    const lastDay = String(row.training_day);
    const dayIndex = days.indexOf(lastDay);
    const nextDay = dayIndex >= 0 ? days[(dayIndex + 1) % days.length] : days[0];
    return {
      last_training_day: lastDay,
      last_workout_date: row.workout_date,
      next_training_day: nextDay,
      days_since_last_workout: daysSince(String(row.workout_date)),
    };
  }

  async getProgressSummary() {
    const recent = await this.getRecentWorkouts(20);
    const weights = await this.getWorkingWeights();
    const weightHistory = await this.db
      .prepare(
        `
        SELECT exercise_name, old_weight, new_weight, changed_at, reason
        FROM working_weight_history
        ORDER BY changed_at DESC, id DESC
        `,
      )
      .all<Row>();
    const workoutStats = await this.db
      .prepare(
        `
        SELECT MIN(workout_date) AS first_date,
               MAX(workout_date) AS last_date,
               COUNT(*) AS count
        FROM workout_sessions
        `,
      )
      .first<Row>();

    const repTrends: Record<string, number[]> = {};
    for (const workout of recent) {
      for (const exercise of workout.exercises) {
        const exerciseName = String(exercise.exercise_name);
        const reps = exercise.sets.reduce((total, set) => total + Number(set.reps ?? 0), 0);
        repTrends[exerciseName] ??= [];
        repTrends[exerciseName].push(reps);
      }
    }

    const staleExercises = Object.entries(repTrends)
      .filter(([, values]) => values.length >= 3 && values[0] <= Math.max(values[1], values[2]))
      .map(([exercise]) => exercise);

    let frequency: number | null = null;
    if (workoutStats?.first_date && workoutStats.last_date && Number(workoutStats.count) > 0) {
      const start = Date.parse(String(workoutStats.first_date));
      const end = Date.parse(String(workoutStats.last_date));
      const weeks = Math.max((end - start) / 1000 / 60 / 60 / 24 / 7, 1 / 7);
      frequency = round(Number(workoutStats.count) / weeks, 2);
    }

    return {
      current_working_weights: weights,
      working_weight_changes: weightHistory.results,
      rep_trends_recent: repTrends,
      training_frequency_per_week: frequency,
      last_workout_date: workoutStats?.last_date ?? null,
      stale_or_no_progress_exercises: staleExercises,
    };
  }

  async getChangeHistory(limit = 50) {
    const rows = await this.db
      .prepare(
        `
        SELECT id, entity_type, entity_id, old_value_json, new_value_json, reason, created_at
        FROM audit_log
        ORDER BY id DESC
        LIMIT ?
        `,
      )
      .bind(limit)
      .all<Row>();

    return rows.results.map((row) => ({
      id: row.id,
      entity_type: row.entity_type,
      entity_id: row.entity_id,
      old_value: parseJson(row.old_value_json),
      new_value: parseJson(row.new_value_json),
      reason: row.reason,
      created_at: row.created_at,
    }));
  }

  private async getDocument(name: string) {
    const row = await this.db
      .prepare("SELECT data_json FROM documents WHERE name = ?")
      .bind(name)
      .first<Row>();
    return row ? parseJson(row.data_json) : null;
  }

  private async upsertDocument(name: string, data: JsonObject) {
    await this.db
      .prepare(
        `
        INSERT INTO documents (name, data_json, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
          data_json = excluded.data_json,
          updated_at = excluded.updated_at
        `,
      )
      .bind(name, JSON.stringify(data), nowIso())
      .run();
  }

  private async createProgramVersion(program: JsonObject, reason?: string | null) {
    const row = await this.db
      .prepare("SELECT COALESCE(MAX(version), 0) + 1 AS next_version FROM program_versions")
      .first<Row>();
    const version = Number(row?.next_version ?? 1);
    await this.db.prepare("UPDATE program_versions SET active = 0").run();
    const result = await this.db
      .prepare(
        `
        INSERT INTO program_versions (version, program_json, reason, created_at, active)
        VALUES (?, ?, ?, ?, 1)
        `,
      )
      .bind(version, JSON.stringify(program), reason ?? null, nowIso())
      .run();
    return result.meta.last_row_id;
  }

  private async seedMissingWorkingWeights(programWrapper: unknown) {
    const program = unwrapProgram(programWrapper);
    for (const day of asArray((program as JsonObject).days)) {
      for (const exercise of asArray((day as JsonObject).exercises)) {
        const item = exercise as JsonObject;
        const name = typeof item.name === "string" ? item.name : null;
        const weight = typeof item.working_weight === "number" ? item.working_weight : null;
        if (!name || weight === null) continue;
        const exists = await this.db
          .prepare("SELECT 1 FROM working_weights WHERE exercise_name = ?")
          .bind(name)
          .first<Row>();
        if (exists) continue;
        const changedAt = nowIso();
        await this.db
          .prepare(
            "INSERT INTO working_weights (exercise_name, weight, changed_at, reason) VALUES (?, ?, ?, ?)",
          )
          .bind(name, weight, changedAt, "seed import")
          .run();
        await this.db
          .prepare(
            `
            INSERT INTO working_weight_history (
              exercise_name, old_weight, new_weight, changed_at, reason
            ) VALUES (?, ?, ?, ?, ?)
            `,
          )
          .bind(name, null, weight, changedAt, "seed import")
          .run();
      }
    }
  }

  private async getWorkout(sessionId: number) {
    const session = await this.db
      .prepare(
        `
        SELECT id, workout_date, training_day, program_version_id, rpe,
               user_comments, coach_recommendations, created_at
        FROM workout_sessions
        WHERE id = ?
        `,
      )
      .bind(sessionId)
      .first<Row>();
    if (!session) throw new Error(`Workout session ${sessionId} not found`);

    const exercises = await this.db
      .prepare(
        `
        SELECT id, exercise_name, position, notes
        FROM workout_exercises
        WHERE session_id = ?
        ORDER BY position
        `,
      )
      .bind(sessionId)
      .all<Row>();

    const resultExercises = [];
    for (const exercise of exercises.results) {
      const sets = await this.db
        .prepare(
          `
          SELECT set_number, weight, reps, rpe, notes
          FROM workout_sets
          WHERE workout_exercise_id = ?
          ORDER BY set_number
          `,
        )
        .bind(exercise.id)
        .all<Row>();
      resultExercises.push({
        exercise_name: exercise.exercise_name,
        position: exercise.position,
        notes: exercise.notes,
        sets: sets.results,
      });
    }

    return {
      id: session.id,
      workout_date: session.workout_date,
      training_day: session.training_day,
      program_version_id: session.program_version_id,
      rpe: session.rpe,
      user_comments: session.user_comments,
      coach_recommendations: session.coach_recommendations,
      created_at: session.created_at,
      exercises: resultExercises,
    };
  }

  private async audit(
    entityType: string,
    entityId: string | null,
    oldValue: unknown,
    newValue: unknown,
    reason?: string | null,
  ) {
    await this.db
      .prepare(
        `
        INSERT INTO audit_log (
          entity_type, entity_id, old_value_json, new_value_json, reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        `,
      )
      .bind(
        entityType,
        entityId,
        oldValue === null || oldValue === undefined ? null : JSON.stringify(oldValue),
        newValue === null || newValue === undefined ? null : JSON.stringify(newValue),
        reason ?? null,
        nowIso(),
      )
      .run();
  }
}

function validateWorkout(workout: WorkoutInput) {
  if (!workout || typeof workout !== "object") throw new Error("workout is required");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(workout.workout_date)) {
    throw new Error("workout_date must be YYYY-MM-DD");
  }
  if (!workout.training_day) throw new Error("training_day is required");
  if (!Array.isArray(workout.exercises)) throw new Error("exercises must be an array");
}

function programDays(programWrapper: unknown) {
  const program = unwrapProgram(programWrapper);
  return asArray((program as JsonObject).days)
    .map((day) => (day as JsonObject).name)
    .filter((name): name is string => typeof name === "string");
}

function unwrapProgram(programWrapper: unknown): unknown {
  if (programWrapper && typeof programWrapper === "object" && "program" in programWrapper) {
    return (programWrapper as JsonObject).program;
  }
  return programWrapper ?? {};
}

function parseJson(value: unknown) {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") return value;
  return JSON.parse(value);
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function nowIso() {
  return new Date().toISOString();
}

function daysSince(isoDate: string) {
  const start = Date.parse(`${isoDate}T00:00:00.000Z`);
  const now = Date.now();
  return Math.floor((now - start) / 1000 / 60 / 60 / 24);
}

function round(value: number, digits: number) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}
