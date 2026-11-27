"""Same-host JD CDN image size variants; pure URL logic, no network."""
from __future__ import annotations
import re
from urllib.parse import urlsplit, urlunsplit

# JD image CDN publishes one image at several size segments (/n1/, /n5/,
# /s800x800_/...). /n12/ is the 800x800 standard variant without the JD.COM
# watermark that /n0/ carries. A corrupt size variant is repaired by switching
# the segment on the same image host, never by switching hosts.
_SIZE_SEGMENT = re.compile(r'^/(?:n\d+|s\d+x\d+_)(?=/)')


def clean_variant(url):
    """Same-host standard-size variant of a JD CDN image URL, or None."""
    parts = urlsplit(str(url))
    if (parts.scheme not in ('https', '') or parts.username or parts.password
            or not (parts.hostname or '').endswith('.360buyimg.com')):
        return None
    if not _SIZE_SEGMENT.match(parts.path):
        return None
    return urlunsplit((parts.scheme, parts.netloc, _SIZE_SEGMENT.sub('/n12', parts.path, count=1),
                       parts.query, ''))


def save_with_clean_fallback(save, url, destination):
    """Run save(url, destination); on failure retry the same-host n12 variant.

    Returns a substitution note for durable receipts, or None when the original
    URL worked. When no variant exists or the variant also fails, the failure
    propagates so the caller records a dead link instead of a silent gap.
    """
    try:
        save(url, destination)
        return None
    except Exception as error:
        status = getattr(getattr(error, 'response', None), 'status_code', None)
        image_invalid = isinstance(error, ValueError) and str(error) == 'JPEG_VALIDATION_FAILED'
        if status not in (404, 410) and not image_invalid:
            raise
        variant = clean_variant(url)
        if not variant or variant == str(url):
            raise
        save(variant, destination)
        return {'file': getattr(destination, 'name', str(destination)), 'originalUrl': str(url),
                'variantUrl': variant, 'reason': type(error).__name__}


def reuse_variant(url, destination, folder, notes):
    """Another slot may share a proven replacement for exactly the same original URL."""
    note = next((row for row in notes if row['originalUrl'] == url), None)
    if note is None:
        return url
    note.setdefault('alsoUsedFor', []).append(destination.relative_to(folder).as_posix())
    return note['variantUrl']


def readback_entries(entries, notes):
    """Bind saved replacements to original main slots and their exact dependent SKU slots."""
    by_file = {entry['file']: entry for entry in entries}
    replaced = {}
    if not isinstance(notes, list):
        raise ValueError('INVALID_VARIANT_NOTES')
    for note in notes:
        name, original, variant = note['file'], note['originalUrl'], note['variantUrl']
        main = '主图/' + name
        others = note.get('alsoUsedFor', [])
        if (not isinstance(others, list) or any(not key.startswith('SKU图/') for key in others)
                or not variant or variant == original or clean_variant(original) != variant):
            raise ValueError('INVALID_MAIN_IMAGE_VARIANT')
        for key in [main, *others]:
            if key in replaced or key not in by_file or by_file[key]['url'] != original:
                raise ValueError('VARIANT_SOURCE_OR_SLOT_MISMATCH')
            replaced[key] = variant
    return [{**row, 'url': replaced.get(row['file'], row['url'])} for row in entries]
