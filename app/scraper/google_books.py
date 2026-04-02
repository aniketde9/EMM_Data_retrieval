import requests
from bs4 import BeautifulSoup


def find_all_books(author_name: str) -> list:
    url = f"https://www.google.com/search?q={requests.utils.quote(author_name)}+books&tbm=bks"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    books = []
    for result in soup.select(".Yr5TG")[:10]:
        title_tag = result.select_one("h3")
        meta = result.select_one(".fl")
        date_tag = result.select_one(".f")
        books.append(
            {
                "title": title_tag.text.strip() if title_tag else "",
                "meta": meta.text.strip() if meta else "",
                "date_info": date_tag.text.strip() if date_tag else "",
            }
        )
    return books
