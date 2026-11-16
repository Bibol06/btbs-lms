"""Canonical address shared by local and temporary public LMS processes."""
import ipaddress
import json
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings


def external_https_url(value):
    try:
        parts = urlsplit(value)
        host = (parts.hostname or '').lower()
        if (parts.scheme != 'https' or not host or parts.username or parts.password
                or parts.query or parts.fragment or parts.path not in ('', '/')
                or parts.port not in (None, 443) or host == 'localhost'
                or host.endswith(('.localhost', '.local'))):
            return ''
        try:
            if not ipaddress.ip_address(host).is_global:
                return ''
        except ValueError:
            if '.' not in host:
                return ''
        return value.rstrip('/')
    except (ValueError, TypeError):
        return ''


def temporary_public_url():
    try:
        data = json.loads(Path(settings.LMS_PUBLIC_URL_FILE).read_text(encoding='utf-8-sig'))
        value = external_https_url(data.get('url', ''))
        if data.get('source') == 'temporary_share' and urlsplit(value).hostname.endswith('.trycloudflare.com'):
            return value
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return ''
