import asyncio
import json
import os

from app.config import settings
from app.scraper import amazon, assembler, goodreads, google_books, google_search, linkedin, website
from app.utils.job_store import update_status
from app.worker.celery_app import celery_app


async def _run_parallel(*func_calls):
    return await asyncio.gather(*(asyncio.to_thread(func, *args) for func, args in func_calls))


def _safe_google_call(func, *args):
    try:
        return func(*args), ""
    except Exception as exc:
        return [], f"{func.__name__} failed: {exc}"


@celery_app.task(name="app.worker.tasks.run_emm_pipeline")
def run_emm_pipeline(job_id: str, inputs: dict):
    try:
        warnings = []
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
        amazon_data, goodreads_data, website_data = asyncio.run(
            _run_parallel(
                (amazon.scrape, (inputs["amazon_url"],)),
                (goodreads.scrape, (inputs["book_title"], inputs["author_name"])),
                (website.scrape, (inputs["website_url"],)),
            )
        )
        press_data, warning = _safe_google_call(google_search.find_press, inputs["author_name"])
        if warning:
            warnings.append(warning)
        podcast_data, warning = _safe_google_call(google_search.find_podcasts, inputs["author_name"])
        if warning:
            warnings.append(warning)
        books_data, warning = _safe_google_call(google_books.find_all_books, inputs["author_name"])
        if warning:
            warnings.append(warning)

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
            warnings=warnings,
        )

        update_status(job_id, "exporting")
        os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
        out_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_research.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(research, f, indent=2, ensure_ascii=False, default=str)

        update_status(job_id, "complete", result_path=out_path)
    except Exception as exc:
        update_status(job_id, "failed", error=str(exc))
        raise
