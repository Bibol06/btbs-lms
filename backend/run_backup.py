"""Windowless scheduled-task entry point; diagnostics stay in a local log."""
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
logs = root / '.local'
logs.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

if __name__ == '__main__':
    with (logs / 'backup-task.log').open('a', encoding='utf-8', buffering=1) as log:
        sys.stdout = sys.stderr = log
        from datetime import datetime, timezone
        print(f'Backup task started: {datetime.now(timezone.utc).isoformat()}')
        import django
        django.setup()
        from django.core.management import call_command
        call_command('backup_lms', if_due=True)
        print('Backup task completed.')
