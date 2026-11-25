"""Same-host JD CDN image size variants; pure URL logic, no network."""
from __future__ import annotations
import re
from urllib.parse import urlsplit, urlunsplit

# JD image CDN publishes one image at several size segments (/n1/, /n5/,
# /s800x800_/...); /n0/ is the standard-size original. A corrupt size variant is
# repaired by switching the segment on the same image host, never by switching hosts.
_SIZE_SEGMENT = re.compile(r'^/(?:n\d+|s\d+x\d+_)')


def n0_variant(url):
    """Same-host standard-size variant of a JD CDN image URL, or None."""
    parts = urlsplit(str(url))
    if not (parts.hostname or '').endswith('.360buyimg.com'):
        return None
    if not _SIZE_SEGMENT.match(parts.path):
        return None
    return urlunsplit((parts.scheme, parts.netloc, _SIZE_SEGMENT.sub('/n0', parts.path, count=1),
                       parts.query, ''))


def save_with_n0_fallback(save, url, destination):
    """Run save(url, destination); on failure retry the same-host n0 variant.

    Returns a substitution note for durable receipts, or None when the original
    URL worked. When no variant exists or the variant also fails, the failure
    propagates so the caller records a dead link instead of a silent gap.
    """
    try:
        save(url, destination)
        return None
    except Exception as error:
        variant = n0_variant(url)
        if not variant:
            raise
        save(variant, destination)
        return {'file': getattr(destination, 'name', str(destination)), 'originalUrl': str(url),
                'variantUrl': variant, 'reason': type(error).__name__}
