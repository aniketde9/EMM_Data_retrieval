import requests

from app.config import settings


BASE = settings.LINKDAPI_BASE_URL
HEADERS = {"X-linkdapi-apikey": settings.LINKDAPI_API_KEY}


def get_full_profile(username: str) -> dict:
    resp = requests.get(
        f"{BASE}/api/v1/profile/full",
        params={"username": username},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("data", {})


def get_posts(urn: str) -> list:
    resp = requests.get(
        f"{BASE}/api/v1/posts/all",
        params={"urn": urn},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    posts = resp.json().get("data", {}).get("posts", [])
    return sorted(posts, key=lambda p: p.get("date", ""), reverse=True)[:10]


def get_articles(urn: str) -> list:
    resp = requests.get(
        f"{BASE}/api/v1/articles/all",
        params={"urn": urn},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    articles = resp.json().get("data", [])
    return sorted(articles, key=lambda a: a.get("publishedAt", ""), reverse=True)[:10]
