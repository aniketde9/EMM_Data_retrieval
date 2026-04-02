# EMM Pipeline — Full Architecture Spec
**For Cursor / Developer Handoff**
**Company: Opika | Product: Extra Mile Method Automation**

---

## Overview

This system takes 5 human inputs about a book author, autonomously scrapes all public data about them, runs one Claude API intelligence call, assembles a fully branded Opika EMM document, and outputs a PDF. Zero manual steps between input submission and finished PDF.

**Stack:** Python (FastAPI + Celery + Redis) · Node.js (docx generation) · BeautifulSoup · LinkdAPI · Anthropic Claude API · LibreOffice (PDF conversion)

---

## Project Structure

```
emm-pipeline/
│
├── .env                          # All API keys and config
├── .env.example                  # Template (commit this, not .env)
├── requirements.txt              # Python dependencies
├── package.json                  # Node.js dependencies (docx generation)
│
├── app/
│   ├── main.py                   # FastAPI app entry point
│   ├── config.py                 # Loads .env, exposes settings
│   │
│   ├── api/
│   │   └── routes.py             # POST /submit, GET /status/{job_id}, GET /download/{job_id}
│   │
│   ├── worker/
│   │   ├── celery_app.py         # Celery instance and config
│   │   └── tasks.py              # Main pipeline task (orchestrates all layers)
│   │
│   ├── scraper/
│   │   ├── linkedin.py           # LinkdAPI calls (full profile, posts, articles)
│   │   ├── amazon.py             # Fetch + parse Amazon product page
│   │   ├── goodreads.py          # Fetch + parse Goodreads book page
│   │   ├── website.py            # Fetch + parse author website
│   │   ├── google_search.py      # Google search wrapper (username lookup, press, podcasts)
│   │   ├── google_books.py       # Verify all titles + publication dates
│   │   └── assembler.py          # Combines all scraped data into structured dossier dict
│   │
│   ├── intelligence/
│   │   └── claude_call.py        # Single Claude Sonnet API call — diagnosis + bespoke sections
│   │
│   ├── emm/
│   │   ├── selector.py           # Reads CLUSTER from Claude output, selects correct body
│   │   ├── merger.py             # Merges Claude output + scraped data into body template
│   │   └── bodies/
│   │       ├── discovery.json    # Pre-built EMM body: Discovery cluster
│   │       ├── conversion.json   # Pre-built EMM body: Conversion cluster
│   │       └── capacity.json     # Pre-built EMM body: Capacity cluster
│   │
│   ├── document/
│   │   ├── generate.js           # Node.js docx generator using docx-js (Opika branded)
│   │   ├── logo_processor.py     # Downloads Opika logo, strips black background, saves PNG
│   │   └── pdf_converter.py      # LibreOffice headless: .docx → .pdf
│   │
│   └── utils/
│       ├── job_store.py          # Redis-backed job status tracker
│       └── logger.py             # Structured logging
│
├── static/
│   └── index.html                # Input form UI (plain HTML, no framework needed)
│
├── outputs/                      # Generated PDFs land here (gitignored)
│
└── emm_bodies/                   # Pre-built EMM body JSON files (also in app/emm/bodies/)
```

---

## .env File

```env
# ─────────────────────────────────────────
# ANTHROPIC
# ─────────────────────────────────────────
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Model to use for intelligence call (do not change unless intentional)
CLAUDE_MODEL=claude-sonnet-4-6

# ─────────────────────────────────────────
# LINKDAPI
# ─────────────────────────────────────────
LINKDAPI_API_KEY=your_linkdapi_api_key_here
LINKDAPI_BASE_URL=https://linkdapi.com

# ─────────────────────────────────────────
# REDIS (job queue broker)
# ─────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0

# ─────────────────────────────────────────
# OPIKA BRANDING
# ─────────────────────────────────────────
OPIKA_LOGO_URL=https://drive.google.com/uc?export=download&id=1c7yetV5g43PlFp59QgTy5IGUbqEfvEDt

# ─────────────────────────────────────────
# OUTPUT
# ─────────────────────────────────────────
OUTPUT_DIR=./outputs

# ─────────────────────────────────────────
# APP
# ─────────────────────────────────────────
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=false
```

---

## .env.example

```env
ANTHROPIC_API_KEY=
CLAUDE_MODEL=claude-sonnet-4-6
LINKDAPI_API_KEY=
LINKDAPI_BASE_URL=https://linkdapi.com
REDIS_URL=redis://localhost:6379/0
OPIKA_LOGO_URL=
OUTPUT_DIR=./outputs
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=false
```

---

## Layer 0 — Input Form (static/index.html)

Plain HTML form. No framework. Submits to `POST /api/submit`.

**Fields:**
```
Author Name         (text, required)
Book Title          (text, required)
Author Website URL  (url, required)
LinkedIn Username   (text, required)
Amazon Book URL     (url, required)
```

On submit: POST to `/api/submit` → receives `{ job_id, status: "queued" }` → polls `GET /api/status/{job_id}` every 5 seconds → shows live status updates → when complete, shows download button linked to `GET /api/download/{job_id}`.

**Status messages to display:**
- `queued` → "In queue..."
- `scraping_linkedin` → "Pulling LinkedIn data..."
- `scraping_web` → "Researching author across the web..."
- `reviewing` → "Building research dossier..."
- `generating` → "Running intelligence analysis..."
- `assembling` → "Assembling EMM document..."
- `exporting` → "Generating PDF..."
- `complete` → "Done. Download ready."
- `failed` → "Something went wrong. [error message]"

---

## Layer 1 — API Routes (app/api/routes.py)

```python
POST /api/submit
  Body: { author_name, book_title, website_url, linkedin_username, amazon_url }
  Action: validates inputs, creates job in Redis, enqueues Celery task
  Returns: { job_id: str, status: "queued" }

GET /api/status/{job_id}
  Returns: { job_id, status, message, created_at, updated_at }

GET /api/download/{job_id}
  Returns: PDF file as attachment if status == "complete"
  404 if not found or not complete
```

---

## Layer 2 — Job Orchestrator (app/worker/tasks.py)

