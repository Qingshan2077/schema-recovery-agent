"""Server-side risk, RBAC, environment and separation-of-duties policy."""

from __future__ import annotations

from backend.agent.dba.contracts import ActorContext, ApprovalRequirement


POLICY_VERSION = "dba-policy-v1"
PROTECTED = {"users", "orders", "products", "mysql", "information_schema", "pg_catalog"}


def evaluate_policy(*, ast: dict, actor: ActorContext, environment: str, dry_run_capability: str) -> dict:
    kinds = {item["type"] for item in ast["statements"]}
    targets = {target.casefold().split(".")[-1] for item in ast["statements"] for target in item["target_objects"]}
    reasons = []
    risk = "low"
    decision = "require_approval"
    if targets & PROTECTED:
        risk, decision = "critical", "deny"
        reasons.append("protected_object")
    if "DROP" in kinds:
        risk = "critical" if environment == "production" else "high"
        reasons.append("destructive_drop")
    elif "ALTER" in kinds:
        risk = "high" if environment == "production" else "medium"
        reasons.append("table_rewrite_or_lock_possible")
    if dry_run_capability == "limited":
        risk = {"low": "medium", "medium": "high", "high": "critical", "critical": "critical"}[risk]
        reasons.append("dry_run_limited")
    if environment == "production" and "dba_plan_production" not in actor.capabilities:
        decision = "deny"
        reasons.append("production_plan_forbidden")
    requirements = [ApprovalRequirement(role="dba_approver")]
    if risk == "critical": requirements.append(ApprovalRequirement(role="security_approver"))
    return {"decision": decision, "risk_level": risk, "reason_codes": reasons or ["approval_required"], "requirements": requirements, "policy_version": POLICY_VERSION}
