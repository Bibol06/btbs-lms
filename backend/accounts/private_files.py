"""Keep local recovery mail, backup archives and the backup key private to this OS user."""
import csv
import os
from pathlib import Path
import subprocess

from django.core.mail.backends.filebased import EmailBackend


def restrict(path, directory=False):
    path = Path(path)
    if os.name != 'nt':
        path.chmod(0o700 if directory else 0o600)
        return
    flags = subprocess.CREATE_NO_WINDOW
    identity = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], check=True, capture_output=True, text=True, creationflags=flags)
    sid = next(csv.reader(identity.stdout.strip().splitlines()))[1]
    inheritance = '(OI)(CI)' if directory else ''
    subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', f'*{sid}:{inheritance}F', f'*S-1-5-18:{inheritance}F'],
                   check=True, capture_output=True, creationflags=flags)


class LocalRecoveryMailBackend(EmailBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        path = Path(self.file_path)
        path.mkdir(parents=True, exist_ok=True)
        restrict(path, directory=True)
