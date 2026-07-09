import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpAgent } from "agents/mcp";
import { z } from "zod";

import { FitnessCoachService } from "./service";

type State = Record<string, never>;

export class FitnessCoachMCP extends McpAgent<Env, State> {
  server = new McpServer({
    name: "AI Fitness Coach",
    version: "0.1.0",
  });

  initialState: State = {};

  async init() {
    const service = new FitnessCoachService(this.env.DB);

    this.server.registerTool(
    "get_startup_context",
    {
      description:
        "Return athlete profile, trainer persona, current program, next training day, working weights, recent workouts, and decision rules.",
      inputSchema: {},
    },
    async () => result(await service.getStartupContext()),
  );

    this.server.registerTool(
    "get_athlete_profile",
    {
      description: "Return the stored athlete profile.",
      inputSchema: {},
    },
    async () => result(await service.getAthleteProfile()),
  );

    this.server.registerTool(
    "update_athlete_profile",
    {
      description: "Replace the athlete profile and write an audit entry.",
      inputSchema: {
        profile: z.record(z.unknown()).describe("Complete athlete profile JSON object."),
        reason: z.string().optional().describe("Why the profile changed."),
      },
    },
    async ({ profile, reason }) => result(await service.updateAthleteProfile(profile, reason)),
  );

    this.server.registerTool(
    "get_trainer_persona",
    {
      description: "Return the trainer persona and coaching style.",
      inputSchema: {},
    },
    async () => result(await service.getTrainerPersona()),
  );

    this.server.registerTool(
    "get_current_program",
    {
      description: "Return the active versioned training program.",
      inputSchema: {},
    },
    async () => result(await service.getCurrentProgram()),
  );

    this.server.registerTool(
    "update_training_program",
    {
      description: "Create a new active training-program version.",
      inputSchema: {
        program: z.record(z.unknown()).describe("Complete training program JSON object."),
        reason: z.string().optional().describe("Why the program changed."),
      },
    },
    async ({ program, reason }) => result(await service.updateTrainingProgram(program, reason)),
  );

    this.server.registerTool(
    "log_workout",
    {
      description:
        "Persist a completed workout with date, training day, exercises, sets, weights, reps, RPE, notes, and coach recommendations.",
      inputSchema: {
        workout: z.object({
          workout_date: z.string().describe("Workout date in YYYY-MM-DD format."),
          training_day: z.string().describe("Training day label, for example A, B, or C."),
          exercises: z.array(
            z.object({
              exercise_name: z.string(),
              notes: z.string().nullable().optional(),
              sets: z
                .array(
                  z.object({
                    weight: z.number().nullable().optional(),
                    reps: z.number().int().nullable().optional(),
                    rpe: z.number().nullable().optional(),
                    notes: z.string().nullable().optional(),
                  }),
                )
                .default([]),
            }),
          ),
          rpe: z.number().nullable().optional(),
          user_comments: z.string().nullable().optional(),
          coach_recommendations: z.string().nullable().optional(),
        }),
      },
    },
    async ({ workout }) => result(await service.logWorkout(workout)),
  );

    this.server.registerTool(
    "get_recent_workouts",
    {
      description: "Return recent logged workouts.",
      inputSchema: {
        limit: z.number().int().min(1).max(100).default(10),
      },
    },
    async ({ limit }) => result(await service.getRecentWorkouts(limit)),
  );

    this.server.registerTool(
    "get_working_weights",
    {
      description: "Return current working weights by exercise.",
      inputSchema: {},
    },
    async () => result(await service.getWorkingWeights()),
  );

    this.server.registerTool(
    "update_working_weight",
    {
      description: "Update one working weight and append weight/audit history.",
      inputSchema: {
        exercise_name: z.string().describe("Exercise name exactly as stored in the program/log."),
        weight: z.number().describe("New working weight."),
        reason: z.string().optional().describe("Why this working weight changed."),
      },
    },
    async ({ exercise_name, weight, reason }) =>
      result(await service.updateWorkingWeight(exercise_name, weight, reason)),
  );

    this.server.registerTool(
    "get_next_training_day",
    {
      description: "Derive the next training day from the active program and workout log.",
      inputSchema: {},
    },
    async () => result(await service.getNextTrainingDay()),
  );

    this.server.registerTool(
    "get_progress_summary",
    {
      description: "Return deterministic progress metrics calculated from stored workout history.",
      inputSchema: {},
    },
    async () => result(await service.getProgressSummary()),
  );

    this.server.registerTool(
    "get_change_history",
    {
      description: "Return audit-log entries ordered newest first.",
      inputSchema: {
        limit: z.number().int().min(1).max(200).default(50),
      },
    },
    async ({ limit }) => result(await service.getChangeHistory(limit)),
  );

    this.server.registerResource(
    "fitness-startup-context",
    "fitness://startup-context",
    {
      title: "Fitness Startup Context",
      description: "Complete startup context for a new fitness-coaching chat.",
      mimeType: "application/json",
    },
    async (uri) => resource(uri, await service.getStartupContext()),
  );

    this.server.registerResource(
    "fitness-athlete-profile",
    "fitness://athlete-profile",
    {
      title: "Athlete Profile",
      description: "Stored athlete profile.",
      mimeType: "application/json",
    },
    async (uri) => resource(uri, await service.getAthleteProfile()),
  );

    this.server.registerResource(
    "fitness-trainer-persona",
    "fitness://trainer-persona",
    {
      title: "Trainer Persona",
      description: "Stored trainer persona and coaching style.",
      mimeType: "application/json",
    },
    async (uri) => resource(uri, await service.getTrainerPersona()),
  );

    this.server.registerResource(
    "fitness-current-program",
    "fitness://current-program",
    {
      title: "Current Program",
      description: "Active versioned training program.",
      mimeType: "application/json",
    },
    async (uri) => resource(uri, await service.getCurrentProgram()),
  );

    this.server.registerResource(
    "fitness-decision-rules",
    "fitness://decision-rules",
    {
      title: "Decision Rules",
      description: "Stored coaching decision rules.",
      mimeType: "application/json",
    },
    async (uri) => resource(uri, await service.getDecisionRules()),
  );
  }
}

const mcpHandler = FitnessCoachMCP.serve("/mcp", { binding: "FitnessCoachMCP" });

export default {
  fetch(request: Request, env: Env, ctx: ExecutionContext) {
    const url = new URL(request.url);

    if (url.pathname === "/" && request.method === "GET") {
      return Response.json({
        name: "AI Fitness Coach MCP Server",
        endpoint: "/mcp",
        auth: env.MCP_SHARED_SECRET ? "bearer" : "none",
      });
    }

    if (!url.pathname.startsWith("/mcp")) {
      return new Response("Not found", { status: 404 });
    }

    const unauthorized = authorize(request, env);
    if (unauthorized) return unauthorized;

    return mcpHandler.fetch(request, env, ctx);
  },
} satisfies ExportedHandler<Env>;

function authorize(request: Request, env: Env) {
  if (!env.MCP_SHARED_SECRET) return null;
  const header = request.headers.get("authorization");
  if (header === `Bearer ${env.MCP_SHARED_SECRET}`) return null;
  return Response.json(
    { error: "Unauthorized" },
    {
      status: 401,
      headers: {
        "WWW-Authenticate": 'Bearer realm="fitness-coach-mcp"',
      },
    },
  );
}

function result(data: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }],
  };
}

function resource(uri: URL, data: unknown) {
  return {
    contents: [
      {
        uri: uri.href,
        mimeType: "application/json",
        text: JSON.stringify(data, null, 2),
      },
    ],
  };
}
