"""WSGI entry point for Gunicorn behind exactly one trusted reverse proxy (Nginx).

Gunicorn does not rewrite REMOTE_ADDR from X-Forwarded-For, but login throttling,
password-recovery limits and analytics read the client IP from REMOTE_ADDR.
Nginx appends the peer address with $proxy_add_x_forwarded_for, so the right-most
entry is the only one we can trust; anything to its left is client-supplied.
"""
import ipaddress
import os

from django.core.wsgi import get_wsgi_application


def trusted_proxy(app, hops=1):
    def wrapped(environ, start_response):
        forwarded = [part.strip() for part in environ.get('HTTP_X_FORWARDED_FOR', '').split(',')]
        forwarded = [part for part in forwarded if part]
        if len(forwarded) >= hops:
            try:
                environ['REMOTE_ADDR'] = str(ipaddress.ip_address(forwarded[-hops]))
            except ValueError:
                pass  # keep the socket peer rather than trust a malformed value
        return app(environ, start_response)
    return wrapped


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
application = trusted_proxy(get_wsgi_application())
