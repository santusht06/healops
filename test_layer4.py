"""Test Layer 4: Server REST Endpoints, Static Serving, and Chaos Workflow."""

import os
import sys
import unittest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import app
from config import settings


class TestLayer4Server(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_01_health_endpoint(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "UP")
        self.assertEqual(data["app"], settings.APP_NAME)
        print("✓ /api/health verified")

    def test_02_telemetry_endpoint(self):
        res = self.client.get("/api/telemetry")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("system", data)
        self.assertIn("cpu_percent", data["system"])
        self.assertIn("ram_percent", data["system"])
        self.assertIn("database", data)
        print("✓ /api/telemetry verified")

    def test_03_services_endpoint(self):
        res = self.client.get("/api/services")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("services", data)
        self.assertTrue(len(data["services"]) > 0)
        print(f"✓ /api/services verified with {len(data['services'])} services")

    def test_04_audit_and_postmortems(self):
        res = self.client.get("/api/audit")
        self.assertEqual(res.status_code, 200)
        self.assertIn("audit_logs", res.json())

        res_pm = self.client.get("/api/postmortems")
        self.assertEqual(res_pm.status_code, 200)
        self.assertIn("postmortems", res_pm.json())
        print("✓ /api/audit and /api/postmortems verified")

    def test_05_chaos_injection_and_reset(self):
        # 1. Inject chaos
        res_inject = self.client.post("/api/chaos/inject", json={"service_name": "api-gateway", "failure_type": "502_bad_gateway"})
        self.assertEqual(res_inject.status_code, 200)
        self.assertEqual(res_inject.json()["status"], "CHAOS_ACTIVE")

        # Verify service state degraded
        res_serv = self.client.get("/api/services")
        services = {s["name"]: s for s in res_serv.json()["services"]}
        self.assertEqual(services["api-gateway"]["status"], "degraded")
        self.assertIn("502", services["api-gateway"]["health"])

        # 2. Reset chaos
        res_reset = self.client.post("/api/chaos/reset")
        self.assertEqual(res_reset.status_code, 200)
        self.assertEqual(res_reset.json()["status"], "RESET_COMPLETED")

        # Verify service state restored
        res_serv2 = self.client.get("/api/services")
        services2 = {s["name"]: s for s in res_serv2.json()["services"]}
        self.assertEqual(services2["api-gateway"]["status"], "running")
        print("✓ /api/chaos/inject and /api/chaos/reset verified")

    def test_06_static_ui_serving(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("<title>HealOps", res.text)
        self.assertIn("CEDAR POLICY", res.text)

        res_css = self.client.get("/style.css")
        self.assertEqual(res_css.status_code, 200)

        res_js = self.client.get("/app.js")
        self.assertEqual(res_js.status_code, 200)
        print("✓ Static UI assets (HTML, CSS, JS) verified")


if __name__ == "__main__":
    unittest.main()
