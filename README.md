# AI Fitness Coach MCP Server

Local `stdio` MCP server that stores fitness-coaching state in SQLite.

## Quick Start

```bash
uv run fitness-coach init-db
uv run fitness-coach import-seeds
uv run fitness-coach serve
```

The default database is `./data/fitness_coach.sqlite`. Override it with:

```bash
FITNESS_COACH_DB=/path/to/fitness.sqlite uv run fitness-coach serve
```

## MCP Tools

- `get_startup_context`
- `get_athlete_profile` / `update_athlete_profile`
- `get_trainer_persona`
- `get_current_program` / `update_training_program`
- `log_workout`
- `get_recent_workouts`
- `get_working_weights` / `update_working_weight`
- `get_next_training_day`
- `get_progress_summary`
- `get_change_history`

## MCP Resources

- `fitness://startup-context`
- `fitness://athlete-profile`
- `fitness://trainer-persona`
- `fitness://current-program`
- `fitness://decision-rules`

YAML seed files in `seeds/` are import inputs only. Runtime state is read from SQLite.

## Cloudflare Worker

A remote MCP version for ChatGPT/mobile access lives in `cloudflare-worker/`.
It uses Cloudflare Workers + D1 and exposes `/mcp` over Streamable HTTP.

See `cloudflare-worker/README.md` for D1 creation, migrations, local testing,
optional bearer-token auth, and deploy commands.
