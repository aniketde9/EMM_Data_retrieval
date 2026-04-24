from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import time


def _get_with_retries(url: str, headers: dict, timeout: int, retries: int = 3, delay_seconds: int = 3):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(delay_seconds)
    raise last_error


def scrape(website_url: str) -> dict:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}
    data = {
        "url": website_url,
        "about_text": "",
        "blog_posts": [],
        "has_speaking_page": False,
        "has_podcast": False,
        "has_blog": False,
        "has_email_capture": False,
        "fetch_error": "",
    }

    try:
        resp = _get_with_retries(website_url, headers=headers, timeout=15, retries=3, delay_seconds=3)
    except Exception as exc:
        data["fetch_error"] = f"Website fetch failed after retries: {exc}"
        return data

    soup = BeautifulSoup(resp.text, "html.parser")
    data["homepage_text"] = soup.get_text(separator=" ", strip=True)[:3000]

    domain = urlparse(website_url).netloc
    full_links = []
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        full_url = urljoin(website_url, href)
        if urlparse(full_url).netloc == domain:
            full_links.append(full_url)

    data["has_speaking_page"] = any("speak" in l.lower() for l in full_links)
    data["has_podcast"] = any(("podcast" in l.lower() or "episode" in l.lower()) for l in full_links)
    data["has_blog"] = any(("blog" in l.lower() or "article" in l.lower() or "post" in l.lower()) for l in full_links)
    data["has_email_capture"] = bool(soup.find("form") or soup.find("input", {"type": "email"}))

    about_url = next((l for l in full_links if "about" in l.lower()), "")
    if about_url:
        try:
            about_resp = _get_with_retries(about_url, headers=headers, timeout=10, retries=2, delay_seconds=2)
            about_soup = BeautifulSoup(about_resp.text, "html.parser")
            data["about_text"] = about_soup.get_text(separator=" ", strip=True)[:3000]
        except Exception:
            data["about_text"] = ""

    blog_url = next((l for l in full_links if "blog" in l.lower()), "")
    if blog_url:
        try:
            blog_resp = _get_with_retries(blog_url, headers=headers, timeout=10, retries=2, delay_seconds=2)
            blog_soup = BeautifulSoup(blog_resp.text, "html.parser")
            post_links = [urljoin(blog_url, a.get("href", "")) for a in blog_soup.select("a[href]")][:20]
            unique = []
            for link in post_links:
                if link not in unique and urlparse(link).netloc == domain:
                    unique.append(link)
            for post_url in unique[:5]:
                try:
                    post_resp = _get_with_retries(post_url, headers=headers, timeout=10, retries=2, delay_seconds=1)
                    post_soup = BeautifulSoup(post_resp.text, "html.parser")
                    for tag in post_soup(["script", "style", "nav", "footer", "header"]):
                        tag.decompose()
                    data["blog_posts"].append({"url": post_url, "text": post_soup.get_text(separator=" ", strip=True)[:1500]})
                except Exception:
                    continue
        except Exception:
            pass

    return data
