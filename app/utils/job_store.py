import json
import time
from typing import Any

import redis

from app.config import settings


r = redis.from_url(settings.REDIS_URL, decode_responses=True)


def create_job(job_id: str, inputs: dict[str, Any]) -> None:
    now = time.time()
    data = {
        "job_id": job_id,
        "status": "queued",
        "message": "",
        "pdf_path": "",
        "error": "",
        "created_at": now,
        "updated_at": now,
        "inputs": inputs,
    }
    r.set(f"job:{job_id}", json.dumps(data))


def update_status(
    job_id: str,
    status: str,
    message: str = "",
    pdf_path: str = "",
    error: str = "",
) -> None:
    raw = r.get(f"job:{job_id}")
    if not raw:
        return
    data = json.loads(raw)
    data["status"] = status
    data["message"] = message
    if pdf_path:
        data["pdf_path"] = pdf_path
    if error:
        data["error"] = error
    data["updated_at"] = time.time()
    r.set(f"job:{job_id}", json.dumps(data))


def get_job(job_id: str) -> dict[str, Any] | None:
    raw = r.get(f"job:{job_id}")
    return json.loads(raw) if raw else None
