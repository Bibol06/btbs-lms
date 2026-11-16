"""Create two scoped demonstration accounts without changing existing users."""
import json
import os
import secrets
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import SystemAuditEvent


class Command(BaseCommand):
    help = 'Create scoped demo administrators; credentials stay in the local ignored access file.'

    def add_arguments(self, parser):
        parser.add_argument('--access-file', type=Path, default=settings.BASE_DIR.parent / '.local' / 'demo-access.json')

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Demo account setup is available only with DEBUG=True.')
        path = options['access_file'].resolve()
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
            if not isinstance(data, dict) or not isinstance(data.get('accounts', {}), dict):
                raise ValueError('Invalid accounts structure')
        except (ValueError, OSError) as exc:
            raise CommandError('Cannot read the local access file; no users were changed.') from exc
        accounts = data.setdefault('accounts', {})
        User = get_user_model()
        owner = User.objects.filter(is_active=True, role='admin', admin_scope='full').first()
        if owner is None:
            raise CommandError('An active platform owner must exist before demo setup.')
        definitions = [
            ('system_admin', 'demo_system_admin', 'system', 'Арман', 'Толеубаев'),
            ('learning_admin', 'demo_learning_admin', 'learning', 'Мадина', 'Касымова'),
        ]
        created = 0
        with transaction.atomic():
            for key, username, scope, first_name, last_name in definitions:
                user = User.objects.select_for_update().filter(username__iexact=username).first()
                recorded = accounts.get(key, {})
                if not isinstance(recorded, dict):
                    raise CommandError(f'Invalid local record for {key}; no users were changed.')
                if user:
                    if not (recorded.get('id') == user.id and recorded.get('username') == user.username
                            and isinstance(recorded.get('password'), str) and user.check_password(recorded['password'])
                            and user.role == 'admin' and user.admin_scope == scope
                            and user.is_active and not user.is_superuser and not user.is_staff):
                        raise CommandError(f'{username} already exists or was changed; refusing to overwrite it.')
                    continue
                if recorded:
                    raise CommandError(f'Local record {key} already exists; refusing to replace its credentials.')
                password = secrets.token_urlsafe(24)
                user = User.objects.create_user(username=username, password=password, first_name=first_name,
                    last_name=last_name, role='admin', admin_scope=scope, is_staff=False, is_superuser=False)
                accounts[key] = {'id': user.id, 'username': username, 'password': password,
                    'display_name': f'{last_name} {first_name}', 'admin_scope': scope, 'demo': True}
                SystemAuditEvent.objects.create(actor=owner, target=user, action='account.responsibility_changed',
                    details={'source': 'demo_setup', 'before': None, 'after': {'role': 'admin', 'admin_scope': scope}})
                created += 1
            if created:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
                        temporary = Path(stream.name)
                        json.dump(data, stream, ensure_ascii=False, indent=2)
                        stream.write('\n')
                    os.replace(temporary, path)
                finally:
                    if temporary and temporary.exists():
                        temporary.unlink()
        self.stdout.write(f'Demo administrators created: {created}. Existing accounts and passwords unchanged.')
        self.stdout.write(f'Credentials saved locally: {path}')
