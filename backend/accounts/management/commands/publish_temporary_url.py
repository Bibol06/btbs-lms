import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.public_url import external_https_url, temporary_public_url


class Command(BaseCommand):
    help = 'Publish an externally checked temporary LMS address for recovery emails.'

    def add_arguments(self, parser):
        parser.add_argument('--url', required=True)
        parser.add_argument('--clear', action='store_true')

    def handle(self, *args, **options):
        value = external_https_url(options['url'])
        if not value or not urlsplit(value).hostname.endswith('.trycloudflare.com'):
            raise CommandError('Expected an HTTPS trycloudflare.com root address.')
        target = Path(settings.LMS_PUBLIC_URL_FILE)
        if options['clear']:
            if temporary_public_url() == value:
                target.unlink(missing_ok=True)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        stage = target.with_suffix('.tmp')
        stage.write_text(json.dumps({'url': value, 'source': 'temporary_share',
            'verified_at': timezone.now().isoformat()}), encoding='utf-8')
        os.replace(stage, target)
        self.stdout.write('Public recovery address updated.')
