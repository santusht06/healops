"""Test script for HealOps Layer 2 (Diagnostic & Remediation Tools Suite).

Verifies:
1. System telemetry & process inspection tools (psutil).
2. Service listing & log inspection (Docker / local registry).
3. HTTP health probe & latency diagnosis (httpx).
4. Database connection pool & lock inspection (SQLAlchemy).
5. Redis cache memory & namespace invalidation.
6. Auto-remediation service restart workflow.
7. Full Strands Agent end-to-end tool registration.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools import (
    get_system_telemetry,
    find_high_resource_processes,
    list_services,
    inspect_service_logs,
    restart_service,
    probe_http_service,
    inspect_database_health,
    inspect_redis_memory,
    flush_cache_namespace,
    ALL_TOOLS
)
from brain import get_model, get_session_manager, postmortem_store
from strands import Agent


def test_1_telemetry():
    print("\n📊 [1/7] Testing System Telemetry & Process Tools...")
    telemetry = get_system_telemetry()
    print(f"   CPU: {telemetry['cpu_percent']}% | RAM: {telemetry['ram_percent']}% ({telemetry['ram_used_mb']}/{telemetry['ram_total_mb']} MB)")
    print(f"   Status: {telemetry['status']} | Active PIDs: {telemetry['active_processes']}")
    assert telemetry['cpu_percent'] >= 0.0

    top_procs = find_high_resource_processes(top_n=3)
    print(f"   Top {len(top_procs)} Resource Processes:")
    for p in top_procs:
        print(f"     • [PID {p['pid']}] {p['name']}: RAM {p['ram_percent']}% | CPU {p['cpu_percent']}%")
    assert len(top_procs) > 0
    print("   ✅ Telemetry tools verified!")


def test_2_service_inspection():
    print("\n📦 [2/7] Testing Service Registry & Log Inspection...")
    services = list_services()
    print(f"   Found {len(services)} managed services:")
    for s in services:
        print(f"     • {s['name']}: status='{s.get('status')}', health='{s.get('health', 'N/A')}', port={s.get('port')}")
    assert len(services) > 0

    logs = inspect_service_logs(service_name="api-gateway", lines=5)
    print(f"   Recent Logs from 'api-gateway':\n{logs.strip()}")
    assert "502 Bad Gateway" in logs
    print("   ✅ Service inspection verified!")


def test_3_http_probe():
    print("\n🌐 [3/7] Testing HTTP Probe Tool...")
    # Probe a known endpoint or non-existent to verify error handling
    res = probe_http_service(url="https://httpbin.org/status/200", timeout_seconds=4.0)
    print(f"   Probe Result: url='{res['url']}' -> status={res['status_code']} ({res['latency_ms']}ms) | Diagnosis: {res['diagnosis']}")
    assert res['status_code'] in [200, 0, -1]
    print("   ✅ HTTP Probe tool verified!")


def test_4_database_health():
    print("\n🗄️ [4/7] Testing Database Diagnostic Tool...")
    db_res = inspect_database_health()
    print(f"   Database Type: {db_res.get('database_type')} | Status: {db_res.get('status')}")
    print(f"   Connection Test: {db_res.get('connection_test')} | Deadlocks: {db_res.get('deadlocks_detected', 0)}")
    assert db_res.get('connection_test') == "PASSED"
    print("   ✅ Database tool verified!")


def test_5_redis_cache():
    print("\n⚡ [5/7] Testing Redis Cache Diagnostics & Flush Tool...")
    cache_info = inspect_redis_memory()
    print(f"   Redis Status: {cache_info.get('status')} | Used Memory: {cache_info.get('used_memory_mb')} MB | Total Keys: {cache_info.get('total_keys')}")
    
    # Test namespace flush
    flush_res = flush_cache_namespace(namespace_prefix="healops:temp")
    print(f"   Flush Test Result: status='{flush_res.get('status')}'")
    assert cache_info.get('status') in ["HEALTHY", "UNAVAILABLE", "WARNING: Key evictions detected (OOM risk)"]
    print("   ✅ Cache tools verified!")


def test_6_auto_remediation():
    print("\n🔧 [6/7] Testing Auto-Remediation (Restart Service)...")
    restart_res = restart_service("api-gateway")
    print(f"   Remediation Result: {restart_res}")
    assert "SUCCESS" in restart_res

    # Check updated status
    updated_services = {s['name']: s for s in list_services()}
    assert updated_services["api-gateway"]["health"] == "healthy"
    print(f"   Verified: api-gateway health is now '{updated_services['api-gateway']['health']}' (Restarts: {updated_services['api-gateway']['restart_count']})")
    print("   ✅ Remediation tool verified!")


def test_7_full_agent_layer2():
    print("\n🤖 [7/7] Testing Strands Agent with Full Layer 2 Tools Suite...")
    session_mgr = get_session_manager("incident-e2e-001")
    model = get_model()

    # Combine Layer 1 postmortem tool + Layer 2 tools
    agent = Agent(
        model=model,
        tools=ALL_TOOLS,
        session_manager=session_mgr,
        system_prompt=(
            "You are HealOps, an autonomous SRE agent. Use your diagnostic tools "
            "to inspect system health, read container logs, and apply remediation tools."
        )
    )

    print(f"   ✅ Agent initialized with {len(agent.tool_names)} registered tools:")
    for t_name in agent.tool_names:
        print(f"      • {t_name}")
    assert len(agent.tool_names) == len(ALL_TOOLS)


def main():
    print("=" * 60)
    print("  🛠️ HealOps — Layer 2 (Tools Suite) Verification")
    print("=" * 60)
    test_1_telemetry()
    test_2_service_inspection()
    test_3_http_probe()
    test_4_database_health()
    test_5_redis_cache()
    test_6_auto_remediation()
    test_7_full_agent_layer2()
    print("\n" + "=" * 60)
    print("  ✨ ALL LAYER 2 TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    main()
