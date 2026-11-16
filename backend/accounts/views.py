from accounts.identity import display_name, role_label, identity_data, profile_names

import json

from django.contrib.auth import authenticate, login, logout, get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.contrib.auth.validators import UnicodeUsernameValidator
from courses.access import can_teach
from .permissions import is_system_admin, access_data
from . import login_guard


@require_GET
@ensure_csrf_cookie
def csrf_view(request):
    return JsonResponse({"message": "CSRF cookie ready"})


@require_POST
def login_view(request):
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError()
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Неверный формат данных"}, status=400)

    username = data.get("username", "")
    password = data.get("password", "")

    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        return JsonResponse({'error': 'Введите логин и пароль'}, status=400)

    identifier = username.strip()
    if not identifier:
        return JsonResponse({'error': 'Введите логин и пароль'}, status=400)
    client_ip = request.META.get('REMOTE_ADDR', '')
    if login_guard.is_locked(identifier, client_ip):
        return JsonResponse({'error': login_guard.LOCKED_MESSAGE}, status=429)
    User = get_user_model()
    candidates = list(User.objects.filter(
        Q(username__iexact=identifier) | Q(email__iexact=identifier)
    ).values_list('username', flat=True)[:2])
    # Ambiguous identifiers must not select another person's account.
    if len(candidates) == 1:
        user = authenticate(request, username=candidates[0], password=password)
    else:
        User().set_password(password)
        user = None

    if user is None:
        login_guard.register_failure(identifier, client_ip)
        return JsonResponse(
            {"error": "Неверный логин или пароль"},
            status=401
        )

    login_guard.register_success(identifier, client_ip)
    login(request, user)

    return JsonResponse({
        "message": "Вход выполнен",
        **access_data(user),
        'id': user.id,
        'preferred_language': user.preferred_language,
        'display_name': display_name(user),
        "username": user.username,
        "role": 'admin' if user.is_superuser else user.role,
        'can_teach': can_teach(user), 'role_label': role_label(user, teaching=can_teach(user)),
    })


@require_POST
def register_view(request):
    # Публичная регистрация создаёт ТОЛЬКО студента, даже если клиент прислал role=admin.
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError()
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Неверный формат данных'}, status=400)

    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    try:
        names = profile_names(data)
    except ValidationError as exc:
        return JsonResponse({'error': ' '.join(exc.messages)}, status=400)
    if not all(isinstance(v, str) for v in (username, email, password)):
        return JsonResponse({'error': 'Заполните логин, email и пароль'}, status=400)

    username, email = username.strip(), email.strip()
    if not username or not email or not password:
        return JsonResponse({'error': 'Заполните все поля'}, status=400)
    if len(username) > 150 or len(email) > 254:
        return JsonResponse({'error': 'Слишком длинный логин или email'}, status=400)

    User = get_user_model()
    candidate = User(username=username, email=email, role='student', **names)
    try:
        UnicodeUsernameValidator()(username)
        validate_email(email)
        validate_password(password, user=candidate)
    except ValidationError as exc:
        return JsonResponse({'error': ' '.join(exc.messages)}, status=400)

    if User.objects.filter(username__iexact=username).exists():
        return JsonResponse({'error': 'Этот логин занят'}, status=409)
    if User.objects.filter(email__iexact=email).exists():
        return JsonResponse({'error': 'Этот email уже используется'}, status=409)

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                role='student',
                is_staff=False,
                is_superuser=False,
                **names,
            )
    except IntegrityError:
        return JsonResponse({'error': 'Пользователь уже существует'}, status=409)

    login(request, user)
    return JsonResponse({
        'message': 'Регистрация успешна',
        'id': user.id,
        'display_name': display_name(user), 'role_label': role_label(user),
        'username': user.username,
        'role': user.role,
    }, status=201)


@require_GET
def me_view(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Не авторизован"},
            status=401
        )

    teaching = can_teach(request.user)
    return JsonResponse({
        "username": request.user.username,
        **access_data(request.user),
        'id': request.user.id,
        'preferred_language': request.user.preferred_language,
        'display_name': display_name(request.user),
        "role": 'admin' if request.user.is_superuser else request.user.role,
        'can_teach': teaching, 'role_label': role_label(request.user, teaching=teaching),
    })


@require_POST
def logout_view(request):
    logout(request)
    return JsonResponse({"message": "Выход выполнен"})


@require_GET
def users_view(request):

    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Вы не авторизованы"},
            status=401
        )

    if not is_system_admin(request.user):
        return JsonResponse(
            {"error": "Доступ запрещён"},
            status=403
        )

    User = get_user_model()

    users = [{**identity_data(u), 'email': u.email, 'is_active': u.is_active} for u in User.objects.order_by('id')]

    return JsonResponse({
        "users": users,
        "total": len(users)
    })


@require_POST
def create_student_view(request):

    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Необходима авторизация"},
            status=401
        )

    if not is_system_admin(request.user):
        return JsonResponse(
            {"error": "Доступ запрещён"},
            status=403
        )

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "Неверный формат данных"},
            status=400
        )

    if not isinstance(data, dict):
        return JsonResponse(
            {"error": "Неверный формат данных"},
            status=400
        )

    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    try:
        names = profile_names(data)
    except ValidationError as exc:
        return JsonResponse({'error': ' '.join(exc.messages)}, status=400)

    if not all(isinstance(x, str) for x in (username, email, password)):
        return JsonResponse(
            {"error": "Заполните все поля"},
            status=400
        )

    username = username.strip()
    email = email.strip()

    if not username or not email or not password:
        return JsonResponse(
            {"error": "Заполните все поля"},
            status=400
        )

    User = get_user_model()

    if len(username) > 150 or len(email) > 254:
        return JsonResponse(
            {"error": "Слишком длинный логин"},
            status=400
        )

    if User.objects.filter(username__iexact=username).exists():
        return JsonResponse(
            {"error": "Такой логин уже существует"},
            status=409
        )

    if User.objects.filter(email__iexact=email).exists():
        return JsonResponse({'error': 'Этот email уже используется'}, status=409)

    try:
        UnicodeUsernameValidator()(username)
        validate_email(email)
        validate_password(password, user=User(username=username, email=email, **names))
    except ValidationError as error:
        return JsonResponse(
            {"error": " ".join(error.messages)},
            status=400
        )

    try:
        with transaction.atomic():
            user = User.objects.create_user(username=username, email=email, password=password, role='student', **names)
    except IntegrityError:
        return JsonResponse({'error': 'Логин или email уже используется'}, status=409)

    return JsonResponse({
        "message": "Студент успешно создан",
        "user": {
            "id": user.id,
            "display_name": display_name(user),
            "role_label": role_label(user),
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active
        }
    }, status=201)


@require_http_methods(["DELETE"])
def delete_student_view(request, user_id):

    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Необходима авторизация"},
            status=401
        )

    if not is_system_admin(request.user):
        return JsonResponse(
            {"error": "Доступ запрещён"},
            status=403
        )

    User = get_user_model()

    student = User.objects.filter(
        id=user_id,
        role='student',
        is_staff=False,
        is_superuser=False
    ).first()

    if student is None:
        return JsonResponse(
            {"error": "Студент не найден или удаление запрещено"},
            status=404
        )

    student.delete()

    return JsonResponse({
        "message": "Студент успешно удалён"
    })
