TRACE_SCHEMA_VERSION = "1.0"

ALLOWED_ATTRIBUTES = {
    "service.name", "service.version", "service.environment", "deployment.id", "git.sha",
    "eval.run.id", "eval.case.id", "dataset.id", "dataset.version", "dataset.split",
    "agent.id", "node.id", "engine", "attempt", "gen_ai.provider", "model.profile",
    "model.id", "prompt.version", "prompt.hash", "tool.name", "tool.version", "tool.call_id",
    "db.system", "db.namespace_hash", "snapshot.id", "snapshot.hash", "relation.id",
    "evidence.ids", "memory.ids", "input.tokens", "output.tokens", "cache.tokens",
    "cost.estimate", "first_token_ms", "duration_ms", "retry_count", "status",
    "error.type", "fallback.reason", "redaction.level", "payload.stored",
}
