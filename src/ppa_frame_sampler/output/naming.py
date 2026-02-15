from __future__ import annotations

import re


def safe_slug(text: str, max_len: int = 200) -> str:
    """Convert *text* to a filesystem-safe slug.

    Unsafe characters are replaced with underscores, consecutive underscores
    are collapsed, and the result is truncated to *max_len* characters.
    Returns ``"item"`` for empty / whitespace-only input.
    """
    slug = re.sub(r'[^\w\-.]', '_', text)
    slug = re.sub(r'_+', '_', slug)
    slug = slug.strip('_')
    slug = slug[:max_len]
    return slug or "item"
