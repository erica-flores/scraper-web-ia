"""In-memory job store for scraping jobs."""

from __future__ import annotations
import uuid
from typing import Any

# { job_id: { status, progress, results } }
_jobs: dict[str, dict[str, Any]] = {}


def create_job() -> str:
    """Create a new job and return its ID."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "pending",
        "progress": [],
        "results": [],     # list of hotel dicts
    }
    return job_id


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def append_log(job_id: str, message: str) -> None:
    if job_id in _jobs:
        _jobs[job_id]["progress"].append(message)


def append_result(job_id: str, hotel_dict: dict) -> None:
    if job_id in _jobs:
        _jobs[job_id]["results"].append(hotel_dict)


def set_status(job_id: str, status: str) -> None:
    if job_id in _jobs:
        _jobs[job_id]["status"] = status


def all_jobs_results() -> list[dict]:
    """Return all hotel results across all completed jobs (for the chat context)."""
    results = []
    for job in _jobs.values():
        results.extend(job.get("results", []))
    return results
