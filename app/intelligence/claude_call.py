import anthropic

from app.config import settings


client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY) if settings.ANTHROPIC_API_KEY else None

PAIN_PATTERNS = """
1. THE SILENCE
2. THE CREDENTIAL GAP
3. THE KEYNOTE EVAPORATION
4. THE CONTENT BURNOUT
5. THE AGING CLASSIC
6. THE IDENTITY SPLIT
7. THE DISCONNECTED ARCHIPELAGO
8. THE STAGE-TO-SCREEN GAP
"""

PROMPT_TEMPLATE = """
You are a senior GTM strategist at Opika.

AUTHOR DOSSIER:
{dossier}

KNOWN PAIN PATTERNS:
{pain_patterns}

Return exactly these labels:
DIAGNOSIS:
CLUSTER:
IDENTITY_SPLIT:
WE_SEE_YOU:
THE_GAP:
STRATEGIC_INSIGHT:
CHAPTER_EXPERIMENT:
LINKEDIN_POST_1:
LINKEDIN_POST_2:
LINKEDIN_POST_3:
EMAIL_HOOKS:
"""

REQUIRED_KEYS = {
    "DIAGNOSIS",
    "CLUSTER",
    "IDENTITY_SPLIT",
    "WE_SEE_YOU",
    "THE_GAP",
    "STRATEGIC_INSIGHT",
    "CHAPTER_EXPERIMENT",
    "LINKEDIN_POST_1",
    "LINKEDIN_POST_2",
    "LINKEDIN_POST_3",
    "EMAIL_HOOKS",
}


def run(dossier: dict) -> dict:
    if client is None:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    prompt = PROMPT_TEMPLATE.format(dossier=_format_dossier(dossier), pain_patterns=PAIN_PATTERNS)
    message = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text
    parsed = _parse_output(raw)
    missing = REQUIRED_KEYS - set(parsed.keys())
    if missing:
        raise ValueError(f"Claude output missing required sections: {', '.join(sorted(missing))}")
    return parsed


def _format_dossier(dossier: dict) -> str:
    lines = [
        f"AUTHOR: {dossier.get('author_name', '')}",
        f"BOOK: {dossier.get('book_title', '')}",
        f"PUBLISHER: {dossier.get('book_publisher', '')}",
        f"PUBLICATION DATE: {dossier.get('book_publication_date', '')}",
        f"AMAZON RANK: {dossier.get('book_bsr', '')}",
        f"AMAZON REVIEWS: {dossier.get('book_review_count', '')} avg {dossier.get('book_avg_rating', '')}",
        f"GOODREADS: {dossier.get('goodreads_review_count', '')} avg {dossier.get('goodreads_avg_rating', '')}",
        f"LINKEDIN HEADLINE: {dossier.get('linkedin_headline', '')}",
        f"FOLLOWERS: {dossier.get('linkedin_follower_count', 0)}",
        f"ABOUT: {dossier.get('linkedin_about', '')[:500]}",
    ]
    lines.append("RECENT POSTS:")
    for post in dossier.get("linkedin_posts", [])[:10]:
        lines.append(
            f"- {post.get('date','')} | {post.get('numLikes',0)} likes | {post.get('numComments',0)} comments | {post.get('text','')[:300]}"
        )
    return "\n".join(lines)


def _parse_output(raw: str) -> dict:
    labels = [f"{k}:" for k in REQUIRED_KEYS]
    out = {}
    current = None
    buf = []
    for line in raw.splitlines():
        stripped = line.strip()
        matched = False
        for label in labels:
            if stripped.startswith(label):
                if current:
                    out[current] = "\n".join(buf).strip()
                current = label[:-1]
                remainder = stripped[len(label) :].strip()
                buf = [remainder] if remainder else []
                matched = True
                break
        if not matched and current:
            buf.append(line)
    if current:
        out[current] = "\n".join(buf).strip()
    return out
