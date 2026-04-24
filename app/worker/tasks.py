import asyncio
import json
import os
import re

from app.config import settings
from app.scraper import amazon, assembler, goodreads, google_books, google_search, linkedin, website
from app.utils.job_store import update_status
from app.worker.celery_app import celery_app


async def _run_parallel(*func_calls):
    return await asyncio.gather(*(asyncio.to_thread(func, *args) for func, args in func_calls))


def _safe_author_filename(author_name: str, job_id: str) -> str:
    """
    Build a filesystem-safe filename:
    - sanitize non-alnum chars to underscore
    - collapse repeats
    - append short job suffix to avoid collisions
    """
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", (author_name or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = "author"
    return f"{cleaned}_{job_id[:8]}_research.json"


@celery_app.task(name="app.worker.tasks.run_emm_pipeline")
def run_emm_pipeline(job_id: str, inputs: dict):
    try:
        update_status(job_id, "scraping_linkedin")
        profile_data = linkedin.get_full_profile(inputs["linkedin_username"].strip())
        urn = profile_data.get("urn", "")
        posts_data, articles_data = asyncio.run(
            _run_parallel(
                (linkedin.get_posts, (urn,)),
                (linkedin.get_articles, (urn,)),
            )
        )

        update_status(job_id, "scraping_web")
        amazon_data, goodreads_data, website_data, press_data, podcast_data, books_data = asyncio.run(
            _run_parallel(
                (amazon.scrape, (inputs["amazon_url"],)),
                (goodreads.scrape, (inputs["book_title"], inputs["author_name"])),
                (website.scrape, (inputs["website_url"],)),
                (google_search.find_press, (inputs["author_name"],)),
                (google_search.find_podcasts, (inputs["author_name"],)),
                (google_books.find_all_books, (inputs["author_name"],)),
            )
        )

        update_status(job_id, "reviewing")
        research = assembler.build_research_export(
            inputs=inputs,
            profile=profile_data,
            posts=posts_data,
            articles=articles_data,
            amazon=amazon_data,
            goodreads=goodreads_data,
            website=website_data,
            press=press_data,
            podcasts=podcast_data,
            books=books_data,
        )

        update_status(job_id, "exporting")
        os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
        out_filename = _safe_author_filename(inputs.get("author_name", ""), job_id)
        out_path = os.path.join(settings.OUTPUT_DIR, out_filename)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(research, f, indent=2, ensure_ascii=False, default=str)

        warnings = []
        if isinstance(website_data, dict) and website_data.get("fetch_error"):
            warnings.append("Website fetching couldn't be completed")
        if isinstance(goodreads_data, dict) and goodreads_data.get("fetch_error"):
            warnings.append("Goodreads fetching couldn't be completed")

        warning_message = ""
        if warnings:
            warning_message = "; ".join(warnings) + ". Other sources were still collected."

        update_status(job_id, "complete", result_path=out_path, message=warning_message)
    except Exception as exc:
        update_status(job_id, "failed", error=str(exc))
        raise
