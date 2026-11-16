"""Shared JSON validation and consistent API errors."""
import json
from functools import wraps

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.db.models.deletion import ProtectedError, RestrictedError


class ApiError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def api(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except ApiError as exc:
            return JsonResponse({'error': exc.message}, status=exc.status)
        except Http404:
            return JsonResponse({'error': 'Объект не найден или недоступен'}, status=404)
        except PermissionDenied:
            return JsonResponse({'error': 'Нет прав доступа'}, status=403)
        except (ProtectedError, RestrictedError):
            return JsonResponse({'error': 'Этот объект используется в учебных шагах. Сначала удалите ссылки или снимите его с публикации.'}, status=409)
        except ValidationError as exc:
            return JsonResponse({'error': ' '.join(exc.messages)}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Неверный формат значения'}, status=400)
    return wrapped


def body(request):
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        raise ApiError('Ожидается JSON-объект')
    if not isinstance(data, dict):
        raise ApiError('Ожидается JSON-объект')
    return data


def text(data, key, limit, required=False, default=''):
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ApiError(f'Поле {key} должно быть текстом')
    value = value.strip()
    if len(value) > limit or (required and not value):
        raise ApiError(f'Поле {key}: от {1 if required else 0} до {limit} символов')
    return value


def integer(data, key, minimum, maximum, default=None):
    value = data.get(key, default)
    if type(value) is not int or not minimum <= value <= maximum:
        raise ApiError(f'Поле {key}: целое число от {minimum} до {maximum}')
    return value


def query_integer(request, key, minimum, maximum, default=None):
    """Query strings are text; JSON integers remain strictly typed by integer()."""
    value = request.GET.get(key)
    if value is None:
        return integer({key: default}, key, minimum, maximum)
    try:
        value = int(value)
    except (ValueError, TypeError):
        raise ApiError(f'Поле {key}: укажите целое число')
    return integer({key: value}, key, minimum, maximum)


def raw_text(data, key, limit, required=False):
    value = data.get(key, '')
    if not isinstance(value, str) or len(value) > limit or '\x00' in value or (required and not value.strip()):
        raise ApiError(f'Поле {key}: некорректный текст или превышен лимит {limit}')
    return value


def boolean(data, key, default=False):
    value = data.get(key, default)
    if type(value) is not bool:
        raise ApiError(f'Поле {key} должно быть true или false')
    return value


def date(data, key):
    value = data.get(key)
    if value in (None, ''):
        return None
    if not isinstance(value, str):
        raise ApiError('Некорректная дата')
    try:
        result = parse_datetime(value)
    except ValueError:
        result = None
    if result is None or timezone.is_naive(result):
        raise ApiError('Укажите дату со временем и часовым поясом')
    return result


def authenticated(request):
    if not request.user.is_authenticated:
        raise ApiError('Необходима авторизация', 401)
    if not request.user.is_active:
        raise ApiError('Аккаунт отключён', 403)
