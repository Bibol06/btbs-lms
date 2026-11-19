"""Human-readable default titles for uploaded files (QA-041).

Used only when the author leaves the title empty; existing titles are never renamed.
"""
import re
from pathlib import Path

_QUALITY = re.compile(r'\b(?:\d{3,4}p|[hx]\.?26[45]|hevc|hd|fhd|uhd|4k|60fps|30fps)\b', re.IGNORECASE)


def readable_title(filename, limit=200):
    stem = Path(str(filename).replace('\\', '/')).stem
    text = re.sub(r'[_]+', ' ', stem)
    text = _QUALITY.sub('', text)
    text = re.sub(r'\(\s*[,;\s]*\)|\[\s*[,;\s]*\]', '', text)  # brackets emptied by the line above
    text = re.sub(r'\s+([,;.)\]])', r'\1', text)
    text = re.sub(r'\s{2,}', ' ', text).strip(' -–—_.,;')
    return (text or stem or 'Материал')[:limit]
