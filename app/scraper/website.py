from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


def scrape(website_url: str) -> dict:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}
    data = {"url": website_url, "about_text": "", "blog_posts": []}

    resp = requests.get(website_url, headers=headers, timeout=15)
    resp.raise_for_status()
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
            about_resp = requests.get(about_url, headers=headers, timeout=10)
            about_resp.raise_for_status()
            about_soup = BeautifulSoup(about_resp.text, "html.parser")
            data["about_text"] = about_soup.get_text(separator=" ", strip=True)[:3000]
        except Exception:
            data["about_text"] = ""

    blog_url = next((l for l in full_links if "blog" in l.lower()), "")
    if blog_url:
        try:
            blog_resp = requests.get(blog_url, headers=headers, timeout=10)
            blog_resp.raise_for_status()
            blog_soup = BeautifulSoup(blog_resp.text, "html.parser")
            post_links = [urljoin(blog_url, a.get("href", "")) for a in blog_soup.select("a[href]")][:20]
            unique = []
            for link in post_links:
                if link not in unique and urlparse(link).netloc == domain:
                    unique.append(link)
            for post_url in unique[:5]:
                try:
                    post_resp = requests.get(post_url, headers=headers, timeout=10)
                    post_resp.raise_for_status()
                    post_soup = BeautifulSoup(post_resp.text, "html.parser")
                    for tag in post_soup(["script", "style", "nav", "footer", "header"]):
                        tag.decompose()
                    data["blog_posts"].append({"url": post_url, "text": post_soup.get_text(separator=" ", strip=True)[:1500]})
                except Exception:
                    continue
        except Exception:
            pass

    return data
