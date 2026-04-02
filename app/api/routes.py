import os
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.config import settings
from app.utils.job_store import create_job, get_job
from app.worker.tasks import run_emm_pipeline


router = APIRouter()


class SubmitRequest(BaseModel):
    author_name: str
    book_title: str
    website_url: HttpUrl
    linkedin_username: str = Field(min_length=1)
    amazon_url: HttpUrl

    @field_validator("linkedin_username")
    @classmethod
    def strip_linkedin_username(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("linkedin_username is required")
        return stripped


@router.post("/submit")
def submit(payload: SubmitRequest) -> dict:
    job_id = str(uuid.uuid4())
    inputs = payload.model_dump()
    inputs["website_url"] = str(inputs["website_url"])
    inputs["amazon_url"] = str(inputs["amazon_url"])
    create_job(job_id, inputs)
    run_emm_pipeline.delay(job_id=job_id, inputs=inputs)
    return {"job_id": job_id, "status": "queued"}


@router.get("/status/{job_id}")
def status(job_id: str) -> dict:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/download/{job_id}")
def download(job_id: str) -> FileResponse:
    job = get_job(job_id)
    if not job or job.get("status") != "complete":
        raise HTTPException(status_code=404, detail="File not available")
    path = job.get("result_path") or job.get("pdf_path")
    if not path:
        path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_research.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Output file not found")
    if path.lower().endswith(".json"):
        return FileResponse(
            path,
            media_type="application/json",
            filename=os.path.basename(path),
        )
    return FileResponse(path, media_type="application/pdf", filename=os.path.basename(path))
