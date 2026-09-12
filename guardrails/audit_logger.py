"""Structured Audit Trail Logger for HealOps Layer 3 SOC2 Compliance."""

import os
import json
import time
import logging
from typing import Dict, Any, Optional
from config import settings
from brain.session import get_redis_client

logger = logging.getLogger("healops.audit")


class AuditLogger:
    """Records chronological, immutable audit logs for all agent actions."""

    def __init__(self, log_path: Optional[str] = None):
        self.log_path = log_path or os.path.join(settings.DATA_DIR, "audit_log.jsonl")
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self.redis_client = get_redis_client()

    def record_event(
        self,
        event_type: str,
        tool_name: str,
        arguments: Dict[str, Any],
        decision: str,
        reason: str,
        role: str = "oncall",
        duration_ms: float = 0.0
    ) -> Dict[str, Any]:
        """Record an audit trail entry to JSON Lines and Redis stream."""
        event = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "epoch_ms": int(time.time() * 1000),
            "event_type": event_type,
            "tool_name": tool_name,
            "arguments": arguments,
            "decision": decision,
            "reason": reason,
            "role": role,
            "duration_ms": duration_ms
        }

        # 1. Append to local JSON Lines file
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.error(f"Failed writing audit log to disk: {e}")

        # 2. Push to Redis for real-time dashboard consumption
        if self.redis_client is not None:
            try:
                self.redis_client.lpush("healops:audit_events", json.dumps(event))
                self.redis_client.ltrim("healops:audit_events", 0, 99)  # Keep latest 100
            except Exception:
                pass

        logger.info(f"AUDIT [{decision}]: Tool '{tool_name}' (Role: {role}) - {reason}")
        return event

    def get_recent_events(self, limit: int = 20) -> list[dict]:
        """Fetch the most recent audit records."""
        if not os.path.exists(self.log_path):
            return []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            return [json.loads(line) for line in reversed(lines[-limit:])]
        except Exception as e:
            logger.error(f"Failed reading audit log: {e}")
            return []


# Global singleton
audit_logger = AuditLogger()
