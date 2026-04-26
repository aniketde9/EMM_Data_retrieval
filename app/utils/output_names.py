"""Stable, filesystem-safe names for pipeline output files."""

from __future__ import annotations

import os
import re

_INVALID_WIN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_author_for_filename(author_name: str, max_len: int = 80) -> str:
    s = (author_name or "").strip()
    s = _INVALID_WIN_CHARS.sub("", s)
    s = re.sub(r"\s+", "_", s)
    s = s.strip("._")
    if not s:
        return "unknown_author"
    return s[:max_len]


def job_hex_suffix(job_id: str, n: int = 8) -> str:
    """Last n hex digits from job_id (UUIDs become a short unique tail)."""
    hex_digits = "".join(c for c in job_id.lower() if c in "0123456789abcdef")
    if len(hex_digits) < n:
        return hex_digits or "job"
    return hex_digits[-n:]


def research_json_filename(author_name: str, job_id: str) -> str:
    base = sanitize_author_for_filename(author_name)
    suffix = job_hex_suffix(job_id)
    return f"{base}__{suffix}_research.json"


def research_json_path(output_dir: str, author_name: str, job_id: str) -> str:
    return os.path.join(output_dir, research_json_filename(author_name, job_id))
