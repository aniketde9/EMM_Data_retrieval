import random
import time

import requests
from bs4 import BeautifulSoup


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
    time.sleep(random.uniform(2, 4))
    return _google_scrape(query, num)


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