This is the main Celery task. It runs every step in order, updates job status in Redis at each step, and handles errors gracefully.

```python
@celery_app.task
def run_emm_pipeline(job_id: str, inputs: dict):

    try:
        update_status(job_id, "scraping_linkedin")

        # Step 1: LinkedIn data via LinkdAPI (profile first, then posts + articles parallel)
        profile_data = scraper.linkedin.get_full_profile(inputs["linkedin_username"])
        urn = profile_data["urn"]

        posts_data, articles_data = asyncio.gather(
            scraper.linkedin.get_posts(urn),
            scraper.linkedin.get_articles(urn)
        )

        update_status(job_id, "scraping_web")

        # Step 2: Web scraping (all parallel)
        amazon_data, goodreads_data, website_data, press_data, podcast_data, books_data = asyncio.gather(
            scraper.amazon.scrape(inputs["amazon_url"]),
            scraper.goodreads.scrape(inputs["book_title"], inputs["author_name"]),
            scraper.website.scrape(inputs["website_url"]),
            scraper.google_search.find_press(inputs["author_name"]),
            scraper.google_search.find_podcasts(inputs["author_name"]),
            scraper.google_books.find_all_books(inputs["author_name"])
        )

        update_status(job_id, "reviewing")

        # Step 3: Assemble structured dossier
        dossier = scraper.assembler.build(
            inputs=inputs,
            profile=profile_data,
            posts=posts_data,
            articles=articles_data,
            amazon=amazon_data,
            goodreads=goodreads_data,
            website=website_data,
            press=press_data,
            podcasts=podcast_data,
            books=books_data
        )

        update_status(job_id, "generating")

        # Step 4: Single Claude intelligence call
        claude_output = intelligence.claude_call.run(dossier)

        update_status(job_id, "assembling")

        # Step 5: Select EMM body based on cluster diagnosis
        body = emm.selector.select(claude_output["CLUSTER"])

        # Step 6: Merge Claude output + dossier into body
        merged_content = emm.merger.merge(body, claude_output, dossier)

        update_status(job_id, "exporting")

        # Step 7: Generate branded .docx
        docx_path = document.generate.build(merged_content, job_id)

        # Step 8: Convert to PDF
        pdf_path = document.pdf_converter.convert(docx_path, job_id)

        # Step 9: Done
        update_status(job_id, "complete", pdf_path=pdf_path)

    except Exception as e:
        update_status(job_id, "failed", error=str(e))
        raise
```

---

## Layer 3 — Scrapers

### app/scraper/linkedin.py

Uses LinkdAPI. Three calls total per author.

```python
import requests
from app.config import settings

BASE = settings.LINKDAPI_BASE_URL
HEADERS = {"X-linkdapi-apikey": settings.LINKDAPI_API_KEY}

def get_full_profile(username: str) -> dict:
    """
    Endpoint: GET /api/v1/profile/full?username={username}
    Cost: 1 credit
    Returns: full profile including URN, name, headline, current role,
             company, about, experience, education, follower count, connections
    """
    resp = requests.get(
        f"{BASE}/api/v1/profile/full",
        params={"username": username},
        headers=HEADERS,
        timeout=15
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    return data  # includes data["urn"] for subsequent calls


def get_posts(urn: str) -> list:
    """
    Endpoint: GET /api/v1/posts/all?urn={urn}
    Cost: 1 credit
    Returns: up to 100 posts. We slice to last 10 by date.
    Each post: text, date, likes, comments, reposts, hashtags
    """
    resp = requests.get(
        f"{BASE}/api/v1/posts/all",
        params={"urn": urn},
        headers=HEADERS,
        timeout=15
    )
    resp.raise_for_status()
    posts = resp.json()["data"]["posts"]
    # Sort by date descending, return last 10
    sorted_posts = sorted(posts, key=lambda p: p.get("date", ""), reverse=True)
    return sorted_posts[:10]


def get_articles(urn: str) -> list:
    """
    Endpoint: GET /api/v1/articles/all?urn={urn}
    Cost: 1 credit
    Returns: all articles. We slice to last 10 by date.
    Each article: title, full text, publish date, reactions
    """
    resp = requests.get(
        f"{BASE}/api/v1/articles/all",
        params={"urn": urn},
        headers=HEADERS,
        timeout=15
    )
    resp.raise_for_status()
    articles = resp.json()["data"]
    sorted_articles = sorted(articles, key=lambda a: a.get("publishedAt", ""), reverse=True)
    return sorted_articles[:10]
```

---

### app/scraper/google_search.py

Handles press coverage and podcast appearances via Google result pages (no SerpAPI). LinkedIn username is always supplied by the client; there is no Google-based LinkedIn lookup.

Uses direct Google HTML scraping with random delays between requests for basic rate limiting.

```python
import time
import random
import requests
from bs4 import BeautifulSoup

def find_press(author_name: str) -> list:
    results = _search(f'"{author_name}" interview OR profile OR featured', num=5)
    ...

def find_podcasts(author_name: str) -> list:
    results = _search(f'"{author_name}" podcast interview', num=5)
    ...

def _search(query: str, num: int = 5) -> list:
    time.sleep(random.uniform(2, 4))
    return _google_scrape(query, num)

def _google_scrape(query: str, num: int) -> list:
    ...
```

---

### app/scraper/amazon.py

