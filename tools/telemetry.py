"""System Telemetry & Resource Monitoring Tool for HealOps Layer 2."""

from typing import Dict, Any, List
import psutil
from strands import tool


@tool
def get_system_telemetry() -> Dict[str, Any]:
    """Inspects live server CPU, Memory, Disk, and load averages.
    
    Returns:
        dict: Real-time system utilization statistics and health flags.
    """
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    load_1m, load_5m, load_15m = psutil.getloadavg()

    cpu_pct = psutil.cpu_percent(interval=0.5)
    ram_pct = vm.percent
    disk_pct = disk.percent

    # Anomaly detection heuristics
    alerts = []
    if ram_pct > 85.0:
        alerts.append(f"CRITICAL: Memory pressure at {ram_pct}% (>85%)")
    elif ram_pct > 70.0:
        alerts.append(f"WARNING: Elevated Memory usage at {ram_pct}%")

    if cpu_pct > 80.0:
        alerts.append(f"CRITICAL: CPU spike at {cpu_pct}%")

    if disk_pct > 90.0:
        alerts.append(f"CRITICAL: Disk capacity nearly exhausted at {disk_pct}%")

    return {
        "cpu_percent": cpu_pct,
        "ram_percent": ram_pct,
        "ram_used_mb": round((vm.total - vm.available) / (1024 * 1024), 2),
        "ram_total_mb": round(vm.total / (1024 * 1024), 2),
        "disk_percent": disk_pct,
        "disk_free_gb": round(disk.free / (1024 * 1024 * 1024), 2),
        "load_averages": [round(load_1m, 2), round(load_5m, 2), round(load_15m, 2)],
        "active_processes": len(psutil.pids()),
        "status": "ALERT" if alerts else "HEALTHY",
        "alerts": alerts
    }


@tool
def find_high_resource_processes(top_n: int = 5) -> List[Dict[str, Any]]:
    """Identifies the top CPU and Memory consuming processes on the system.
    
    Args:
        top_n: Number of top resource-consuming processes to return.
    """
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
        try:
            info = p.info
            procs.append({
                "pid": info['pid'],
                "name": info['name'],
                "cpu_percent": round(info['cpu_percent'] or 0.0, 1),
                "ram_percent": round(info['memory_percent'] or 0.0, 1),
                "status": info['status']
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Sort primarily by memory, then cpu
    procs.sort(key=lambda x: (x['ram_percent'], x['cpu_percent']), reverse=True)
    return procs[:top_n]
