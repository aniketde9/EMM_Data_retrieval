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


def _posts_from_payload(data) -> list:
    """LinkdAPI returns { posts: [...], cursor: ... } per https://linkdapi.com/docs (posts/all)."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        posts = data.get("posts")
        if isinstance(posts, list):
            return [x for x in posts if isinstance(x, dict)]
    return []


def _articles_from_payload(data) -> list:
    """LinkdAPI returns { articles: [...], paging: ... } per https://linkdapi.com/docs (articles/all)."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        articles = data.get("articles")
        if isinstance(articles, list):
            return [x for x in articles if isinstance(x, dict)]
    return []


def _normalize_post(p: dict) -> dict:
    eng = p.get("engagements") if isinstance(p.get("engagements"), dict) else {}
    return {
        **p,
        "date": p.get("postedAt") or p.get("date") or "",
        "numLikes": eng.get("totalReactions", p.get("numLikes", 0)) or 0,
        "numComments": eng.get("commentsCount", p.get("numComments", 0)) or 0,
    }


def _normalize_article(a: dict) -> dict:
    cover = a.get("coverImage") if isinstance(a.get("coverImage"), dict) else {}
    return {
        **a,
        "title": a.get("title") or "",
        "publishedAt": a.get("publishedAt") or a.get("postedAt") or "",
        "text": a.get("description") or a.get("text") or "",
        "url": a.get("navigationUrl") or a.get("url") or "",
        "coverImageUrl": cover.get("url") or "",
    }


def get_posts(urn: str) -> list:
    resp = requests.get(
        f"{BASE}/api/v1/posts/all",
        params={"urn": urn},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    raw = resp.json().get("data", {})
    posts = _posts_from_payload(raw)
    normalized = [_normalize_post(p) for p in posts]
    return sorted(normalized, key=lambda p: str(p.get("date", "")), reverse=True)[:10]


def get_articles(urn: str) -> list:
    resp = requests.get(
        f"{BASE}/api/v1/articles/all",
        params={"urn": urn},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    raw = resp.json().get("data", {})
    articles = _articles_from_payload(raw)
    normalized = [_normalize_article(a) for a in articles]
    return sorted(normalized, key=lambda a: str(a.get("publishedAt", "")), reverse=True)[:10]
