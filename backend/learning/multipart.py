"""Owner-scoped, resumable S3 uploads. No video bytes cross the Django process."""
import math
from botocore.exceptions import ClientError
from django.conf import settings
from common import ApiError

PART_SIZE = 8 * 1024 * 1024


def params(upload):
    return {'Bucket': settings.MEDIA_S3_BUCKET, 'Key': upload.staging_key, 'UploadId': upload.multipart_id}


def uploaded_parts(s3, upload):
    result = []
    for page in s3.get_paginator('list_parts').paginate(**params(upload)):
        result.extend(page.get('Parts', []))
    return result


def assemble(s3, upload):
    if not upload.multipart_id:
        return
    try:
        parts = sorted(uploaded_parts(s3, upload), key=lambda p: p['PartNumber'])
    except ClientError as exc:
        if exc.response['Error']['Code'] != 'NoSuchUpload':
            raise
        # A previous completion may have succeeded before its HTTP/DB response was lost.
        # The existing complete endpoint will validate the assembled object again.
        s3.head_object(Bucket=settings.MEDIA_S3_BUCKET, Key=upload.staging_key)
        return
    count = math.ceil(upload.size / upload.part_size)
    if [p['PartNumber'] for p in parts] != list(range(1, count + 1)):
        raise ApiError('Загружены не все части файла. Продолжите загрузку.')
    for p in parts:
        expected = min(upload.part_size, upload.size - (p['PartNumber']-1)*upload.part_size)
        if p['Size'] != expected:
            raise ApiError('Размер части файла не совпадает. Повторите загрузку.')
    s3.complete_multipart_upload(**params(upload), MultipartUpload={'Parts': [
        {'PartNumber': p['PartNumber'], 'ETag': p['ETag']} for p in parts]})


def abort_parts(s3, upload):
    if upload.multipart_id:
        try:
            s3.abort_multipart_upload(**params(upload))
        except ClientError as exc:
            if exc.response['Error']['Code'] != 'NoSuchUpload':
                raise
