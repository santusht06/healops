"""Historical Post-Mortem and SRE Runbook Store for HealOps Layer 1.

Enables HealOps to recall past incidents, diagnose known patterns,
and save newly resolved incident post-mortems for future reuse.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from config import settings

logger = logging.getLogger("healops.postmortems")


class IncidentRecord(BaseModel):
    id: str
    service: str
    symptom: str
    root_cause: str
    remediation_steps: List[str]
    preventive_action: str
    severity: str = "HIGH"
    tags: List[str] = Field(default_factory=list)


DEFAULT_POSTMORTEMS: List[Dict[str, Any]] = [
    {
        "id": "INC-2026-081",
        "service": "api-gateway",
        "symptom": "HTTP 502 Bad Gateway and latency spike > 5000ms",
        "root_cause": "Nginx upstream keepalive connection exhaustion due to unclosed keepalive connections from upstream FastAPI workers.",
        "remediation_steps": [
            "Inspect upstream status via HTTP ping",
            "Reload Nginx service configuration",
            "Restart stalled FastAPI worker containers"
        ],
        "preventive_action": "Increased upstream keepalive pool in nginx.conf from 32 to 128",
        "severity": "CRITICAL",
        "tags": ["nginx", "502", "fastapi", "connection_pool"]
    },
    {
        "id": "INC-2026-074",
        "service": "order-db",
        "symptom": "PostgreSQL connection pool exhausted. FATAL: remaining connection slots are reserved for non-replication superuser connections",
        "root_cause": "Long-running analytics query holding table lock with unindexed join on orders and audit_logs.",
        "remediation_steps": [
            "Identify blocking PID via pg_stat_activity",
            "Terminate blocking PID using pg_cancel_backend()",
            "Restart connection pooler (PgBouncer/SQLAlchemy pool)"
        ],
        "preventive_action": "Added index on audit_logs.order_id and set statement_timeout to 10s",
        "severity": "CRITICAL",
        "tags": ["postgres", "database", "deadlock", "connection_pool"]
    },
    {
        "id": "INC-2026-068",
        "service": "cache-cluster",
        "symptom": "Redis OOM (Out Of Memory) command not allowed when used memory > maxmemory",
        "root_cause": "Session keys written without TTL during flash sale traffic surge.",
        "remediation_steps": [
            "Check memory usage with redis-cli INFO memory",
            "Set eviction policy to allkeys-lru",
            "Purge expired keyspace batch"
        ],
        "preventive_action": "Enforced rolling TTL on RedisSessionManager with 24h expiration",
        "severity": "HIGH",
        "tags": ["redis", "oom", "cache", "memory_leak"]
    },
    {
        "id": "INC-2026-059",
        "service": "payment-worker",
        "symptom": "Docker container exited with Code 137 (OOMKilled by Linux kernel)",
        "root_cause": "Unbounded memory buffer accumulating unacknowledged payment queue payloads in Python process.",
        "remediation_steps": [
            "Inspect docker inspect <container> for OOMKilled flag",
            "Clear stale queue backlog in Redis / SQS",
            "Restart container with revised memory limit"
        ],
        "preventive_action": "Added streaming backpressure to consumer loop",
        "severity": "CRITICAL",
        "tags": ["docker", "oomkilled", "code137", "memory_leak"]
    }
]


class PostMortemStore:
    """Manages SRE knowledge base and incident history."""

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path or os.path.join(settings.DATA_DIR, "postmortems.json")
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        self._load_or_seed()

    def _load_or_seed(self):
        if not os.path.exists(self.storage_path):
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_POSTMORTEMS, f, indent=2)
            self.records = [IncidentRecord(**rec) for rec in DEFAULT_POSTMORTEMS]
            logger.info(f"Seeded {len(self.records)} initial post-mortems to {self.storage_path}")
        else:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.records = [IncidentRecord(**rec) for rec in data]
            logger.info(f"Loaded {len(self.records)} post-mortems from {self.storage_path}")

    def search(self, query: str, top_k: int = 3) -> List[IncidentRecord]:
        """Performs multi-field keyword & tag matching across past post-mortems."""
        query_words = set(query.lower().replace("-", " ").replace("_", " ").split())
        scored: List[tuple[int, IncidentRecord]] = []

        for record in self.records:
            score = 0
            haystack = f"{record.service} {record.symptom} {record.root_cause} {' '.join(record.tags)}".lower()
            for word in query_words:
                if len(word) > 2 and word in haystack:
                    score += 2
                for tag in record.tags:
                    if word == tag.lower():
                        score += 3
            if score > 0:
                scored.append((score, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:top_k]]

    def add_postmortem(self, incident: IncidentRecord):
        """Append a newly resolved incident to persistent storage."""
        self.records.append(incident)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in self.records], f, indent=2)
        logger.info(f"Added post-mortem for incident: {incident.id}")


# Singleton instance
postmortem_store = PostMortemStore()
