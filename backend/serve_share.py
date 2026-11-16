"""Serve only the compiled frontend and Django routes on a loopback port."""
import argparse
import os
from pathlib import Path

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.share_settings'

from django.conf import settings
from django.core.wsgi import get_wsgi_application
from waitress import serve
from whitenoise import WhiteNoise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8001)
    args = parser.parse_args()
    frontend = Path(__file__).resolve().parent.parent / 'frontend' / 'dist'
    if not (frontend / 'index.html').is_file():
        raise SystemExit('Сначала выполните npm run build в frontend')
    django_app = get_wsgi_application()
    app = WhiteNoise(django_app, root=str(frontend), index_file=True, allow_all_origins=False)
    if settings.STATIC_ROOT.is_dir():
        app.add_files(str(settings.STATIC_ROOT), prefix='static/')
    serve(app, host='127.0.0.1', port=args.port, threads=8,
          trusted_proxy='127.0.0.1', trusted_proxy_count=1,
          trusted_proxy_headers={'x-forwarded-proto', 'x-forwarded-for'},
          clear_untrusted_proxy_headers=True, expose_tracebacks=False,
          max_request_body_size=110 * 1024 * 1024)


if __name__ == '__main__':
    main()
