import requests
from bs4 import BeautifulSoup


def scrape(book_title: str, author_name: str) -> dict:
    query = requests.utils.quote(f"{book_title} {author_name}")
    search_url = f"https://www.goodreads.com/search?q={query}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}
    resp = requests.get(search_url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    first_result = soup.select_one("a.bookTitle")
    if not first_result:
        return {"error": "Book not found on Goodreads"}
    book_url = "https://www.goodreads.com" + first_result["href"]

    book_resp = requests.get(book_url, headers=headers, timeout=15)
    book_resp.raise_for_status()
    book_soup = BeautifulSoup(book_resp.text, "html.parser")

    data = {"url": book_url}
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
