"""Public names and role captions, kept separate from authentication logins."""
from django.core.exceptions import ValidationError


def profile_names(data):
    names = {}
    for key in ('first_name', 'last_name'):
        value = data.get(key, '')
        if not isinstance(value, str) or len(value.strip()) > 150:
            raise ValidationError('Имя и фамилия должны быть текстом до 150 символов')
        names[key] = value.strip()
    return names


def display_name(user):
    if user is None:
        return 'Удалённый пользователь'
    return ' '.join(part.strip() for part in (user.last_name, user.first_name) if part.strip()) or user.username


def role_label(user, teaching=False):
    if user is None:
        return ''
    if user.is_superuser or user.role == 'admin':
        if not user.is_superuser and user.admin_scope == 'system':
            return 'Системный администратор'
        if not user.is_superuser and user.admin_scope == 'learning':
            return 'Администратор обучения'
        return 'Владелец платформы'
    if teaching or user.role == 'teacher':
        return 'Преподаватель'
    return 'Студент'


def identity_data(user, teaching=False):
    from .permissions import access_data
    return {'id': user.id, 'username': user.username, 'display_name': display_name(user),
            'role': 'admin' if user.is_superuser else user.role, 'role_label': role_label(user, teaching), **access_data(user)}
