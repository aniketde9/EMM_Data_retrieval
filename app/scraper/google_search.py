import random
import time

import requests
from bs4 import BeautifulSoup

from app.config import settings


def find_linkedin_username(author_name: str) -> str:
    results = _search(f'"{author_name}" site:linkedin.com/in')
    for r in results:
        url = r.get("url", "")
        if "linkedin.com/in/" in url:
            return url.split("linkedin.com/in/")[1].split("/")[0].split("?")[0]
    raise ValueError(f"Could not find LinkedIn username for {author_name}")


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
    if settings.SERPAPI_KEY:
        return _serpapi_search(query, num)
    time.sleep(random.uniform(2, 4))
    return _google_scrape(query, num)


def _serpapi_search(query: str, num: int) -> list:
    resp = requests.get(
        "https://serpapi.com/search",
        params={"q": query, "num": num, "api_key": settings.SERPAPI_KEY},
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json().get("organic_results", [])
    return [{"url": r.get("link"), "title": r.get("title"), "source": r.get("source", "")} for r in results]


def _google_scrape(query: str, num: int) -> list:
    url = f"https://www.google.com/search?q={requests.utils.quote(query)}&num={num}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
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
