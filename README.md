# Fitness Coach MCP on Cloudflare Workers

Remote MCP server for ChatGPT/mobile access, backed by Cloudflare D1.

The local `stdio` MCP server (SQLite-backed) lives in `python/` — see
`python/README.md` for that setup.

## Local Setup

```bash
npm install
npm run typecheck
```

## Create D1

```bash
npx wrangler login
npx wrangler d1 create fitness-coach
```

Copy the returned `database_id` into `wrangler.jsonc`:

```jsonc
{
  "binding": "DB",
  "database_name": "fitness-coach",
  "database_id": "..."
}
```

## Apply Migrations

Local:

```bash
npx wrangler d1 migrations apply fitness-coach --local
```

Remote:

```bash
npx wrangler d1 migrations apply fitness-coach --remote
```

## Run Locally

```bash
npm run dev
```

The local MCP endpoint is:

```text
http://localhost:8787/mcp
```

Do not test `/mcp` by opening it in a browser. Use an MCP client:

```bash
npx @modelcontextprotocol/inspector@latest
```

For Streamable HTTP, clients must send `Accept: application/json, text/event-stream`.

## Optional Shared Secret

For a quick private deployment, set a bearer token:

```bash
npx wrangler secret put MCP_SHARED_SECRET
```

Clients must then send:

```text
Authorization: Bearer <your-secret>
```

Leave the secret unset only for short local or private testing.

## Deploy

```bash
npm run deploy
```

The remote MCP endpoint will be:

```text
https://fitness-coach-mcp.<your-account>.workers.dev/mcp
```

## Tools

- `get_startup_context`
- `get_athlete_profile`
- `update_athlete_profile`
- `get_trainer_persona`
- `get_current_program`
- `update_training_program`
- `log_workout`
- `get_recent_workouts`
- `get_working_weights`
- `update_working_weight`
- `get_next_training_day`
- `get_progress_summary`
- `get_change_history`
