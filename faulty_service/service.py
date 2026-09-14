"""
Intentional Faulty Microservice: Payment & Checkout Gateway
Port: 8085
Designed for real-world SRE autonomous diagnosis, live log streaming, and Cedar policy auto-remediation.
"""

import os
import sys
import time
import json
import asyncio
import traceback
from typing import List, Dict, Any
from datetime import datetime
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Payment & Checkout Microservice", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Persistent Log File Location
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = os.path.join(BASE_DIR, "data", "logs", "payment-gateway.log")
os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)

# Service Runtime State
service_state = {
    "name": "payment-gateway",
    "port": 8085,
    "status": "HEALTHY",   # HEALTHY, DEADLOCKED_502, MEMORY_LEAK_503
    "active_connections": 4,
    "max_connections": 16,
    "requests_served": 1420,
    "error_count": 0,
    "restarts": 0,
    "start_time": time.time(),
    "leaked_memory_mb": 0.0
}

# WebSocket Connected Clients for Live Log Streaming
log_clients: List[WebSocket] = []
log_history: List[Dict[str, Any]] = []

def emit_log(level: str, message: str, meta: Dict[str, Any] = None):
    """Emit formatted log event to console, log file, and all WebSocket subscribers."""
    now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    entry = {
        "timestamp": now_str,
        "level": level.upper(),
        "service": "payment-gateway",
        "message": message,
        "meta": meta or {}
    }
    
    # Keep history bounded
    log_history.append(entry)
    if len(log_history) > 200:
        log_history.pop(0)

    # Append to file
    try:
        with open(LOG_FILE_PATH, "a") as f:
            f.write(f"[{entry['timestamp']}] [{entry['level']}] {entry['message']}\n")
    except Exception:
        pass

    # Async broadcast scheduled in active loop if running
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            asyncio.create_task(broadcast_log(entry))
    except RuntimeError:
        pass


async def broadcast_log(entry: Dict[str, Any]):
    """Send log line to all active WebSocket listeners."""
    dead = []
    for ws in log_clients:
        try:
            await ws.send_json(entry)
        except Exception:
            dead.append(ws)
    for d in dead:
        if d in log_clients:
            log_clients.remove(d)


@app.on_event("startup")
async def startup_event():
    emit_log("INFO", "Payment & Checkout Gateway v2.1.0 initialized on :8085")
    emit_log("INFO", "Worker pool initialized: 16 clean sockets allocated across 4 worker threads")
    asyncio.create_task(background_traffic_simulator())


async def background_traffic_simulator():
    """Generates real-time synthetic traffic logs so viewers see continuous activity."""
    endpoints = ["/api/checkout", "/api/transactions/verify", "/api/stripe/webhook", "/healthz"]
    while True:
        await asyncio.sleep(2.0)
        status = service_state["status"]
        if status == "HEALTHY":
            service_state["requests_served"] += 1
            ep = endpoints[service_state["requests_served"] % len(endpoints)]
            emit_log("INFO", f"HTTP 200 GET {ep} - 24ms - client_id=usr_9281x status=PROCESSED")
        elif status == "DEADLOCKED_502":
            service_state["error_count"] += 1
            emit_log("ERROR", "HTTP 502 Bad Gateway: Connection pool exhausted (16/16 worker sockets deadlocked)")
            emit_log("CRITICAL", "ThreadStarvationException: Upstream worker pool unable to acquire lock on socket fd 42. Request timed out after 30000ms.")
        elif status == "MEMORY_LEAK_503":
            service_state["error_count"] += 1
            service_state["leaked_memory_mb"] += 14.5
            emit_log("WARN", f"MemoryPressureWarning: Heap usage at {service_state['leaked_memory_mb']:.1f}MB / 512MB threshold")
            emit_log("ERROR", "HTTP 503 Service Unavailable: Garbage collection paused for 2400ms. Refusing connections.")


# ==========================================
# REST API Endpoints
# ==========================================

