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


def find_press(author_name: str) -> list:
    results = _search(f'"{author_name}" interview OR profile OR featured', num=5)
    rows = []
    for r in results:
        text = _fetch_page_text(r.get("url", ""))
        if text:
            rows.append(
                {
                    "source": r.get("source", ""),
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "excerpt": text[:1500],
                }
            )
    return rows


def find_podcasts(author_name: str) -> list:
    results = _search(f'"{author_name}" podcast interview', num=5)
    rows = []
    for r in results:
        text = _fetch_page_text(r.get("url", ""))
        if text:
            rows.append(
                {
                    "show": r.get("source", ""),
                    "episode_title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "notes": text[:1500],
                }
            )
    return rows


def _search(query: str, num: int = 5) -> list:
    time.sleep(random.uniform(2.5, 4.5))
    return _google_scrape(query, num)


def _google_scrape(query: str, num: int) -> list:
    url = f"https://www.google.com/search?q={requests.utils.quote(query)}&num={num}"
    resp = _google_get_with_retry(url, timeout=15, max_attempts=3)
    soup = BeautifulSoup(resp.text, "html.parser")
    output = []
    for item in soup.select("div.g")[:num]:
        link = item.select_one("a")
        title = item.select_one("h3")
        if link and title and link.get("href"):
            output.append({"url": link["href"], "title": title.text, "source": ""})
    return output


def _fetch_page_text(url: str) -> str:
    if not url:
        return ""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)[:3000]
    except Exception:
        return ""
