"""Analyse déterministe de la luminance d'un fond d'écran local."""
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from PIL import Image, ImageOps


ALGORITHM_VERSION = 1
SAMPLE_SIDE = 128
# Calibrés entre les groupes de gris 80/128, gradient/Sway bleu et 192/224.
THRESHOLDS = (0.15, 0.30, 0.64)
FLAVORS = ('mocha', 'macchiato', 'frappe', 'latte')
CACHE = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'labfy-appearance/analyses'


def linear_channel(value):
    """sRGB normalisé vers lumière linéaire, conformément à IEC 61966-2-1."""
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def quantile(sorted_values, fraction):
    position = (len(sorted_values) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return sorted_values[low]
    return sorted_values[low] * (high - position) + sorted_values[high] * (position - low)


def classify(score):
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError('Score de luminance invalide')
    return FLAVORS[sum(score >= threshold for threshold in THRESHOLDS)]


def cache_key(meta):
    # CONTRACT: changer l'algorithme ou le fichier invalide l'analyse cachée.
    payload = json.dumps([ALGORITHM_VERSION, meta['canonicalPath'], meta['size'], meta['mtime']],
                         ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def sample_luminance(meta):
    with Image.open(meta['canonicalPath']) as source:
        sample = ImageOps.exif_transpose(source)
        # WHY: les métriques travaillent sur <= 16 384 pixels, même pour une
        # image 4K ; le noir explicite représente les zones transparentes.
        sample.thumbnail((SAMPLE_SIDE, SAMPLE_SIDE), Image.Resampling.LANCZOS)
        if 'A' in sample.getbands() or 'transparency' in sample.info:
            rgba = sample.convert('RGBA')
            rgb = Image.new('RGB', rgba.size, (0, 0, 0))
            rgb.paste(rgba, mask=rgba.getchannel('A'))
        else:
            rgb = sample.convert('RGB')
        values = []
        for red, green, blue in rgb.get_flattened_data():
            values.append(0.2126 * linear_channel(red / 255)
                          + 0.7152 * linear_channel(green / 255)
                          + 0.0722 * linear_channel(blue / 255))
    return sorted(values)


def compute(meta):
    values = sample_luminance(meta)
    if not values:
        raise ValueError('Image vide')
    mean = sum(values) / len(values)
    median = quantile(values, 0.50)
    p10, p25 = quantile(values, 0.10), quantile(values, 0.25)
    p75, p90 = quantile(values, 0.75), quantile(values, 0.90)
    # La médiane évite qu'une petite zone opposée domine ; les quartiles
    # séparent les compositions mixtes des fonds uniformes de même moyenne.
    score = 0.50 * median + 0.30 * mean + 0.10 * p25 + 0.10 * p75
    return {'path': meta['path'], 'mean': mean, 'median': median,
            'p10': p10, 'p25': p25, 'p75': p75, 'p90': p90,
            'score': score, 'flavor': classify(score),
            'algorithmVersion': ALGORITHM_VERSION}


def analyze(meta):
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / (cache_key(meta) + '.json')
    try:
        cached = json.loads(target.read_text(encoding='utf-8'))
        if cached.get('algorithmVersion') == ALGORITHM_VERSION \
                and cached.get('path') == meta['path'] \
                and cached.get('flavor') == classify(cached.get('score')):
            return cached
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    result = compute(meta)
    fd, temporary = tempfile.mkstemp(prefix='.analysis-', suffix='.json', dir=CACHE)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, separators=(',', ':'))
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    # Nettoyage local et non périodique : aucune base de données ni daemon.
    entries = list(CACHE.glob('*.json'))
    if len(entries) > 256:
        for old in sorted(entries, key=lambda item: item.stat().st_mtime_ns)[:len(entries) - 224]:
            if old != target:
                old.unlink(missing_ok=True)
    return result
