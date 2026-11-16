"""Shared validation for locally uploaded lesson and course illustrations."""
import warnings
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from common import ApiError


def validate_image_upload(file):
    from learning.upload_views import valid_file_signature

    if not file:
        raise ApiError('Выберите изображение')
    extension = Path(file.name).suffix.lower()
    if extension not in {'.png', '.jpg', '.jpeg'}:
        raise ApiError('Для иллюстрации выберите PNG или JPEG')
    if not 0 < file.size <= 8 * 1024 * 1024:
        raise ApiError('Размер иллюстрации должен быть не больше 8 МБ')
    if not valid_file_signature(file, extension):
        raise ApiError('Содержимое файла не соответствует его формату')
    raw = file.read()
    file.seek(0)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw), formats=('PNG', 'JPEG')) as picture:
                if picture.width * picture.height > 16_000_000 or max(picture.size) > 12_000:
                    raise ApiError('Слишком большое разрешение изображения. Максимум 16 млн пикселей.')
                picture.verify()
            with Image.open(BytesIO(raw), formats=('PNG', 'JPEG')) as picture:
                picture.load()
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise ApiError('Слишком большое разрешение изображения. Максимум 16 млн пикселей.')
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise ApiError('Изображение повреждено или не поддерживается')
    return extension
