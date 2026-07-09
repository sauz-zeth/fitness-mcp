interface Env {
  DB: D1Database;
  FitnessCoachMCP: DurableObjectNamespace<import("./src/index").FitnessCoachMCP>;
  MCP_SHARED_SECRET?: string;
}
