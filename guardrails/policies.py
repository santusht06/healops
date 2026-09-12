"""Cedar-Style Policy Definitions & Tool Risk Classification for HealOps Layer 3."""

from enum import Enum
from typing import Dict, Any, List, Optional
import re


class RiskLevel(str, Enum):
    LOW = "LOW"            # Read-only telemetry, metrics, logs, probes
    MEDIUM = "MEDIUM"      # Non-destructive diagnostics, cache stats
    HIGH = "HIGH"          # Cache invalidation, configuration updates
    CRITICAL = "CRITICAL"  # Container restarts, process terminations, rollback


# Tool classification by risk profile
TOOL_RISK_MAP: Dict[str, RiskLevel] = {
    # Layer 1 Tools
    "lookup_past_incidents": RiskLevel.LOW,
    
    # Layer 2 Read-Only Diagnostics
    "get_system_telemetry": RiskLevel.LOW,
    "find_high_resource_processes": RiskLevel.LOW,
    "list_services": RiskLevel.LOW,
    "inspect_service_logs": RiskLevel.LOW,
    "probe_http_service": RiskLevel.LOW,
    "inspect_database_health": RiskLevel.LOW,
    "inspect_redis_memory": RiskLevel.LOW,

    # Layer 2 State Modifying / Remediation
    "flush_cache_namespace": RiskLevel.HIGH,
    "restart_service": RiskLevel.CRITICAL,
}

# Forbidden command/argument injection patterns
DANGEROUS_INJECTION_PATTERNS = [
    re.compile(r"rm\s+-rf", re.IGNORECASE),
    re.compile(r"drop\s+table", re.IGNORECASE),
    re.compile(r"shutdown\s+-h", re.IGNORECASE),
    re.compile(r"mkfs", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;", re.IGNORECASE),  # Fork bomb
    re.compile(r";\s*rm", re.IGNORECASE),
    re.compile(r"&&\s*rm", re.IGNORECASE),
]


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"


class PolicyEngine:
    """Evaluates policy constraints for tool executions."""

    def __init__(self, active_role: str = "oncall", auto_approve_remediation: bool = False):
        self.active_role = active_role
        self.auto_approve_remediation = auto_approve_remediation

    def evaluate(self, tool_name: str, tool_args: Dict[str, Any]) -> tuple[PolicyDecision, str]:
        """Evaluate whether a tool invocation is allowed, denied, or requires human approval."""
        # 1. Parameter Injection & Sanitization Check
        args_str = str(tool_args)
        for pattern in DANGEROUS_INJECTION_PATTERNS:
            if pattern.search(args_str):
                return PolicyDecision.DENY, f"SECURITY VIOLATION: Malicious argument pattern detected '{pattern.pattern}'"

        # 2. Scope Validation for Destructive Tools
        if tool_name == "flush_cache_namespace":
            prefix = tool_args.get("namespace_prefix", "")
            if prefix in ["*", "/", "", "healops:sessions"]:
                return PolicyDecision.DENY, "SAFETY DENIED: Blanket flush on root or session keys is strictly prohibited."

        # 3. Risk-Based Role RBAC Evaluation
        risk = TOOL_RISK_MAP.get(tool_name, RiskLevel.MEDIUM)

        if risk == RiskLevel.LOW:
            return PolicyDecision.ALLOW, "Policy: Read-only diagnostic tools permitted unconditionally."

        if risk == RiskLevel.HIGH:
            if self.active_role in ["sre", "admin"]:
                return PolicyDecision.ALLOW, f"Policy: Permitted for role '{self.active_role}'."
            return PolicyDecision.REQUIRE_CONFIRMATION, "Policy: High-risk cache invalidation requires SRE confirmation."

        if risk == RiskLevel.CRITICAL:
            if self.active_role == "admin" or self.auto_approve_remediation:
                return PolicyDecision.ALLOW, f"Policy: Permitted under '{self.active_role}' authority."
            return PolicyDecision.REQUIRE_CONFIRMATION, (
                f"GUARDRAIL INTERVENTION: Remediation action '{tool_name}' on target '{tool_args.get('service_name', 'target')}' "
                f"is CRITICAL. Manual SRE confirmation or admin token required."
            )

        return PolicyDecision.ALLOW, "Default allow."
