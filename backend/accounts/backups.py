"""Encrypted PostgreSQL snapshots with copies of referenced local/S3 media."""
import base64
from contextlib import contextmanager
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import subprocess
import tempfile
from uuid import uuid4
import zipfile
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

MAGIC = b'BTBSBACKUP1\n'
CHUNK = 1024 * 1024


class BackupError(Exception):
    pass


class BackupBusy(BackupError):
    pass


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def root():
    return settings.LMS_BACKUP_DIR.resolve()


@contextmanager
def backup_lock():
    root().mkdir(parents=True, exist_ok=True)
    with (root() / '.lock').open('a+b') as stream:
        stream.seek(0)
        if not stream.read(1):
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise BackupBusy('Резервное копирование уже выполняется') from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def key_bytes(create=False):
    path = settings.LMS_BACKUP_KEY_FILE
    if not path.exists() and create:
        if any(root().glob('*.lmsbak')):
            raise BackupError('Ключ резервных копий отсутствует. Восстановите прежний ключ.')
        path.parent.mkdir(parents=True, exist_ok=True)
        from .private_files import restrict
        restrict(path.parent, directory=True)
        try:
            with path.open('x', encoding='ascii') as stream:
                stream.write(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
        except FileExistsError:
            pass
        restrict(path)
    try:
        key = base64.urlsafe_b64decode(path.read_text(encoding='ascii').strip())
        if len(key) != 32:
            raise ValueError()
        return key
    except (OSError, ValueError) as exc:
        raise BackupError('Не найден корректный ключ резервных копий') from exc


def pg_tool(name):
    candidates = [Path(settings.LMS_PG_BIN) / (name + ('.exe' if os.name == 'nt' else ''))] if settings.LMS_PG_BIN else []
    found = shutil.which(name)
    if found:
        candidates.append(Path(found))
    if os.name == 'nt':
        parent = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'PostgreSQL'
        candidates.extend(sorted(parent.glob(f'*/bin/{name}.exe'), reverse=True))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise BackupError(f'Не найден {name}. Укажите LMS_PG_BIN в backend/.env.')


def pg_environment(database=None):
    db = settings.DATABASES['default']
    env = dict(os.environ)
    for key, value in {'PGHOST': db.get('HOST') or 'localhost', 'PGPORT': db.get('PORT') or '5432',
                       'PGUSER': db.get('USER') or '', 'PGPASSWORD': db.get('PASSWORD') or '',
                       'PGDATABASE': database or db['NAME'], 'PGCONNECT_TIMEOUT': '10'}.items():
        env[key] = str(value)
    return env


def pg_run(name, args, database=None):
    result = subprocess.run([pg_tool(name), '--no-password', *args], env=pg_environment(database), capture_output=True, timeout=7200,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        raise BackupError(f'{name}: операция не выполнена. Проверьте PostgreSQL, права и свободное место.')
    return result


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def encrypt(source, destination, key):
    nonce = secrets.token_bytes(12)
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    cipher.authenticate_additional_data(MAGIC)
    with Path(source).open('rb') as incoming, Path(destination).open('xb') as outgoing:
        outgoing.write(MAGIC + nonce)
        while chunk := incoming.read(CHUNK):
            outgoing.write(cipher.update(chunk))
        outgoing.write(cipher.finalize())
        outgoing.write(cipher.tag)
        outgoing.flush(); os.fsync(outgoing.fileno())


def decrypt(source, destination, key):
    try:
        with Path(source).open('rb') as incoming, Path(destination).open('xb') as outgoing:
            if incoming.read(len(MAGIC)) != MAGIC:
                raise ValueError()
            nonce = incoming.read(12)
            incoming.seek(-16, os.SEEK_END)
            end, tag = incoming.tell(), incoming.read(16)
            incoming.seek(len(MAGIC)+12)
            cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
            cipher.authenticate_additional_data(MAGIC)
            while incoming.tell() < end:
                outgoing.write(cipher.update(incoming.read(min(CHUNK, end-incoming.tell()))))
            outgoing.write(cipher.finalize())
    except Exception as exc:
        Path(destination).unlink(missing_ok=True)
        raise BackupError('Архив повреждён или выбран неверный ключ') from exc


def media_sources():
    from learning.models import LessonMaterial
    from courses.models import CourseImage
    from assessment.models import Submission
    sources = {}
    for model in [LessonMaterial, CourseImage, Submission]:
        for item in model.objects.exclude(file='').iterator():
            sources.setdefault(item.file.name, item.file.storage)
    return sources


@contextmanager
def open_media(storage, name):
    if name.startswith('_s3/'):
        remote = storage.remote
        stream = remote.connection.meta.client.get_object(Bucket=remote.bucket_name, Key=name)['Body']
        try:
            yield stream
        finally:
            stream.close()
    else:
        with storage.open(name, 'rb') as stream:
            yield stream


def safe_media_name(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or name != str(path):
        raise BackupError('Некорректный путь файла в резервной копии')
    return name


def critical_counts():
    from django.contrib.auth import get_user_model
    from courses.models import Course, CourseRun, Enrollment
    from learning.models import Step
    from assessment.models import Submission, QuizAttempt
    return {m._meta.db_table: m.objects.count() for m in [get_user_model(), Course, CourseRun, Enrollment, Step, Submission, QuizAttempt]}


def next_due(stamp):
    local = stamp.astimezone(ZoneInfo(settings.ANALYTICS_TIMEZONE))
    return (local.replace(hour=settings.LMS_BACKUP_HOUR, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat()


def backup_status():
    state = read_json(root() / 'status.json')
    rows = []
    for path in sorted(root().glob('btbs-*.lmsbak'), key=lambda p: p.stat().st_mtime_ns, reverse=True)[:settings.LMS_BACKUP_KEEP]:
        rows.append({'name': path.name, 'bytes': path.stat().st_size})
    return {**state, 'archives': rows, 'queued': (root() / 'requested.json').exists(),
            'key_available': settings.LMS_BACKUP_KEY_FILE.is_file(), 'keep': settings.LMS_BACKUP_KEEP,
            'schedule_hour': settings.LMS_BACKUP_HOUR, 'timezone': settings.ANALYTICS_TIMEZONE,
            'location': 'local+s3' if settings.LMS_BACKUP_S3_BUCKET else 'local',
            'restore_check': read_json(root() / 'restore-check.json')}


def backup_due():
    state = read_json(root() / 'status.json')
    now = timezone.now()
    if state.get('last_attempt'):
        if now < datetime.fromisoformat(state['last_attempt']) + timedelta(minutes=15):
            return False
    return not state.get('next_due') or now >= datetime.fromisoformat(state['next_due'])


def create_backup(if_due=False):
    with backup_lock():
        requested = root() / 'requested.json'
        if if_due and not requested.exists() and not backup_due():
            return None
        requested.unlink(missing_ok=True)
        state = read_json(root() / 'status.json')
        state.update(running=True, last_attempt=timezone.now().isoformat(), error=None)
        write_json(root() / 'status.json', state)
        destination = root() / f'btbs-{timezone.now():%Y%m%dT%H%M%S%f}-{uuid4().hex[:8]}.lmsbak'
        partial = destination.with_suffix('.part')
        try:
            from .private_files import restrict
            restrict(root(), directory=True)
            if shutil.disk_usage(root()).free < 256*1024**2:
                raise BackupError('Недостаточно места для резервной копии')
            key = key_bytes(create=True)
            with tempfile.TemporaryDirectory(prefix='.creating-', dir=root()) as temporary:
                temp = Path(temporary)
                dump, package = temp / 'database.dump', temp / 'backup.zip'
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                        cursor.execute('SELECT pg_export_snapshot()')
                        snapshot = cursor.fetchone()[0]
                    counts, sources = critical_counts(), media_sources()
                    # ZIP, encrypted archive and validation copy coexist locally.
                    # Fail early rather than filling the server disk with large videos.
                    media_bytes = sum(storage.size(name) for name, storage in sources.items())
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT pg_database_size(current_database())')
                        database_bytes = cursor.fetchone()[0]
                    required = 4 * (media_bytes + database_bytes) + 512 * 1024**2
                    if shutil.disk_usage(root()).free < required:
                        raise BackupError('Недостаточно места: для безопасной сборки архива требуется больше свободного диска. Предыдущие копии сохранены.')
                    pg_run('pg_dump', ['--format=custom', '--no-owner', '--no-acl', '--snapshot=' + snapshot, '--file=' + str(dump)])
                    manifest = {'version': 1, 'created_at': timezone.now().isoformat(), 'database_sha256': digest(dump),
                                'database_bytes': dump.stat().st_size, 'counts': counts, 'files': []}
                    with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                        archive.write(dump, 'database.dump')
                        for name, storage in sorted(sources.items()):
                            safe_media_name(name)
                            sha, size = hashlib.sha256(), 0
                            with open_media(storage, name) as incoming, archive.open('media/' + name, 'w', force_zip64=True) as outgoing:
                                while chunk := incoming.read(CHUNK):
                                    outgoing.write(chunk); sha.update(chunk); size += len(chunk)
                            manifest['files'].append({'name': name, 'sha256': sha.hexdigest(), 'bytes': size})
                        archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
                encrypt(package, partial, key)
                # Authenticate the completed encrypted archive before publishing it.
                verified = temp / 'verified.zip'
                decrypt(partial, verified, key)
                with zipfile.ZipFile(verified) as archive:
                    if archive.testzip():
                        raise BackupError('Не удалось проверить целостность архива')
                os.replace(partial, destination)
            from .backup_remote import upload_archive
            try:
                remote = upload_archive(destination)
            except Exception as exc:
                state['last_local_archive'] = destination.name
                raise BackupError('Локальная копия сохранена, но внешняя копия S3 не подтверждена. Проверьте доступ к хранилищу.') from exc
            if remote:
                state['remote'] = remote
            state.update(running=False, last_success=timezone.now().isoformat(), next_due=next_due(timezone.now()),
                         last_archive=destination.name, media_files=len(manifest['files']), error=None)
            write_json(root() / 'status.json', state)
            for old in sorted(root().glob('btbs-*.lmsbak'), key=lambda p: p.stat().st_mtime_ns, reverse=True)[settings.LMS_BACKUP_KEEP:]:
                old.unlink()
            return destination
        except Exception as exc:
            partial.unlink(missing_ok=True)
            state.update(running=False, error=str(exc) if isinstance(exc, BackupError) else 'Не удалось создать резервную копию. Проверьте PostgreSQL, S3 и свободное место.')
            write_json(root() / 'status.json', state)
            raise BackupError(state['error']) from exc


def restore_backup(archive_path, database, media_root):
    """Always restore to a new isolated database and directory; never overwrite."""
    import re
    import psycopg
    from psycopg import sql
    if not re.fullmatch(r'lms_restore_[a-z0-9_]{1,45}', database) or database == settings.DATABASES['default']['NAME']:
        raise BackupError('Для восстановления укажите новое имя базы lms_restore_…')
    media_root = Path(media_root).resolve()
    if media_root.exists():
        raise BackupError('Каталог восстановления уже существует. Выберите новый пустой путь.')
    media_root.parent.mkdir(parents=True, exist_ok=True)
    from .private_files import restrict
    env = pg_environment()
    connect = dict(host=env['PGHOST'], port=env['PGPORT'], user=env['PGUSER'], password=env['PGPASSWORD'], connect_timeout=10)
    with tempfile.TemporaryDirectory(prefix='.restoring-', dir=media_root.parent) as temporary:
        temp = Path(temporary)
        restrict(temp, directory=True)
        package, dump, staged_media = temp / 'backup.zip', temp / 'database.dump', temp / 'media'
        decrypt(archive_path, package, key_bytes())
        try:
            with zipfile.ZipFile(package) as archive:
                manifest = json.loads(archive.read('manifest.json'))
                if manifest.get('version') != 1:
                    raise BackupError('Неподдерживаемая версия резервной копии')
                with archive.open('database.dump') as incoming, dump.open('xb') as outgoing:
                    shutil.copyfileobj(incoming, outgoing, CHUNK)
                if digest(dump) != manifest['database_sha256']:
                    raise BackupError('Контрольная сумма базы не совпадает')
                staged_media.mkdir()
                converted = set()
                for item in manifest['files']:
                    name = safe_media_name(item['name'])
                    local_name = safe_media_name(name[4:] if name.startswith('_s3/') else name)
                    if local_name in converted:
                        raise BackupError('Конфликт имён файлов при восстановлении')
                    converted.add(local_name)
                    target = staged_media / local_name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open('media/' + name) as incoming, target.open('xb') as outgoing:
                        shutil.copyfileobj(incoming, outgoing, CHUNK)
                    if target.stat().st_size != item['bytes'] or digest(target) != item['sha256']:
                        raise BackupError('Контрольная сумма вложения не совпадает')
        except (KeyError, ValueError, zipfile.BadZipFile) as exc:
            raise BackupError('Неверный состав резервной копии') from exc
        pg_run('pg_restore', ['--list', str(dump)])
        with psycopg.connect(dbname='postgres', autocommit=True, **connect) as admin:
            if admin.execute('SELECT 1 FROM pg_database WHERE datname=%s', (database,)).fetchone():
                raise BackupError('База восстановления уже существует. Её данные не изменены.')
            admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(database)))
        # A failure leaves only the newly created database for diagnosis; no existing DB is touched.
        pg_run('pg_restore', ['--exit-on-error', '--single-transaction', '--no-owner', '--no-acl', '--dbname=' + database, str(dump)], database=database)
        with psycopg.connect(dbname=database, **connect) as restored:
            expected_tables = set(critical_counts())
            if set(manifest['counts']) != expected_tables:
                raise BackupError('Список проверяемых таблиц не совпадает')
            for table, expected in manifest['counts'].items():
                count = restored.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier(table))).fetchone()[0]
                if count != expected:
                    raise BackupError('Количество восстановленных записей не совпадает')
            for table in ['learning_lessonmaterial', 'courses_courseimage', 'assessment_submission']:
                restored.execute(sql.SQL("UPDATE {} SET file=substring(file from 5) WHERE left(file,4)='_s3/'").format(sql.Identifier(table)))
            restored.execute('DELETE FROM django_session')
            restored.execute('DELETE FROM accounts_passwordresetdelivery')
            restored.execute('DELETE FROM accounts_recoverythrottle')
            restored.execute("DELETE FROM learning_mediaupload WHERE state='pending'")
            restored.execute('DELETE FROM learning_storagedeletion')
            restored.execute("UPDATE analytics_sessionrecord SET ended_at=COALESCE(ended_at,CURRENT_TIMESTAMP), end_reason='backup_restore'")
        shutil.move(str(staged_media), str(media_root))
        restrict(media_root, directory=True)
        result = {'checked_at': timezone.now().isoformat(), 'archive': Path(archive_path).name,
                  'database': database, 'media_files': len(manifest['files']), 'counts': manifest['counts'], 'ok': True}
        write_json(root() / 'restore-check.json', result)
        return result
