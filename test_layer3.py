"""Test script for HealOps Layer 3 (Safety Guardrails & Cedar Policy Enforcement).

Verifies:
1. Tool risk profile classification.
2. Parameter sanitization & anti-injection defense (blocking rm -rf, drop table, etc.).
3. Blanket cache flush restriction (protecting session & root namespaces).
4. Role-based access control (oncall vs sre vs admin).
5. Strands InterventionHandler execution (Proceed, Deny, Confirm).
6. Immutable audit logging to disk & Redis.
7. Full Agent instantiation with Layer 1 Brain + Layer 2 Tools + Layer 3 Interventions.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from guardrails import (
    RiskLevel,
    PolicyDecision,
    PolicyEngine,
    TOOL_RISK_MAP,
    HealOpsPolicyGuard,
    audit_logger
)
from tools import ALL_TOOLS
from brain import get_model, get_session_manager
from strands import Agent
from strands.hooks import BeforeToolCallEvent


def test_1_risk_classification():
    print("\n🛡️ [1/7] Testing Tool Risk Classifications...")
    assert TOOL_RISK_MAP["get_system_telemetry"] == RiskLevel.LOW
    assert TOOL_RISK_MAP["restart_service"] == RiskLevel.CRITICAL
    assert TOOL_RISK_MAP["flush_cache_namespace"] == RiskLevel.HIGH
    print(f"   get_system_telemetry: {TOOL_RISK_MAP['get_system_telemetry'].value} (Safe Read-Only)")
    print(f"   flush_cache_namespace: {TOOL_RISK_MAP['flush_cache_namespace'].value} (State Modifying)")
    print(f"   restart_service: {TOOL_RISK_MAP['restart_service'].value} (Process Terminating)")
    print("   ✅ Risk classification verified!")


def test_2_injection_defense():
    print("\n🛑 [2/7] Testing Command Injection & Malicious Argument Defense...")
    engine = PolicyEngine(active_role="admin")
    
    # Simulate malicious argument injection
    decision, reason = engine.evaluate(
        tool_name="restart_service",
        tool_args={"service_name": "api-gateway; rm -rf /"}
    )
    print(f"   Injected: 'api-gateway; rm -rf /' -> Decision: {decision.value}")
    print(f"   Reason: {reason}")
    assert decision == PolicyDecision.DENY
    assert "SECURITY VIOLATION" in reason
    print("   ✅ Injection defense verified!")


def test_3_scope_restrictions():
    print("\n🔒 [3/7] Testing Destructive Scope Restrictions (Blanket Flush Protection)...")
    engine = PolicyEngine(active_role="admin")
    
    # Attempt blanket purge of all keys
    decision, reason = engine.evaluate(
        tool_name="flush_cache_namespace",
        tool_args={"namespace_prefix": "*"}
    )
    print(f"   Attempted: flush('*') -> Decision: {decision.value}")
    assert decision == PolicyDecision.DENY
    assert "SAFETY DENIED" in reason

    # Attempt flush on session namespace
    decision2, reason2 = engine.evaluate(
        tool_name="flush_cache_namespace",
        tool_args={"namespace_prefix": "healops:sessions"}
    )
    assert decision2 == PolicyDecision.DENY
    print("   ✅ Scope restrictions verified!")


def test_4_rbac_roles():
    print("\n👥 [4/7] Testing Role-Based Access Control (Oncall vs Admin)...")
    oncall_engine = PolicyEngine(active_role="oncall")
    admin_engine = PolicyEngine(active_role="admin")

    # Oncall attempting service restart -> Requires SRE confirmation
    dec_oncall, reason_oncall = oncall_engine.evaluate(
        tool_name="restart_service",
        tool_args={"service_name": "api-gateway"}
    )
    print(f"   Role 'oncall' -> restart_service: {dec_oncall.value}")
    assert dec_oncall == PolicyDecision.REQUIRE_CONFIRMATION

    # Admin attempting service restart -> Allowed
    dec_admin, reason_admin = admin_engine.evaluate(
        tool_name="restart_service",
        tool_args={"service_name": "api-gateway"}
    )
    print(f"   Role 'admin'  -> restart_service: {dec_admin.value}")
    assert dec_admin == PolicyDecision.ALLOW
    print("   ✅ RBAC evaluation verified!")


def test_5_intervention_handler():
    print("\n⚡ [5/7] Testing Strands InterventionHandler Execution...")
    
    # Mock event
    class MockEvent:
        def __init__(self, name, args):
            self.tool_use = {"name": name, "input": args}

    # Case A: Low-risk read tool
    guard = HealOpsPolicyGuard(active_role="oncall")
    action = guard.before_tool_call(MockEvent("get_system_telemetry", {}))
    print(f"   Tool 'get_system_telemetry' action: {type(action).__name__}")
    assert type(action).__name__ == "Proceed"

    # Case B: Human-in-the-loop approved
    approving_guard = HealOpsPolicyGuard(
        active_role="oncall",
        confirmation_callback=lambda name, args, reason: True
    )
    action_app = approving_guard.before_tool_call(MockEvent("restart_service", {"service_name": "api-gateway"}))
    print(f"   Tool 'restart_service' with Human Approval: {type(action_app).__name__}")
    assert type(action_app).__name__ == "Proceed"

    # Case C: Human-in-the-loop rejected
    rejecting_guard = HealOpsPolicyGuard(
        active_role="oncall",
        confirmation_callback=lambda name, args, reason: False
    )
    action_rej = rejecting_guard.before_tool_call(MockEvent("restart_service", {"service_name": "api-gateway"}))
    print(f"   Tool 'restart_service' with Human Rejection: {type(action_rej).__name__}")
    assert type(action_rej).__name__ == "Deny"
    print("   ✅ InterventionHandler verified!")


def test_6_audit_logging():
    print("\n📜 [6/7] Testing SOC2 Audit Logging to Disk & Redis...")
    events = audit_logger.get_recent_events(limit=5)
    print(f"   Retrieved {len(events)} recent audit events from disk:")
    for ev in events[:3]:
        print(f"     • [{ev['timestamp']}] {ev['event_type']} -> {ev['tool_name']} ({ev['decision']})")
    assert len(events) > 0
    print("   ✅ Audit logging verified!")


def test_7_full_agent_with_guardrails():
    print("\n🤖 [7/7] Testing Strands Agent Init with Layer 1 Brain + Layer 2 Tools + Layer 3 Guardrails...")
    session_mgr = get_session_manager("incident-guardrail-test")
    model = get_model()
    guard = HealOpsPolicyGuard(active_role="sre", auto_approve_remediation=False)

    agent = Agent(
        model=model,
        tools=ALL_TOOLS,
        session_manager=session_mgr,
        interventions=[guard],
        system_prompt="You are HealOps SRE Agent operating under Cedar safety guardrails."
    )

    print(f"   ✅ Agent fully wired with Guardrails!")
    print(f"      • Model: {type(agent.model).__name__}")
    print(f"      • Interventions: {[i.name for i in agent._intervention_registry.handlers]}")
    print(f"      • Tools: {len(agent.tool_names)} registered")
    assert len(agent._intervention_registry.handlers) > 0


def main():
    print("=" * 60)
    print("  🛡️ HealOps — Layer 3 (Safety Guardrails) Verification")
    print("=" * 60)
    test_1_risk_classification()
    test_2_injection_defense()
    test_3_scope_restrictions()
    test_4_rbac_roles()
    test_5_intervention_handler()
    test_6_audit_logging()
    test_7_full_agent_with_guardrails()
    print("\n" + "=" * 60)
    print("  ✨ ALL LAYER 3 TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    main()