@app.get("/healthz")
async def health_check():
    """Live health check endpoint inspected by SRE agents and load balancers."""
    status = service_state["status"]
    if status == "DEADLOCKED_502":
        emit_log("ERROR", "Incoming probe /healthz FAILED: 502 Bad Gateway (Pool deadlocked)")
        raise HTTPException(
            status_code=502,
            detail="Upstream Connection Pool Exhausted: 16/16 worker threads deadlocked in epoll_wait"
        )
    elif status == "MEMORY_LEAK_503":
        emit_log("ERROR", "Incoming probe /healthz FAILED: 503 Out of Memory (OOM threshold exceeded)")
        raise HTTPException(
            status_code=503,
            detail="Service Unavailable: Heap allocation failed, memory pool exhausted"
        )

    return {
        "status": "healthy",
        "service": "payment-gateway",
        "port": 8085,
        "active_sockets": service_state["active_connections"],
        "max_sockets": service_state["max_connections"],
        "requests_served": service_state["requests_served"],
        "restarts": service_state["restarts"],
        "uptime_seconds": round(time.time() - service_state["start_time"], 1)
    }


@app.get("/api/status")
async def get_status():
    return service_state


class CheckoutRequest(BaseModel):
    user_id: str = "usr_demo123"
    amount: float = 149.99
    currency: str = "USD"


@app.post("/api/checkout")
async def post_checkout(req: CheckoutRequest):
    status = service_state["status"]
    if status != "HEALTHY":
        raise HTTPException(status_code=502, detail="Gateway Deadlocked: Transaction aborted")
    
    emit_log("INFO", f"Payment processed successfully for {req.user_id}: ${req.amount} {req.currency}")
    return {"status": "SUCCESS", "tx_id": f"tx_{int(time.time()*1000)}", "amount": req.amount}


# ==========================================
# Intentional Fault Injections
# ==========================================

@app.post("/fault/deadlock")
async def trigger_deadlock():
    """Trigger intentional connection pool exhaustion and deadlock."""
    service_state["status"] = "DEADLOCKED_502"
    service_state["active_connections"] = 16
    emit_log("CRITICAL", "⚡ INJECTED FAULT: Upstream Worker Connection Pool Deadlock triggered!")
    emit_log("ERROR", "Traceback (most recent call last):\n"
                      "  File '/app/workers/pool.py', line 142, in acquire_connection\n"
                      "    lock.acquire(timeout=30)\n"
                      "DeadlockDetected: All 16 worker sockets in unrecoverable epoll_wait lock.")
    return {"status": "FAULT_TRIGGERED", "mode": "DEADLOCKED_502", "message": "Service is now returning 502 Bad Gateway"}


@app.post("/fault/leak")
async def trigger_leak():
    """Trigger intentional memory pressure."""
    service_state["status"] = "MEMORY_LEAK_503"
    emit_log("CRITICAL", "⚡ INJECTED FAULT: Memory Runaway Leak triggered!")
    return {"status": "FAULT_TRIGGERED", "mode": "MEMORY_LEAK_503"}


@app.post("/fault/reset")
async def reset_fault():
    """Manual reset back to healthy."""
    service_state["status"] = "HEALTHY"
    service_state["active_connections"] = 4
    service_state["leaked_memory_mb"] = 0.0
    emit_log("INFO", "Reset command received. Service baseline restored to HEALTHY.")
    return {"status": "RESET_OK"}


@app.post("/service/restart")
async def restart_service():
    """Simulates safe microservice restart orchestrated by SRE Agent."""
    emit_log("WARN", "RESTART SIGNAL RECEIVED: Gracefully terminating deadlocked worker threads...")
    await asyncio.sleep(1.0)
    service_state["status"] = "HEALTHY"
    service_state["active_connections"] = 4
    service_state["restarts"] += 1
    service_state["start_time"] = time.time()
    service_state["leaked_memory_mb"] = 0.0
    emit_log("INFO", "Worker pool re-initialized: Sockets flushed, PID refreshed, listening on :8085")
    emit_log("INFO", "✅ Service restored to 100% operational health.")
    return {"status": "RESTARTED_OK", "restarts": service_state["restarts"]}


# ==========================================
# WebSocket Endpoint for Live Log Streaming
# ==========================================

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    log_clients.append(websocket)
    try:
        # Send recent log history first
        for entry in log_history[-30:]:
            await websocket.send_json(entry)
        
        while True:
            # Keepalive
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in log_clients:
            log_clients.remove(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8085)
