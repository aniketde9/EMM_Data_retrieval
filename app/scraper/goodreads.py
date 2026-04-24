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


def scrape(book_title: str, author_name: str) -> dict:
    query = requests.utils.quote(f"{book_title} {author_name}")
    search_url = f"https://www.goodreads.com/search?q={query}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}
    data = {
        "url": "",
        "avg_rating": "",
        "review_count": "",
        "description": "",
        "shelves": [],
        "top_reviews": [],
        "fetch_error": "",
    }

    try:
        resp = _get_with_retries(search_url, headers=headers, timeout=15, retries=3, delay_seconds=3)
    except Exception as exc:
        data["fetch_error"] = f"Goodreads search fetch failed after retries: {exc}"
        return data

    soup = BeautifulSoup(resp.text, "html.parser")

    first_result = soup.select_one("a.bookTitle")
    if not first_result:
        data["fetch_error"] = "Book not found on Goodreads"
        return data
    book_url = "https://www.goodreads.com" + first_result["href"]
    data["url"] = book_url

    try:
        book_resp = _get_with_retries(book_url, headers=headers, timeout=15, retries=3, delay_seconds=3)
    except Exception as exc:
        data["fetch_error"] = f"Goodreads book page fetch failed after retries: {exc}"
        return data

    book_soup = BeautifulSoup(book_resp.text, "html.parser")

    rating_tag = book_soup.select_one("[itemprop='ratingValue']")
    data["avg_rating"] = rating_tag.text.strip() if rating_tag else ""
    review_count_tag = book_soup.select_one("[itemprop='reviewCount']")
    data["review_count"] = review_count_tag.text.strip() if review_count_tag else ""
    desc_tag = book_soup.select_one("#description span:last-child") or book_soup.select_one(".readable.stacked")
    data["description"] = desc_tag.text.strip()[:2000] if desc_tag else ""
    data["shelves"] = [s.text.strip() for s in book_soup.select(".elementList .left a")[:15]]

    reviews = []
    for review in book_soup.select(".review")[:10]:
        body = review.select_one(".reviewText span:last-child")
        if body:
            reviews.append(body.text.strip()[:600])
    data["top_reviews"] = reviews
    return data
