import json
import os
import subprocess

from app.config import settings


def build(content: dict, job_id: str) -> str:
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    json_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}.json")
    docx_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}.docx")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(content, f)

    result = subprocess.run(
        ["node", "app/document/generate.js", json_path, docx_path],
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode != 0:
        raise RuntimeError(f"DOCX generation failed: {result.stderr}")
    return docx_path
