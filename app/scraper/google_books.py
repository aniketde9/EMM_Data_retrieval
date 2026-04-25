import random
import time

import requests
from bs4 import BeautifulSoup


def _is_blocked_response(text: str) -> bool:
    lowered = (text or "").lower()
    return "google.com/sorry" in lowered or "our systems have detected unusual traffic" in lowered


def _google_get_with_retry(url: str, timeout: int = 15, max_attempts: int = 3) -> requests.Response:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    backoff_seconds = 2.0

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 429:
                raise requests.HTTPError("429 Too Many Requests", response=resp)
            resp.raise_for_status()
            if _is_blocked_response(resp.text):
                raise requests.HTTPError("Google anti-bot block page", response=resp)
            return resp
        except requests.RequestException:
            if attempt == max_attempts:
                raise
            jitter = random.uniform(0.3, 1.1)
            time.sleep(backoff_seconds + jitter)
            backoff_seconds *= 2

    raise RuntimeError("Google request retry loop exited unexpectedly")


def find_all_books(author_name: str) -> list:
    url = f"https://www.google.com/search?q={requests.utils.quote(author_name)}+books&tbm=bks&num=5"
    resp = _google_get_with_retry(url, timeout=15, max_attempts=3)
    soup = BeautifulSoup(resp.text, "html.parser")

    books = []
    for result in soup.select(".Yr5TG")[:10]:
        title_tag = result.select_one("h3")
        meta = result.select_one(".fl")
        date_tag = result.select_one(".f")
        books.append(
            {
                "title": title_tag.text.strip() if title_tag else "",
                "meta": meta.text.strip() if meta else "",
                "date_info": date_tag.text.strip() if date_tag else "",
            }
        )
    return books
