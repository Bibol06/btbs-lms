from accounts.identity import display_name, role_label
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods

from common import api, authenticated, body, text
from courses.access import can_teach
from courses.models import Course
from .permissions import access_data


def profile_data(user, own=False):
    taught = Course.objects.filter(Q(teacher=user) | Q(team__user=user) | Q(runs__teachers=user)).distinct()
    data = {
        **access_data(user),
        'id': user.id, 'username': user.username, 'first_name': user.first_name,
        'last_name': user.last_name, 'display_name': display_name(user),
        'role': 'admin' if user.is_superuser else user.role, 'can_teach': can_teach(user), 'role_label': role_label(user, teaching=can_teach(user)),
        'bio': user.bio, 'organization': user.organization, 'city': user.city,
        'joined_at': user.date_joined, 'is_own': own,
        'teaching_courses': list((taught if own else taught.filter(is_published=True)).order_by('id').values('id', 'title', 'is_published')),
    }
    if own:
        data['email'] = user.email
        data['preferred_language'] = user.preferred_language
        data['learning'] = {
            'active': user.enrollments.filter(status='active').count(),
            'completed': user.enrollments.filter(status='completed').count(),
        }
    return data


@require_http_methods(['GET', 'PATCH'])
@api
def my_profile(request):
    authenticated(request)
    if request.method == 'PATCH':
        values = body(request)
        fields = {'first_name': 150, 'last_name': 150, 'bio': 3000, 'organization': 200, 'city': 100}
        # Role, email, permissions and login are deliberately outside this edit form.
        for name, limit in fields.items():
            if name in values:
                setattr(request.user, name, text(values, name, limit))
        request.user.save(update_fields=list(fields))
    return JsonResponse(profile_data(request.user, own=True))


@require_GET
@api
def user_profile(request, user_id):
    authenticated(request)
    user = get_object_or_404(get_user_model(), pk=user_id, is_active=True)
    return JsonResponse(profile_data(user, own=user.id == request.user.id))


@require_http_methods(['GET', 'PATCH'])
@api
def preferences(request):
    authenticated(request)
    if request.method == 'PATCH':
        from common import ApiError
        values = body(request)
        language = values.get('language')
        if not isinstance(language, str) or language not in {'kk', 'ru', 'en'}:
            raise ApiError('Выберите казахский, русский или английский язык')
        request.user.preferred_language = language
        request.user.save(update_fields=['preferred_language'])
    return JsonResponse({'language': request.user.preferred_language})
