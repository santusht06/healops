"""Container & Service Management Tools for HealOps Layer 2.

Interacts with live Docker containers if Docker daemon is running,
and seamlessly provides fallback local process/mock service registry
for standalone and CI environments.
"""

import os
import json
import subprocess
import logging
from typing import List, Dict, Any
from strands import tool
from config import settings

logger = logging.getLogger("healops.container")

SERVICES_REGISTRY_FILE = os.path.join(settings.DATA_DIR, "services_registry.json")


def _is_docker_available() -> bool:
    """Check if docker daemon is reachable."""
    try:
        res = subprocess.run(["docker", "info"], capture_output=True, timeout=2)
        return res.returncode == 0
    except Exception:
        return False


def _get_local_services_registry() -> Dict[str, Any]:
    """Load or initialize local services registry."""
    if not os.path.exists(SERVICES_REGISTRY_FILE):
        default_services = {
            "api-gateway": {
                "status": "running",
                "port": 8080,
                "restart_count": 0,
                "logs_file": os.path.join(settings.DATA_DIR, "logs", "api-gateway.log"),
                "health": "degraded"
            },
            "order-db": {
                "status": "running",
                "port": 5432,
                "restart_count": 0,
                "logs_file": os.path.join(settings.DATA_DIR, "logs", "order-db.log"),
                "health": "healthy"
            },
            "cache-cluster": {
                "status": "running",
                "port": 6379,
                "restart_count": 0,
                "logs_file": os.path.join(settings.DATA_DIR, "logs", "cache-cluster.log"),
                "health": "healthy"
            }
        }
        os.makedirs(os.path.dirname(SERVICES_REGISTRY_FILE), exist_ok=True)
        os.makedirs(os.path.join(settings.DATA_DIR, "logs"), exist_ok=True)
        with open(SERVICES_REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(default_services, f, indent=2)

        # Seed sample incident log
        sample_log = (
            "2026-09-12T20:15:01Z [INFO] Worker process 4118 started.\n"
            "2026-09-12T20:18:22Z [WARNING] Upstream keepalive connection timeout after 5000ms.\n"
            "2026-09-12T20:19:10Z [ERROR] 502 Bad Gateway: Upstream connection pool exhausted (32/32 connections active).\n"
            "2026-09-12T20:19:11Z [CRITICAL] Request worker thread deadlocked waiting on socket handle.\n"
        )
        with open(default_services["api-gateway"]["logs_file"], "w", encoding="utf-8") as f:
            f.write(sample_log)

        return default_services

    with open(SERVICES_REGISTRY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@tool
def list_services() -> List[Dict[str, Any]]:
    """List all managed microservices and Docker containers with their health status.
    
    Returns:
        list of service summaries including name, status, and port.
    """
    if _is_docker_available():
        try:
            res = subprocess.run(
                ["docker", "ps", "--format", "{{json .}}"],
                capture_output=True, text=True, timeout=5
            )
            containers = []
            for line in res.stdout.strip().split("\n"):
                if line:
                    c = json.loads(line)
                    containers.append({
                        "name": c.get("Names"),
                        "status": c.get("Status"),
                        "image": c.get("Image"),
                        "ports": c.get("Ports")
                    })
            if containers:
                return containers
        except Exception as e:
            logger.warning(f"Error querying docker ps: {e}")

    # Fallback to local services registry
    registry = _get_local_services_registry()
    return [{"name": k, **v} for k, v in registry.items()]


@tool
def inspect_service_logs(service_name: str, lines: int = 50) -> str:
    """Fetch recent standard error and diagnostic logs from a service or container.
    
    Args:
        service_name: Name of the service or container (e.g. 'api-gateway', 'order-db').
        lines: Number of trailing log lines to retrieve (default 50).
    """
    if _is_docker_available():
        try:
            res = subprocess.run(
                ["docker", "logs", "--tail", str(lines), service_name],
                capture_output=True, text=True, timeout=5
            )
            if res.returncode == 0 and (res.stdout or res.stderr):
                return f"=== DOCKER LOGS: {service_name} ===\n" + res.stdout + res.stderr
        except Exception:
            pass

    # Read from local registry log file
    registry = _get_local_services_registry()
    if service_name in registry:
        log_path = registry[service_name].get("logs_file")
        if log_path and os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
                return f"=== SERVICE LOGS: {service_name} ===\n" + "".join(all_lines[-lines:])

    return f"No log entries found for service '{service_name}'."


@tool
def restart_service(service_name: str) -> str:
    """Restart a degraded or failed service container to restore service health.
    
    Args:
        service_name: Name of the service to restart.
    """
    if _is_docker_available():
        try:
            res = subprocess.run(["docker", "restart", service_name], capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return f"SUCCESS: Docker container '{service_name}' restarted successfully."
        except Exception as e:
            logger.warning(f"Docker restart failed: {e}")

    # Update local registry state
    registry = _get_local_services_registry()
    if service_name in registry:
        registry[service_name]["status"] = "running"
        registry[service_name]["health"] = "healthy"
        registry[service_name]["restart_count"] = registry[service_name].get("restart_count", 0) + 1
        with open(SERVICES_REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2)

        # Append restart event to log
        log_path = registry[service_name].get("logs_file")
        if log_path:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n[SYSTEM NOTICE] Service '{service_name}' restarted by HealOps Auto-Remediation.\n")

        return f"SUCCESS: Service '{service_name}' was safely restarted. Health status reset to 'healthy'."

    return f"FAILED: Service '{service_name}' was not found in active registry."