```python
import requests
from bs4 import BeautifulSoup

def scrape(amazon_url: str) -> dict:
    """
    Fetches Amazon book page and extracts:
    - title, subtitle, author, publisher
    - publication date
    - Amazon Best Seller Rank (current)
    - categories
    - total review count + average rating
    - top 10 most helpful review texts
    - most recent 5 review texts
    - editorial reviews and endorsement blurbs
    - book description / editorial description

    Note: Does not attempt Look Inside iframe (too protected).
    All other fields are in the main product page HTML.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    resp = requests.get(amazon_url, headers=headers, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")

    data = {}

    # Title
    title_tag = soup.select_one("#productTitle")
    data["title"] = title_tag.text.strip() if title_tag else ""

    # Subtitle
    subtitle_tag = soup.select_one("#productSubtitle")
    data["subtitle"] = subtitle_tag.text.strip() if subtitle_tag else ""

    # Author
    author_tag = soup.select_one(".author .a-link-normal")
    data["author"] = author_tag.text.strip() if author_tag else ""

    # Rating and review count
    rating_tag = soup.select_one("#acrPopover")
    data["avg_rating"] = rating_tag["title"].split(" ")[0] if rating_tag else ""

    review_count_tag = soup.select_one("#acrCustomerReviewText")
    data["review_count"] = review_count_tag.text.strip() if review_count_tag else ""

    # Best Seller Rank
    rank_section = soup.find("li", {"id": "SalesRank"}) or soup.find(string=lambda t: "Best Sellers Rank" in str(t))
    data["bsr"] = str(rank_section)[:300] if rank_section else ""

    # Publisher and publication date
    detail_bullets = soup.select("#detailBullets_feature_div li")
    for item in detail_bullets:
        text = item.text.strip()
        if "Publisher" in text:
            data["publisher"] = text.split(":")[-1].strip()
        if "Publication date" in text or "Published" in text:
            data["publication_date"] = text.split(":")[-1].strip()

    # Book description
    desc_tag = soup.select_one("#bookDescription_feature_div")
    data["description"] = desc_tag.text.strip()[:2000] if desc_tag else ""

    # Editorial reviews and endorsements
    editorial = soup.select_one("#editorialReviews_feature_div")
    data["editorial_reviews"] = editorial.text.strip()[:2000] if editorial else ""

    # Customer reviews — top helpful reviews
    reviews = []
    for review in soup.select("[data-hook='review']")[:10]:
        body = review.select_one("[data-hook='review-body']")
        rating = review.select_one("[data-hook='review-star-rating']")
        if body:
            reviews.append({
                "text": body.text.strip()[:500],
                "rating": rating.text.strip() if rating else ""
            })
    data["top_reviews"] = reviews

    return data
```

---

### app/scraper/goodreads.py

```python
import requests
from bs4 import BeautifulSoup

def scrape(book_title: str, author_name: str) -> dict:
    """
    Searches Goodreads for the book and scrapes:
    - Rating, review count
    - Top 10 review texts (most helpful)
    - Shelf names (how readers categorize this book)
    - Book description
    """
    # Search for book on Goodreads
    search_url = f"https://www.goodreads.com/search?q={requests.utils.quote(book_title + ' ' + author_name)}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}

    resp = requests.get(search_url, headers=headers, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")

    # Get first result book URL
    first_result = soup.select_one("a.bookTitle")
    if not first_result:
        return {"error": "Book not found on Goodreads"}

    book_url = "https://www.goodreads.com" + first_result["href"]
    book_resp = requests.get(book_url, headers=headers, timeout=15)
    book_soup = BeautifulSoup(book_resp.text, "html.parser")

    data = {"url": book_url}

    # Rating
    rating_tag = book_soup.select_one("[itemprop='ratingValue']")
    data["avg_rating"] = rating_tag.text.strip() if rating_tag else ""

    # Review count
    review_count_tag = book_soup.select_one("[itemprop='reviewCount']")
    data["review_count"] = review_count_tag.text.strip() if review_count_tag else ""

    # Description
    desc_tag = book_soup.select_one("#description span:last-child") or book_soup.select_one(".readable.stacked")
    data["description"] = desc_tag.text.strip()[:2000] if desc_tag else ""

    # Shelves (how readers categorize)
    shelves = []
    for shelf in book_soup.select(".elementList .left a")[:15]:
        shelves.append(shelf.text.strip())
    data["shelves"] = shelves

    # Reviews
    reviews = []
    for review in book_soup.select(".review")[:10]:
        body = review.select_one(".reviewText span:last-child")
        if body:
            reviews.append(body.text.strip()[:600])
    data["top_reviews"] = reviews

    return data
```

---

### app/scraper/website.py

```python
import requests
from bs4 import BeautifulSoup

def scrape(website_url: str) -> dict:
    """
    Fetches author website and extracts:
    - About page text
    - Email capture: exists? lead magnet description?
    - Speaking page: exists?
    - Podcast: exists? linked?
    - Blog: exists? how many posts? most recent date?
    - Last 5 blog post texts
    - Any products, courses, workshops beyond the book
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}
    data = {"url": website_url}

    # Fetch homepage
    resp = requests.get(website_url, headers=headers, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    data["homepage_text"] = soup.get_text(separator=" ", strip=True)[:3000]

    # Find internal links
    links = [a["href"] for a in soup.select("a[href]") if a.get("href")]
    full_links = []
    for link in links:
        if link.startswith("/"):
            full_links.append(website_url.rstrip("/") + link)
        elif website_url.split("//")[1].split("/")[0] in link:
            full_links.append(link)

    # Detect key pages
    data["has_speaking_page"] = any("speak" in l.lower() for l in full_links)
    data["has_podcast"] = any("podcast" in l.lower() or "episode" in l.lower() for l in full_links)
    data["has_blog"] = any("blog" in l.lower() or "article" in l.lower() or "post" in l.lower() for l in full_links)
    data["has_email_capture"] = bool(soup.find("form") or soup.find("input", {"type": "email"}))

    # Find and fetch About page
    about_url = next((l for l in full_links if "about" in l.lower()), None)
    if about_url:
        try:
            about_resp = requests.get(about_url, headers=headers, timeout=10)
            about_soup = BeautifulSoup(about_resp.text, "html.parser")
            data["about_text"] = about_soup.get_text(separator=" ", strip=True)[:3000]
        except Exception:
            data["about_text"] = ""

    # Find and fetch blog posts (up to 5)
    blog_url = next((l for l in full_links if "blog" in l.lower()), None)
    data["blog_posts"] = []
    if blog_url:
        try:
            blog_resp = requests.get(blog_url, headers=headers, timeout=10)
            blog_soup = BeautifulSoup(blog_resp.text, "html.parser")
            # Find individual post links on the blog index page
            post_links = [
                a["href"] for a in blog_soup.select("a[href]")
                if a.get("href") and (blog_url in a["href"] or a["href"].startswith("/"))
            ][:5]
            for post_url in post_links[:5]:
                try:
                    full_url = post_url if post_url.startswith("http") else website_url.rstrip("/") + post_url
                    post_resp = requests.get(full_url, headers=headers, timeout=10)
                    post_soup = BeautifulSoup(post_resp.text, "html.parser")
                    for tag in post_soup(["script", "style", "nav", "footer", "header"]):
                        tag.decompose()
                    data["blog_posts"].append({
                        "url": full_url,
                        "text": post_soup.get_text(separator=" ", strip=True)[:1500]
                    })
                except Exception:
                    continue
        except Exception:
            pass

    return data
```

