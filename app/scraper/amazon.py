import requests
from bs4 import BeautifulSoup


def scrape(amazon_url: str) -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    resp = requests.get(amazon_url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    data = {}
    title_tag = soup.select_one("#productTitle")
    data["title"] = title_tag.text.strip() if title_tag else ""
    subtitle_tag = soup.select_one("#productSubtitle")
    data["subtitle"] = subtitle_tag.text.strip() if subtitle_tag else ""
    author_tag = soup.select_one(".author .a-link-normal")
    data["author"] = author_tag.text.strip() if author_tag else ""

    rating_tag = soup.select_one("#acrPopover")
    data["avg_rating"] = rating_tag["title"].split(" ")[0] if rating_tag and rating_tag.get("title") else ""
    review_count_tag = soup.select_one("#acrCustomerReviewText")
    data["review_count"] = review_count_tag.text.strip() if review_count_tag else ""

    rank_section = soup.find("li", {"id": "SalesRank"}) or soup.find(string=lambda t: "Best Sellers Rank" in str(t))
    data["bsr"] = str(rank_section)[:300] if rank_section else ""

    detail_bullets = soup.select("#detailBullets_feature_div li")
    for item in detail_bullets:
        text = item.text.strip()
        if "Publisher" in text:
            data["publisher"] = text.split(":")[-1].strip()
        if "Publication date" in text or "Published" in text:
            data["publication_date"] = text.split(":")[-1].strip()

    desc_tag = soup.select_one("#bookDescription_feature_div")
    data["description"] = desc_tag.text.strip()[:2000] if desc_tag else ""
    editorial = soup.select_one("#editorialReviews_feature_div")
    data["editorial_reviews"] = editorial.text.strip()[:2000] if editorial else ""

    reviews = []
    for review in soup.select("[data-hook='review']")[:10]:
        body = review.select_one("[data-hook='review-body']")
        rating = review.select_one("[data-hook='review-star-rating']")
        if body:
            reviews.append({"text": body.text.strip()[:500], "rating": rating.text.strip() if rating else ""})
    data["top_reviews"] = reviews
    return data
