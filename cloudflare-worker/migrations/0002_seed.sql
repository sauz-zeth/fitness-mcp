INSERT INTO documents (name, data_json, updated_at)
VALUES
  ('athlete_profile', '{"age":null,"available_equipment":["barbell","dumbbells","bench","pull-up bar"],"goals":["build muscle","improve strength safely"],"health_limitations":[],"height_cm":null,"nutrition":{"calories":null,"protein_grams":null},"posture_notes":[],"priority_muscle_groups":[],"training_experience":null,"training_preferences":{"preferred_days_per_week":3,"session_length_minutes":null},"weight_kg":null}', datetime('now')),
  ('trainer_persona', '{"communication_style":"direct, calm, specific","constraints":["do not flatter","do not invent facts","do not change the program without enough evidence","treat pain reports as a reason to stop, modify, or substitute exercises"],"decision_principles":["prioritize technique and consistency over aggressive progression","use stored facts before making recommendations","ask clarifying questions when data is missing"],"motivation_rules":["be honest about weak spots","reinforce concrete progress only when supported by data"],"strictness_level":"medium-high"}', datetime('now')),
  ('decision_rules', '{"missing_information":["do not infer unknown health constraints","ask for missing weight, reps, RPE, or pain details before making load decisions"],"program_changes":["do not change exercises after one bad workout","consider changes after repeated stalls or pain patterns"],"progression":["if all working sets hit the top of the rep range with good technique and RPE is acceptable, increase working weight next time","if technique worsens, do not increase weight","if reps fall below the target range repeatedly, reduce load or volume","if pain appears, suggest a safer substitution and avoid loading through pain"]}', datetime('now'))
ON CONFLICT(name) DO NOTHING;

INSERT INTO program_versions (version, program_json, reason, created_at, active)
SELECT 1, '{"days":[{"exercises":[{"name":"Squat","order":1,"reps_max":10,"reps_min":6,"sets":3,"working_weight":40},{"name":"Bench Press","order":2,"reps_max":10,"reps_min":6,"sets":3,"working_weight":30},{"name":"Row","order":3,"reps_max":12,"reps_min":8,"sets":3,"working_weight":25}],"name":"A"},{"exercises":[{"name":"Deadlift","order":1,"reps_max":8,"reps_min":5,"sets":3,"working_weight":50},{"name":"Overhead Press","order":2,"reps_max":10,"reps_min":6,"sets":3,"working_weight":20},{"name":"Lat Pulldown","order":3,"reps_max":12,"reps_min":8,"sets":3,"working_weight":35}],"name":"B"},{"exercises":[{"name":"Romanian Deadlift","order":1,"reps_max":12,"reps_min":8,"sets":3,"working_weight":35},{"name":"Incline Dumbbell Press","order":2,"reps_max":12,"reps_min":8,"sets":3,"working_weight":16},{"name":"Split Squat","order":3,"reps_max":12,"reps_min":8,"sets":3,"working_weight":12}],"name":"C"}],"name":"Starter A/B/C Hypertrophy","rules":{"progression":"double progression inside the prescribed rep range","rest_minutes":"2-3 for compounds, 1-2 for isolation"}}', 'seed import', datetime('now'), 1
WHERE NOT EXISTS (SELECT 1 FROM program_versions);

INSERT INTO working_weights (exercise_name, weight, changed_at, reason)
VALUES
  ('Bench Press', 30, datetime('now'), 'seed import'),
  ('Deadlift', 50, datetime('now'), 'seed import'),
  ('Incline Dumbbell Press', 16, datetime('now'), 'seed import'),
  ('Lat Pulldown', 35, datetime('now'), 'seed import'),
  ('Overhead Press', 20, datetime('now'), 'seed import'),
  ('Romanian Deadlift', 35, datetime('now'), 'seed import'),
  ('Row', 25, datetime('now'), 'seed import'),
  ('Split Squat', 12, datetime('now'), 'seed import'),
  ('Squat', 40, datetime('now'), 'seed import')
ON CONFLICT(exercise_name) DO NOTHING;

INSERT INTO working_weight_history (exercise_name, old_weight, new_weight, changed_at, reason)
SELECT exercise_name, NULL, weight, changed_at, reason
FROM working_weights
WHERE NOT EXISTS (SELECT 1 FROM working_weight_history);