---

### app/scraper/google_books.py

```python
import requests
from bs4 import BeautifulSoup

def find_all_books(author_name: str) -> list:
    """
    Searches Google Books for all books by this author.
    Returns list of: { title, publication_date, publisher, isbn }
    Critical for catching books the team didn't know about (Rain Bennett situation).
    """
    url = f"https://www.google.com/search?q={requests.utils.quote(author_name)}+books&tbm=bks"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}
    resp = requests.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")

    books = []
    for result in soup.select(".Yr5TG")[:10]:
        title_tag = result.select_one("h3")
        meta = result.select_one(".fl")
        date_tag = result.select_one(".f")
        books.append({
            "title": title_tag.text.strip() if title_tag else "",
            "meta": meta.text.strip() if meta else "",
            "date_info": date_tag.text.strip() if date_tag else ""
        })

    return books
```

---

### app/scraper/assembler.py

Combines everything into one clean structured dossier dict.

```python
def build(inputs, profile, posts, articles, amazon, goodreads, website, press, podcasts, books) -> dict:
    """
    Builds the structured dossier passed to Claude.
    Keys are clear field names. Values are clean strings or lists.
    No raw HTML. All text extracted and trimmed.
    """
    return {
        # Author basics
        "author_name": inputs["author_name"],
        "book_title": inputs["book_title"],
        "amazon_url": inputs["amazon_url"],
        "website_url": inputs["website_url"],

        # LinkedIn profile
        "linkedin_headline": profile.get("headline", ""),
        "linkedin_about": profile.get("about", ""),
        "linkedin_current_role": profile.get("position", [{}])[0].get("title", "") if profile.get("position") else "",
        "linkedin_current_company": profile.get("position", [{}])[0].get("companyName", "") if profile.get("position") else "",
        "linkedin_follower_count": profile.get("followersCount", 0),
        "linkedin_connection_count": profile.get("connectionsCount", 0),
        "linkedin_experience": profile.get("experience", []),
        "linkedin_education": profile.get("education", []),

        # LinkedIn content
        "linkedin_posts": posts,          # last 10, each has text + engagement
        "linkedin_articles": articles,     # last 10, each has title + text

        # Book data
        "book_publication_date": amazon.get("publication_date", ""),
        "book_publisher": amazon.get("publisher", ""),
        "book_avg_rating": amazon.get("avg_rating", ""),
        "book_review_count": amazon.get("review_count", ""),
        "book_bsr": amazon.get("bsr", ""),
        "book_description": amazon.get("description", ""),
        "book_editorial_reviews": amazon.get("editorial_reviews", ""),
        "amazon_top_reviews": amazon.get("top_reviews", []),

        # Goodreads
        "goodreads_avg_rating": goodreads.get("avg_rating", ""),
        "goodreads_review_count": goodreads.get("review_count", ""),
        "goodreads_shelves": goodreads.get("shelves", []),
        "goodreads_top_reviews": goodreads.get("top_reviews", []),

        # Website
        "website_about_text": website.get("about_text", ""),
        "website_has_email_capture": website.get("has_email_capture", False),
        "website_has_speaking_page": website.get("has_speaking_page", False),
        "website_has_podcast": website.get("has_podcast", False),
        "website_has_blog": website.get("has_blog", False),
        "website_blog_posts": website.get("blog_posts", []),

        # Press and podcasts
        "press_coverage": press,
        "podcast_appearances": podcasts,

        # All books by this author (Rain Bennett check)
        "all_known_books": books,
    }
```

---

## Layer 4 — Claude Intelligence Call (app/intelligence/claude_call.py)

One API call. Claude Sonnet. Tight structured output.

