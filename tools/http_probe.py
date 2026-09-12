"""HTTP Service Health & Latency Prober for HealOps Layer 2."""

import time
from typing import Dict, Any
import httpx
from strands import tool


@tool
def probe_http_service(url: str, expected_status: int = 200, timeout_seconds: float = 3.0) -> Dict[str, Any]:
    """Sends an active HTTP probe to an endpoint to measure latency and verify health.
    
    Args:
        url: Full HTTP/HTTPS URL to probe (e.g. 'http://localhost:8080/health').
        expected_status: Expected HTTP status code (default 200).
        timeout_seconds: Maximum wait timeout before declaring timeout (default 3.0).
    """
    start_time = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            response = client.get(url)
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

            is_healthy = (response.status_code == expected_status) and (elapsed_ms < 2000.0)
            diagnosis = "HEALTHY" if is_healthy else "DEGRADED"

            if response.status_code >= 500:
                diagnosis = f"CRITICAL: HTTP {response.status_code} Server Error"
            elif elapsed_ms >= 2000.0:
                diagnosis = f"DEGRADED: High Latency ({elapsed_ms}ms)"

            return {
                "url": url,
                "status_code": response.status_code,
                "latency_ms": elapsed_ms,
                "healthy": is_healthy,
                "diagnosis": diagnosis,
                "response_preview": response.text[:200]
            }

    except httpx.ConnectError:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "url": url,
            "status_code": 0,
            "latency_ms": elapsed_ms,
            "healthy": False,
            "diagnosis": "CONNECTION_REFUSED: Target host/port unreachable.",
            "response_preview": ""
        }
    except httpx.TimeoutException:
        return {
            "url": url,
            "status_code": 504,
            "latency_ms": timeout_seconds * 1000,
            "healthy": False,
            "diagnosis": f"TIMEOUT: Endpoint did not respond within {timeout_seconds}s.",
            "response_preview": ""
        }
    except Exception as e:
        return {
            "url": url,
            "status_code": -1,
            "latency_ms": 0.0,
            "healthy": False,
            "diagnosis": f"ERROR: {str(e)}",
            "response_preview": ""
        }
