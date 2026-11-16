import hashlib
import urllib.request
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Install checksum-verified WASI Python into the local sandbox runtime folder'

    def handle(self, *args, **kwargs):
        base = 'https://github.com/vmware-labs/webassembly-language-runtimes/releases/download/python/3.12.0%2B20231211-040d5a6/'
        name = 'python-3.12.0.wasm'
        folder = Path(settings.BASE_DIR).parent / '.local/runtime'
        folder.mkdir(parents=True, exist_ok=True)
        expected = urllib.request.urlopen(base + name + '.sha256sum', timeout=30).read().decode().split()[0]
        target = folder / name
        if not target.exists():
            urllib.request.urlretrieve(base + name, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise CommandError('Не совпадает SHA256 среды Python')
        self.stdout.write(self.style.SUCCESS('Изолированная среда Python готова'))