```python
import anthropic
import json
from app.config import settings

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

PAIN_PATTERNS = """
1. THE SILENCE — Book published 6+ months ago. Amazon rank above 200K. Reviews strong but few. No email capture. No podcast. Author is invisible.
2. THE CREDENTIAL GAP — Impressive affiliations. LinkedIn followers under 5K. Known in rooms, invisible online.
3. THE KEYNOTE EVAPORATION — Active speaker. No email funnel. No post-talk capture system. Every talk ends with applause and nothing else.
4. THE CONTENT BURNOUT — Sporadic LinkedIn posting. High quality when it appears. Tried content help before. Burnout is the bottleneck.
5. THE AGING CLASSIC — Book published 5-15 years ago. Still relevant. Distribution went cold. Author feels they were right too early.
6. THE IDENTITY SPLIT — Current company or venture is different from book topic. Book is an awkward fit with where they are now.
7. THE DISCONNECTED ARCHIPELAGO — Website, podcast, blog, book, workshops all exist. Nothing connects them. No funnel.
8. THE STAGE-TO-SCREEN GAP — Magnetic on stage. Flat or absent online. Digital presence doesn't capture who they are in person.
"""

PROMPT_TEMPLATE = """
You are a senior GTM strategist at Opika. You have researched this book author thoroughly using publicly available data. You are NOT writing an EMM yet. You are diagnosing their situation and generating ONLY the bespoke sections that require genuine intelligence about this specific person.

Do not claim to have read their book. Do not reference data sources explicitly. Write as if you synthesized this through careful observation.

AUTHOR DOSSIER:
{dossier}

KNOWN PAIN PATTERNS:
{pain_patterns}

GENERATE EXACTLY THE FOLLOWING — nothing else, no preamble, no markdown, no explanation:

DIAGNOSIS:
Primary pain pattern (1-8 above). One sentence of evidence from the dossier.
Secondary pain if applicable. One sentence of evidence.

CLUSTER: [Discovery OR Conversion OR Capacity]

IDENTITY_SPLIT: [Yes OR No]

WE_SEE_YOU:
120 words maximum. Name their specific situation using specific data points from the dossier. No flattery. No generic observations. The author should read this and feel slightly unsettled — like someone got inside their head. Reference concrete signals: rank, engagement patterns, what their readers say, where the gap is. Do not mention Opika.

THE_GAP:
60 words maximum. The single precise point of failure between where they are and where the book should be taking them. Not a category. A diagnosis.

STRATEGIC_INSIGHT:
80 words maximum. One non-obvious observation this specific author has likely never heard before. Must be derived from triangulating at least two data sources in the dossier. Cannot be generic marketing advice. If you cannot find a genuine insight, say so rather than inventing one.

CHAPTER_EXPERIMENT:
60 words maximum. One specific LinkedIn post concept built around their highest-performing content angle from the dossier. Name the angle, sketch the post concept, one sentence on why this angle specifically for this person.

LINKEDIN_POST_1:
120 words. Written in their voice based on their actual post samples from the dossier. Match their sentence length, vocabulary, whether they use vulnerability or authority, first or second person. Do not write generic thought leadership.

LINKEDIN_POST_2:
120 words. Different angle from Post 1. Same voice rules.

LINKEDIN_POST_3:
120 words. Different angle from Posts 1 and 2. Same voice rules.

EMAIL_HOOKS:
Day 1 — [subject line] — [one sentence description of angle]
Day 3 — [subject line] — [one sentence description of angle]
Day 6 — [subject line] — [one sentence description of angle]
Day 10 — [subject line] — [one sentence description of angle]
Day 14 — [subject line] — [one sentence description of angle]
"""

def run(dossier: dict) -> dict:
    """
    Calls Claude Sonnet with the assembled dossier.
    Returns parsed dict with all labeled sections.
    Target: ~1000-1200 output tokens.
    """
    dossier_text = _format_dossier(dossier)

    prompt = PROMPT_TEMPLATE.format(
        dossier=dossier_text,
        pain_patterns=PAIN_PATTERNS
    )

    message = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw_output = message.content[0].text
    return _parse_output(raw_output)


def _format_dossier(dossier: dict) -> str:
    """Converts dossier dict to clean readable text for the prompt."""
    lines = []

    lines.append(f"AUTHOR: {dossier['author_name']}")
    lines.append(f"BOOK: {dossier['book_title']}")
    lines.append(f"PUBLISHER: {dossier['book_publisher']}")
    lines.append(f"PUBLICATION DATE: {dossier['book_publication_date']}")
    lines.append(f"AMAZON RANK: {dossier['book_bsr']}")
    lines.append(f"AMAZON REVIEWS: {dossier['book_review_count']} reviews, avg {dossier['book_avg_rating']} stars")
    lines.append(f"GOODREADS: {dossier['goodreads_review_count']} reviews, avg {dossier['goodreads_avg_rating']} stars")
    lines.append(f"GOODREADS SHELVES: {', '.join(dossier['goodreads_shelves'][:8])}")
    lines.append("")
    lines.append(f"LINKEDIN HEADLINE: {dossier['linkedin_headline']}")
    lines.append(f"CURRENT ROLE: {dossier['linkedin_current_role']} at {dossier['linkedin_current_company']}")
    lines.append(f"FOLLOWERS: {dossier['linkedin_follower_count']}")
    lines.append(f"CONNECTIONS: {dossier['linkedin_connection_count']}")
    lines.append(f"ABOUT: {dossier['linkedin_about'][:500]}")
    lines.append("")
    lines.append("RECENT LINKEDIN POSTS (last 10):")
    for i, post in enumerate(dossier["linkedin_posts"][:10]):
        lines.append(f"  Post {i+1} ({post.get('date','')} | {post.get('numLikes',0)} likes | {post.get('numComments',0)} comments):")
        lines.append(f"  {post.get('text','')[:300]}")
    lines.append("")
    lines.append("RECENT ARTICLES (last 10):")
    for i, article in enumerate(dossier["linkedin_articles"][:10]):
        lines.append(f"  Article {i+1}: {article.get('title','')} ({article.get('publishedAt','')})")
    lines.append("")
    lines.append("WEBSITE:")
    lines.append(f"  Email capture: {dossier['website_has_email_capture']}")
    lines.append(f"  Speaking page: {dossier['website_has_speaking_page']}")
    lines.append(f"  Podcast: {dossier['website_has_podcast']}")
    lines.append(f"  Blog: {dossier['website_has_blog']}")
    lines.append(f"  About: {dossier['website_about_text'][:500]}")
    lines.append("")
    lines.append("ALL KNOWN BOOKS BY THIS AUTHOR:")
    for book in dossier["all_known_books"]:
        lines.append(f"  {book.get('title','')} — {book.get('date_info','')}")
    lines.append("")
    lines.append("TOP AMAZON REVIEWS (themes):")
    for review in dossier["amazon_top_reviews"][:5]:
        lines.append(f"  [{review.get('rating','')}] {review.get('text','')[:200]}")
    lines.append("")
    lines.append("TOP GOODREADS REVIEWS:")
    for review in dossier["goodreads_top_reviews"][:5]:
        lines.append(f"  {review[:200]}")
    lines.append("")
    lines.append("PODCAST APPEARANCES:")
    for pod in dossier["podcast_appearances"][:3]:
        lines.append(f"  {pod.get('show','')} — {pod.get('episode_title','')}")
        lines.append(f"  {pod.get('notes','')[:300]}")

    return "\n".join(lines)


def _parse_output(raw: str) -> dict:
    """
    Parses labeled sections from Claude's structured output.
    Returns dict with keys: CLUSTER, IDENTITY_SPLIT, WE_SEE_YOU,
    THE_GAP, STRATEGIC_INSIGHT, CHAPTER_EXPERIMENT,
    LINKEDIN_POST_1/2/3, EMAIL_HOOKS, DIAGNOSIS
    """
    result = {}
    current_key = None
    current_lines = []

    labels = [
        "DIAGNOSIS:", "CLUSTER:", "IDENTITY_SPLIT:", "WE_SEE_YOU:",
        "THE_GAP:", "STRATEGIC_INSIGHT:", "CHAPTER_EXPERIMENT:",
        "LINKEDIN_POST_1:", "LINKEDIN_POST_2:", "LINKEDIN_POST_3:", "EMAIL_HOOKS:"
    ]

    for line in raw.split("\n"):
        matched = False
        for label in labels:
            if line.strip().startswith(label):
                if current_key:
                    result[current_key] = "\n".join(current_lines).strip()
                current_key = label.rstrip(":")
                rest = line.strip()[len(label):].strip()
                current_lines = [rest] if rest else []
                matched = True
                break
        if not matched and current_key:
            current_lines.append(line)

    if current_key:
        result[current_key] = "\n".join(current_lines).strip()

    return result
```

