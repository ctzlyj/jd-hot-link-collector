"""Publish complete JPEGs atomically; coalesce shared public-URL downloads."""
import hashlib
import io
import os
import tempfile
import threading
from pathlib import Path
from PIL import Image

_LOCKS = [threading.Lock() for _ in range(64)]


def _valid_jpeg(data):
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != 'JPEG':
                return False
            image.load()
        return True
    except (OSError, ValueError):
        return False


def _publish(destination, data):
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=destination.name+'.',
                                         suffix='.part', delete=False) as out:
            pending = Path(out.name)
            out.write(data)
        os.replace(pending, destination)
    finally:
        if pending is not None and pending.exists():
            pending.unlink()


def save_cached_jpeg(url, destination, cache_root, stage, fetch):
    destination = Path(destination).resolve()
    stage = Path(stage).resolve()
    if not destination.is_relative_to(stage):
        raise ValueError('JPEG_DESTINATION_OUTSIDE_STAGE')
    key = hashlib.sha256(url.encode()).hexdigest()
    cache = Path(cache_root) / (key + '.jpg')
    with _LOCKS[int(key[:8], 16) % len(_LOCKS)]:
        data = cache.read_bytes() if cache.is_file() else b''
        if not _valid_jpeg(data):
            with Image.open(io.BytesIO(fetch(url))) as image:
                image.load()
                if image.mode == 'RGBA':
                    rgb = Image.new('RGB', image.size, 'white')
                    rgb.paste(image, mask=image.getchannel('A'))
                else:
                    rgb = image.convert('RGB')
                encoded = io.BytesIO()
                rgb.save(encoded, 'JPEG', quality=92)
                data = encoded.getvalue()
            if not _valid_jpeg(data):
                raise ValueError('JPEG_VALIDATION_FAILED')
            _publish(cache, data)
        if not destination.is_file() or destination.read_bytes() != data:
            _publish(destination, data)
    return str(destination.relative_to(stage))
