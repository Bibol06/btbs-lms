"""Encrypted archives only. Never upload the encryption key or delete remote copies."""
import hashlib
import re
from pathlib import Path
import boto3
from botocore.config import Config
from boto3.s3.transfer import TransferConfig
from django.conf import settings
from django.utils import timezone
from .backups import BackupError, CHUNK, MAGIC, digest


def client():
    return boto3.client('s3', region_name=settings.LMS_BACKUP_S3_REGION,
                        aws_access_key_id=settings.MEDIA_S3_ACCESS_KEY,
                        aws_secret_access_key=settings.MEDIA_S3_SECRET_KEY,
                        config=Config(connect_timeout=10, read_timeout=60, retries={'max_attempts': 3}))


def object_key(name):
    if not re.fullmatch(r'btbs-[0-9T]+-[a-f0-9]{8}\.lmsbak', name):
        raise BackupError('Некорректное имя резервной копии')
    return 'encrypted/' + name


def upload_archive(path):
    bucket = settings.LMS_BACKUP_S3_BUCKET
    if not bucket:
        return None
    path = Path(path)
    with path.open('rb') as stream:
        if stream.read(len(MAGIC)) != MAGIC:
            raise BackupError('Во внешнее хранилище разрешены только зашифрованные архивы')
    s3, key, sha = client(), object_key(path.name), digest(path)
    s3.upload_file(str(path), bucket, key, ExtraArgs={
        'ServerSideEncryption': 'AES256', 'ContentType': 'application/octet-stream',
        'Metadata': {'sha256': sha}}, Config=TransferConfig(max_concurrency=2))
    head = s3.head_object(Bucket=bucket, Key=key)
    if head['ContentLength'] != path.stat().st_size or head.get('Metadata', {}).get('sha256') != sha:
        raise BackupError('Проверка внешней резервной копии не пройдена')
    # Read back the exact version, not just user-defined checksum metadata.
    version = head.get('VersionId')
    args = {'Bucket': bucket, 'Key': key}
    if version: args['VersionId'] = version
    body = s3.get_object(**args)['Body']
    actual = hashlib.sha256()
    try:
        while chunk := body.read(CHUNK): actual.update(chunk)
    finally:
        body.close()
    if actual.hexdigest() != sha:
        raise BackupError('Контрольная сумма внешней резервной копии не совпадает')
    return {'bucket': bucket, 'key': key, 'version_id': version,
            'sha256': sha, 'bytes': head['ContentLength'], 'verified_at': timezone.now().isoformat()}


def download_archive(name, destination, version_id=None):
    target = Path(destination)
    if target.exists():
        raise BackupError('Файл назначения уже существует')
    args = {'Bucket': settings.LMS_BACKUP_S3_BUCKET, 'Key': object_key(name)}
    if version_id: args['VersionId'] = version_id
    response = client().get_object(**args)
    body, sha = response['Body'], hashlib.sha256()
    created = False
    try:
        with target.open('xb') as outgoing:
            created = True
            while chunk := body.read(CHUNK):
                outgoing.write(chunk); sha.update(chunk)
        if sha.hexdigest() != response.get('Metadata', {}).get('sha256'):
            raise BackupError('Контрольная сумма скачанного архива не совпадает')
        return target
    except Exception:
        if created: target.unlink(missing_ok=True)
        raise
    finally:
        body.close()