---

## Layer 5 — EMM Body Selection (app/emm/selector.py)

```python
import json
import os

BODIES_DIR = os.path.join(os.path.dirname(__file__), "bodies")

def select(cluster: str) -> dict:
    """
    cluster: "Discovery" | "Conversion" | "Capacity"
    Loads the correct pre-built EMM body JSON.
    Falls back to Discovery if cluster unrecognized.
    """
    cluster_map = {
        "Discovery": "discovery.json",
        "Conversion": "conversion.json",
        "Capacity": "capacity.json"
    }
    filename = cluster_map.get(cluster, "discovery.json")
    path = os.path.join(BODIES_DIR, filename)

    with open(path, "r") as f:
        return json.load(f)
```

---

## Layer 5 — EMM Merger (app/emm/merger.py)

```python
def merge(body: dict, claude_output: dict, dossier: dict) -> dict:
    """
    Takes the pre-built body (which has merge field placeholders),
    Claude's output (bespoke sections), and the scraped dossier,
    and returns a single complete content dict ready for docx generation.

    Body merge fields use {field_name} syntax.
    The merger replaces all placeholders with real values.
    """
    content = body.copy()

    # Inject Claude's bespoke sections
    content["we_see_you"] = claude_output.get("WE_SEE_YOU", "")
    content["the_gap"] = claude_output.get("THE_GAP", "")
    content["strategic_insight"] = claude_output.get("STRATEGIC_INSIGHT", "")
    content["chapter_experiment"] = claude_output.get("CHAPTER_EXPERIMENT", "")
    content["linkedin_post_1"] = claude_output.get("LINKEDIN_POST_1", "")
    content["linkedin_post_2"] = claude_output.get("LINKEDIN_POST_2", "")
    content["linkedin_post_3"] = claude_output.get("LINKEDIN_POST_3", "")
    content["email_hooks"] = claude_output.get("EMAIL_HOOKS", "")
    content["diagnosis"] = claude_output.get("DIAGNOSIS", "")

    # Inject scraped data
    content["author_name"] = dossier["author_name"]
    content["book_title"] = dossier["book_title"]
    content["book_publisher"] = dossier["book_publisher"]
    content["book_publication_date"] = dossier["book_publication_date"]
    content["amazon_rank"] = dossier["book_bsr"]
    content["review_count"] = dossier["book_review_count"]
    content["avg_rating"] = dossier["book_avg_rating"]
    content["linkedin_followers"] = str(dossier["linkedin_follower_count"])
    content["current_role"] = dossier["linkedin_current_role"]
    content["current_company"] = dossier["linkedin_current_company"]
    content["cluster"] = claude_output.get("CLUSTER", "Discovery")
    content["identity_split"] = claude_output.get("IDENTITY_SPLIT", "No")

    return content
```

---

## EMM Body JSON Structure (app/emm/bodies/discovery.json)

This is the template structure. **You must write the actual body content.** This is the architectural schema — the real prose goes in after.

```json
{
  "cluster": "Discovery",
  "sections": {
    "hero": {
      "label": "The Opportunity",
      "static_content": "[WRITE THIS: 2-3 paragraphs framing the Discovery opportunity — why good books stay invisible and what that costs authors. This is Opika's Discovery cluster argument. Written once, used for all Discovery EMMs.]"
    },
    "we_see_you": {
      "label": "We See You",
      "content_field": "we_see_you"
    },
    "the_gap": {
      "label": "The Gap",
      "content_field": "the_gap"
    },
    "foundation": {
      "label": "What You've Built",
      "static_content": "[WRITE THIS: Discovery cluster framing of existing assets — what an author in this situation typically has built and why it isn't working. Generic enough to apply to any Discovery author.]"
    },
    "strategic_insight": {
      "label": "What We Found",
      "content_field": "strategic_insight"
    },
    "gtm_strategy": {
      "label": "The Play",
      "static_content": "[WRITE THIS: Discovery cluster GTM approach — specific channels and tactics for authors whose problem is top-of-funnel invisibility. Not generic. Specific to Discovery.]"
    },
    "chapter_experiment": {
      "label": "One Post. This Week.",
      "content_field": "chapter_experiment"
    },
    "roadmap": {
      "label": "90-Day Roadmap",
      "static_content": "[WRITE THIS: Discovery cluster 3-phase roadmap. Phase 1: Audit and architecture. Phase 2: Launch and test. Phase 3: Compound and scale. Specific milestones for Discovery situation.]"
    },
    "work_weve_done": {
      "label": "Work We've Done",
      "static_content": "[WRITE THIS: Opika's proof — what Opika has done for other authors in Discovery situations. Real or representative proof points. Written once for this cluster.]"
    },
    "ask": {
      "label": "What We're Asking",
      "static_content": "[WRITE THIS: The low-friction ask. Time commitment, what the author does vs. what Opika does, what a yes means. Standard for all EMMs.]"
    },
    "linkedin_posts": {
      "label": "Ready to Publish",
      "content_fields": ["linkedin_post_1", "linkedin_post_2", "linkedin_post_3"]
    },
    "email_sequence": {
      "label": "5-Email Nurture",
      "content_field": "email_hooks"
    }
  }
}
```

**Create three of these:** `discovery.json`, `conversion.json`, `capacity.json`. Each has different static_content sections written for that specific pain cluster.

