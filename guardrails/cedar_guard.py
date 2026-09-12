"""Cedar-Style Policy Guardrail & Human-in-the-Loop Intervention Handler for HealOps."""

import time
import logging
from typing import Optional, Dict, Any
from strands.interventions import InterventionHandler, Proceed, Deny, Confirm
from strands.hooks import BeforeToolCallEvent, AfterToolCallEvent
from guardrails.policies import PolicyEngine, PolicyDecision
from guardrails.audit_logger import audit_logger

logger = logging.getLogger("healops.guardrails")


class HealOpsPolicyGuard(InterventionHandler):
    """Strands InterventionHandler enforcing Cedar-style safety policies on agent tool execution."""

    name = "healops-cedar-guard"

    def __init__(
        self,
        active_role: str = "oncall",
        auto_approve_remediation: bool = False,
        confirmation_callback: Optional[callable] = None
    ):
        super().__init__()
        self.policy_engine = PolicyEngine(
            active_role=active_role,
            auto_approve_remediation=auto_approve_remediation
        )
        self.confirmation_callback = confirmation_callback
        self._tool_start_times: Dict[str, float] = {}

    def before_tool_call(self, event: BeforeToolCallEvent, **kwargs: Any):
        """Intercepts tool call before execution to evaluate safety and RBAC policies."""
        tool_use = getattr(event, "tool_use", {}) or {}
        tool_name = tool_use.get("name", "unknown")
        tool_args = tool_use.get("input", {}) or {}

        # Track execution start time
        self._tool_start_times[tool_name] = time.perf_counter()

        # Evaluate against Cedar-style policy rules
        decision, reason = self.policy_engine.evaluate(tool_name, tool_args)

        # Audit attempt
        audit_logger.record_event(
            event_type="BEFORE_TOOL_CALL",
            tool_name=tool_name,
            arguments=tool_args,
            decision=decision.value,
            reason=reason,
            role=self.policy_engine.active_role
        )

        if decision == PolicyDecision.DENY:
            logger.warning(f"🛑 [POLICY DENIED] Tool '{tool_name}' blocked: {reason}")
            return Deny(reason=reason)

        elif decision == PolicyDecision.REQUIRE_CONFIRMATION:
            logger.info(f"⚠️ [CONFIRMATION REQUIRED] Tool '{tool_name}' triggered guardrail: {reason}")
            
            # If a custom interactive confirmation callback is supplied:
            if self.confirmation_callback is not None:
                approved = self.confirmation_callback(tool_name, tool_args, reason)
                if approved:
                    logger.info(f"✅ [HUMAN APPROVAL] SRE approved remediation '{tool_name}'.")
                    return Proceed(reason="Manually approved by SRE operator.")
                else:
                    logger.warning(f"❌ [HUMAN REJECTION] SRE rejected remediation '{tool_name}'.")
                    return Deny(reason="Remediation rejected by human SRE operator.")

            return Confirm(
                prompt=f"Are you sure you want to execute remediation tool '{tool_name}' on args {tool_args}?",
                reason=reason
            )

        logger.debug(f"✅ [POLICY PROCEED] Tool '{tool_name}' approved.")
        return Proceed()

    def after_tool_call(self, event: AfterToolCallEvent, **kwargs: Any):
        """Intercepts tool call after execution to record execution duration and metrics."""
        tool_use = getattr(event, "tool_use", {}) or {}
        tool_name = tool_use.get("name", "unknown")
        start_time = self._tool_start_times.pop(tool_name, time.perf_counter())
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        audit_logger.record_event(
            event_type="AFTER_TOOL_CALL",
            tool_name=tool_name,
            arguments=tool_use.get("input", {}) or {},
            decision="COMPLETED",
            reason=f"Executed in {duration_ms}ms",
            role=self.policy_engine.active_role,
            duration_ms=duration_ms
        )
        return Proceed()
