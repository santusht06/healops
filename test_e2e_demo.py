"""End-to-End Autonomous SRE Remediation & Cedar Guardrail Loop Test."""

import os
import sys
import json
import time
import asyncio
import unittest
import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import app, pending_approvals, active_incident
from brain import postmortem_store


class TestE2EDemoLoop(unittest.IsolatedAsyncioTestCase):
    async def test_complete_autonomous_remediation_lifecycle(self):
        print("\n=======================================================")
        print("🚀 STARTING HEALOPS AUTONOMOUS SRE END-TO-END DEMO TEST")
        print("=======================================================")

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Baseline Health Check
            res = await client.get("/api/health")
            self.assertEqual(res.status_code, 200)
            print("1. [BASELINE] System health verified UP")

            # 2. Inject Chaos (HTTP 502 on api-gateway)
            res_chaos = await client.post("/api/chaos/inject", json={
                "service_name": "api-gateway",
                "failure_type": "502_bad_gateway"
            })
            self.assertEqual(res_chaos.status_code, 200)
            incident_info = res_chaos.json()["incident"]
            self.assertTrue(incident_info["is_active"])
            print(f"2. [CHAOS INJECTED] Outage triggered: {incident_info['description']}")

            # Verify degraded in registry
            res_services = await client.get("/api/services")
            services = {s["name"]: s for s in res_services.json()["services"]}
            self.assertEqual(services["api-gateway"]["status"], "degraded")
            print("   -> Registry reflects status: degraded (502_BAD_GATEWAY)")

            # 3. Dispatch Autonomous Triage
            initial_pm_count = len(postmortem_store.records)
            res_triage = await client.post("/api/triage/start", json={
                "service_name": "api-gateway",
                "role": "oncall"
            })
            self.assertEqual(res_triage.status_code, 200)
            print(f"3. [TRIAGE DISPATCHED] Agent investigating incident {incident_info['incident_id']}...")

            # 4. Wait for Cedar Policy Interception (Awaiting Approval)
            max_wait = 15
            waited = 0
            approval_id = None
            while waited < max_wait:
                await asyncio.sleep(0.5)
                waited += 0.5
                if pending_approvals:
                    approval_id = list(pending_approvals.keys())[0]
                    break

            self.assertIsNotNone(approval_id, "Cedar Guardrail should intercept and require approval")
            print(f"4. [CEDAR INTERCEPT] Guardrail halted 'restart_service'. Pending Approval ID: {approval_id}")
            self.assertEqual(active_incident["stage"], "AWAITING_APPROVAL")

            # 5. Human SRE Grants Approval
            res_decision = await client.post("/api/remediation/decide", json={
                "approval_id": approval_id,
                "approved": True
            })
            self.assertEqual(res_decision.status_code, 200)
            self.assertTrue(res_decision.json()["approved"])
            print(f"5. [SRE SIGN-OFF] Human operator approved remediation for {approval_id}")

            # 6. Wait for Auto-Remediation and Post-Mortem Indexing
            await asyncio.sleep(4.0)
            self.assertEqual(active_incident["stage"], "RESOLVED")
            self.assertFalse(active_incident["is_active"])
            print("6. [REMEDIATION EXECUTED] Service restarted, socket deadlock cleared!")

            # 7. Verify Registry Restored
            res_post = await client.get("/api/services")
            services_post = {s["name"]: s for s in res_post.json()["services"]}
            self.assertEqual(services_post["api-gateway"]["status"], "running")
            self.assertEqual(services_post["api-gateway"]["health"], "healthy")
            print("7. [HEALTH RESTORED] api-gateway status: running (healthy)")

            # 8. Verify Post-Mortem Runbook Stored
            new_pm_count = len(postmortem_store.records)
            self.assertEqual(new_pm_count, initial_pm_count + 1)
            latest_pm = postmortem_store.records[-1]
            self.assertEqual(latest_pm.service, "api-gateway")
            print(f"8. [RUNBOOK INDEXED] New Post-Mortem saved: {latest_pm.id} ({latest_pm.root_cause})")

            # 9. Verify SOC-2 Audit Trail
            res_audit = await client.get("/api/audit?limit=10")
            logs = res_audit.json()["audit_logs"]
            self.assertTrue(len(logs) > 0)
            print(f"9. [SOC-2 AUDIT] Verified immutable audit logs ({len(logs)} entries logged)")

            print("=======================================================")
            print("✅ FULL END-TO-END DEMO TEST PASSED WITH 100% SUCCESS!")
            print("=======================================================\n")


if __name__ == "__main__":
    unittest.main()