---

## Layer 6 — Document Generation (app/document/generate.js)

Node.js script using `docx` npm package. Called from Python via subprocess.

**Opika Brand Spec:**
- Page: US Letter (12240 × 15840 DXA), 1 inch margins
- Title: 49pt ExtraBold, color #305A81 (Navy), font: JetBrains Mono
- Subtitle: 27pt Bold, color #FF4D71 (Pink), font: JetBrains Mono
- H3: 31pt Bold, color #305A81 (Navy), font: JetBrains Mono, pink bottom border
- Callout boxes: 19pt Bold, color #305A81, background #F5F7FA
- Body: 11pt Roboto, color #212C35 (Dark)
- Bullets: pink ● color #FF4D71, 11pt
- Footer: 8pt, Opika logo left, page number right
- Header: 7pt label, author name right
- Logo: 106px × 46px, top-right header, transparent background

```javascript
// app/document/generate.js
// Called via: node generate.js <content_json_path> <output_docx_path>

const { Document, Packer, Paragraph, TextRun, ImageRun,
        AlignmentType, HeadingLevel, BorderStyle, WidthType,
        Header, Footer, PageNumber, ShadingType,
        LevelFormat, TableRow, TableCell, Table } = require('docx');
const fs = require('fs');

const contentPath = process.argv[2];
const outputPath = process.argv[3];
const content = JSON.parse(fs.readFileSync(contentPath, 'utf8'));

// Load logo if available
let logoImage = null;
if (content.logo_path && fs.existsSync(content.logo_path)) {
  logoImage = fs.readFileSync(content.logo_path);
}

// Color constants
const NAVY = "305A81";
const PINK = "FF4D71";
const ORANGE = "FF6545";
const DARK = "212C35";
const LIGHT_GREY = "F5F7FA";

// Helper: Section header paragraph
function sectionHeader(text) {
  return new Paragraph({
    children: [new TextRun({ text, bold: true, size: 62, color: NAVY, font: "JetBrains Mono" })],
    spacing: { before: 480, after: 120 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: PINK, space: 4 } }
  });
}

// Helper: Body paragraph
function bodyPara(text, options = {}) {
  return new Paragraph({
    children: [new TextRun({ text, size: 22, color: DARK, font: "Roboto", ...options })],
    spacing: { before: 120, after: 120 }
  });
}

// Helper: Callout box (shaded paragraph)
function calloutPara(text) {
  return new Paragraph({
    children: [new TextRun({ text, bold: true, size: 38, color: NAVY, font: "Roboto" })],
    shading: { fill: LIGHT_GREY, type: ShadingType.CLEAR },
    spacing: { before: 240, after: 240 },
    indent: { left: 480, right: 480 }
  });
}

// Build document sections
const children = [];

// Cover / Hero
children.push(new Paragraph({
  children: [new TextRun({
    text: `Extra Mile Method`,
    bold: true, size: 98, color: NAVY, font: "JetBrains Mono"
  })],
  alignment: AlignmentType.LEFT,
  spacing: { before: 0, after: 120 }
}));

children.push(new Paragraph({
  children: [new TextRun({
    text: `A GTM Memo for ${content.author_name}`,
    bold: true, size: 54, color: PINK, font: "JetBrains Mono"
  })],
  spacing: { before: 0, after: 480 }
}));

// Section: We See You
children.push(sectionHeader("We See You"));
children.push(bodyPara(content.we_see_you));

// Section: The Gap
children.push(sectionHeader("The Gap"));
children.push(calloutPara(content.the_gap));

// Section: What We Found (Strategic Insight)
children.push(sectionHeader("What We Found"));
children.push(bodyPara(content.strategic_insight));

// Section: Static body sections from the cluster body
const sections = content.sections || {};
for (const [key, section] of Object.entries(sections)) {
  if (section.static_content) {
    children.push(sectionHeader(section.label));
    children.push(bodyPara(section.static_content));
  }
}

// Section: One Post This Week
children.push(sectionHeader("One Post. This Week."));
children.push(bodyPara(content.chapter_experiment));

// Section: LinkedIn Posts
children.push(sectionHeader("Ready to Publish"));
for (const post of [content.linkedin_post_1, content.linkedin_post_2, content.linkedin_post_3]) {
  if (post) {
    children.push(new Paragraph({
      children: [new TextRun({ text: post, size: 22, color: DARK, font: "Roboto", italics: true })],
      spacing: { before: 240, after: 240 },
      indent: { left: 480 }
    }));
    children.push(new Paragraph({ children: [], spacing: { before: 60, after: 60 } }));
  }
}

// Section: Email Hooks
children.push(sectionHeader("5-Email Sequence"));
const emailLines = (content.email_hooks || "").split("\n").filter(l => l.trim());
for (const line of emailLines) {
  children.push(bodyPara(line));
}

// Build and save
const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: "●",
        alignment: AlignmentType.LEFT,
        style: {
          run: { color: PINK, size: 22 },
          paragraph: { indent: { left: 720, hanging: 360 } }
        }
      }]
    }]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
      }
    },
    headers: {
      default: new Header({
        children: [
          new Paragraph({
            children: [
              new TextRun({ text: "OPIKA × EXTRA MILE METHOD", size: 14, color: "999999", font: "Roboto" }),
              new TextRun({ text: `\t${content.author_name}`, size: 14, color: "999999", font: "Roboto" })
            ],
            tabStops: [{ type: "right", position: 9360 }]
          })
        ]
      })
    },
    footers: {
      default: new Footer({
        children: [
          new Paragraph({
            children: [
              ...(logoImage ? [new ImageRun({
                data: logoImage, type: "png",
                transformation: { width: 106, height: 46 }
              })] : [new TextRun({ text: "Opika", size: 16, bold: true, color: NAVY, font: "JetBrains Mono" })]),
              new TextRun({ text: "\t", size: 16 }),
              new TextRun({ children: [PageNumber.CURRENT], size: 16, color: "999999", font: "Roboto" })
            ],
            tabStops: [{ type: "right", position: 9360 }]
          })
        ]
      })
    },
    children
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(outputPath, buffer);
  console.log(`Generated: ${outputPath}`);
});
```

