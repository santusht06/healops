"""Chaos Service Simulator for HealOps Hackathon Live Demos.

Simulates real-world microservice degradation and failures:
- HTTP 502 Bad Gateway (Upstream pool exhaustion)
- High Latency spikes (>3000ms)
- Out of Memory / high resource utilization
"""

from fastapi import FastAPI, Response, status
from pydantic import BaseModel
import time

app = FastAPI(title="Chaos Microservice Mock")


class ChaosState:
    is_failing: bool = False
    failure_type: str = "502_bad_gateway"
    latency_seconds: float = 0.0
    failure_count: int = 0


chaos = ChaosState()


class ChaosConfigRequest(BaseModel):
    failure_type: str = "502_bad_gateway"
    latency_seconds: float = 0.0


@app.get("/healthz")
def healthz(response: Response):
    """Health check endpoint monitored by SRE."""
    if chaos.latency_seconds > 0:
        time.sleep(chaos.latency_seconds)

    if chaos.is_failing:
        chaos.failure_count += 1
        response.status_code = status.HTTP_502_BAD_GATEWAY
        return {
            "status": "DOWN",
            "error": "UpstreamConnectionPoolExhausted",
            "message": "FATAL: Connection pool (32/32) saturated. Upstream workers deadlocked.",
            "failure_count": chaos.failure_count
        }

    return {
        "status": "UP",
        "service": "api-gateway",
        "uptime_seconds": 3600,
        "active_workers": 4
    }


@app.post("/chaos/inject")
def inject_chaos(config: ChaosConfigRequest):
    """Inject a failure state to demonstrate HealOps autonomous remediation."""
    chaos.is_failing = True
    chaos.failure_type = config.failure_type
    chaos.latency_seconds = config.latency_seconds
    chaos.failure_count = 0
    return {"message": f"Injected chaos: {config.failure_type}", "active": True}


@app.post("/chaos/reset")
def reset_chaos():
    """Reset service back to healthy status."""
    chaos.is_failing = False
    chaos.latency_seconds = 0.0
    chaos.failure_count = 0
    return {"message": "Chaos cleared. Service restored to healthy status.", "active": False}