---

### app/document/logo_processor.py

```python
import requests
import io
from PIL import Image
from app.config import settings

def download_and_process(output_path: str) -> str:
    """
    Downloads Opika logo, strips black background (pixels where r<30,g<30,b<30),
    saves as transparent PNG. Returns path to saved PNG.
    """
    resp = requests.get(settings.OPIKA_LOGO_URL, timeout=15)
    img = Image.open(io.BytesIO(resp.content)).convert("RGBA")

    data = img.getdata()
    new_data = []
    for item in data:
        r, g, b, a = item
        if r < 30 and g < 30 and b < 30:
            new_data.append((r, g, b, 0))  # transparent
        else:
            new_data.append(item)

    img.putdata(new_data)
    img.save(output_path, "PNG")
    return output_path
```

---

### app/document/pdf_converter.py

```python
import subprocess
import os

def convert(docx_path: str, job_id: str, output_dir: str) -> str:
    """
    Uses LibreOffice headless to convert .docx → .pdf
    Returns path to generated PDF.
    """
    result = subprocess.run(
        ["libreoffice", "--headless", "--convert-to", "pdf",
         "--outdir", output_dir, docx_path],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice conversion failed: {result.stderr}")

    pdf_filename = os.path.basename(docx_path).replace(".docx", ".pdf")
    pdf_path = os.path.join(output_dir, pdf_filename)

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found after conversion: {pdf_path}")

    return pdf_path
```

---

## Layer 7 — Job Store (app/utils/job_store.py)

```python
import redis
import json
import time
from app.config import settings

r = redis.from_url(settings.REDIS_URL)

def create_job(job_id: str, inputs: dict):
    data = {
        "job_id": job_id,
        "status": "queued",
        "message": "",
        "pdf_path": "",
        "error": "",
        "created_at": time.time(),
        "updated_at": time.time(),
        "inputs": inputs
    }
    r.set(f"job:{job_id}", json.dumps(data))

def update_status(job_id: str, status: str, message: str = "", pdf_path: str = "", error: str = ""):
    raw = r.get(f"job:{job_id}")
    if not raw:
        return
    data = json.loads(raw)
    data["status"] = status
    data["message"] = message
    data["pdf_path"] = pdf_path
    data["error"] = error
    data["updated_at"] = time.time()
    r.set(f"job:{job_id}", json.dumps(data))

def get_job(job_id: str) -> dict:
    raw = r.get(f"job:{job_id}")
    if not raw:
        return None
    return json.loads(raw)
```

---

## requirements.txt

```
fastapi==0.115.0
uvicorn==0.30.0
celery==5.4.0
redis==5.0.8
requests==2.32.3
beautifulsoup4==4.12.3
pillow==12.2.0
anthropic==0.40.0
python-dotenv==1.0.1
aiohttp==3.10.5
lxml==5.3.0
```

---

## package.json

```json
{
  "name": "emm-docx-generator",
  "version": "1.0.0",
  "scripts": {
    "generate": "node app/document/generate.js"
  },
  "dependencies": {
    "docx": "^8.5.0"
  }
}
```

---

## Installation & Setup

```bash
# 1. Clone and enter project
git clone <your-repo>
cd emm-pipeline

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install Node.js dependencies
npm install

# 5. Install LibreOffice (for PDF conversion)
# macOS:
brew install libreoffice
# Ubuntu/Debian:
sudo apt-get install libreoffice

# 6. Copy and fill in .env
cp .env.example .env
# Edit .env with your API keys

# 7. Start Redis (required for job queue)
# macOS:
brew services start redis
# Ubuntu:
sudo systemctl start redis

# 8. Start Celery worker (in separate terminal)
celery -A app.worker.celery_app worker --loglevel=info

# 9. Start FastAPI app
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## What Cursor Needs to Build (Checklist)

```
✅ Already fully specced above — Cursor implements as written:
  [ ] FastAPI app with 3 routes
  [ ] Celery + Redis job queue
  [ ] All scraper modules (linkedin, amazon, goodreads, website, google_search, google_books, assembler)
  [ ] Claude intelligence call module
  [ ] EMM selector and merger
  [ ] Node.js docx generator with Opika brand spec
  [ ] Logo processor (Pillow, transparency strip)
  [ ] LibreOffice PDF converter
  [ ] Job store (Redis-backed)
  [ ] Input form (static/index.html) with polling

✋ You need to do separately (not code — content):
  [ ] Write the 3 pre-built EMM body JSON files (discovery, conversion, capacity)
      These are the static_content sections — the strategic framework, roadmap,
      GTM approach, Opika proof points, and ask language for each cluster.
      This is the craft work. The code scaffolding is ready to receive them.
```

---

## Data Flow Summary

```
User submits form (5 fields)
        ↓
FastAPI creates job → enqueues Celery task
        ↓
PARALLEL:
  Thread A: LinkdAPI (3 credits)
    └── Full Profile → URN
    └── Posts (last 10)
    └── Articles (last 10)
  Thread B: Web scraping (0 cost)
    └── Amazon page
    └── Goodreads search + page
    └── Author website + blog posts
    └── Google: press coverage (5 results)
    └── Google: podcast appearances (5 results)
    └── Google Books: all titles
        ↓
Assembler builds structured dossier dict
        ↓
Single Claude Sonnet API call (~1200 tokens out)
  → Diagnosis, WE_SEE_YOU, THE_GAP, STRATEGIC_INSIGHT,
    CHAPTER_EXPERIMENT, 3 LinkedIn posts, 5 email hooks
        ↓
EMM selector picks body JSON (Discovery / Conversion / Capacity)
        ↓
Merger combines body + Claude output + dossier
        ↓
Logo processor downloads + strips Opika logo
        ↓
Node.js docx generator builds branded .docx
        ↓
LibreOffice converts .docx → .pdf
        ↓
PDF saved to /outputs/{job_id}.pdf
        ↓
User downloads finished EMM
```

---

*Architecture version 1.0 — Opika EMM Pipeline*
*Remove Notion. Remove Gamma. Opika branded .docx + PDF only.*
