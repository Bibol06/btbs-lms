from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from common import api, authenticated, body, ApiError
from .permissions import is_full_admin
from .identity import identity_data
from .models import SystemAuditEvent


@require_POST
@api
def change_responsibility(request, user_id):
    authenticated(request)
    if not is_full_admin(request.user):
        raise ApiError('Назначать административные полномочия может только администратор с полным доступом', 403)
    responsibility = body(request).get('responsibility')
    if responsibility not in ['student', 'teacher', 'system', 'learning']:
        raise ApiError('Выберите область ответственности')
    with transaction.atomic():
        target = get_object_or_404(get_user_model().objects.select_for_update(), pk=user_id)
        if target.id == request.user.id or target.is_superuser or target.role == 'admin' and target.admin_scope == 'full':
            raise ApiError('Полный доступ владельца не меняется через эту форму')
        previous = {'role': target.role, 'admin_scope': target.admin_scope}
        target.role = 'admin' if responsibility in ['system', 'learning'] else responsibility
        target.admin_scope = responsibility if target.role == 'admin' else 'full'
        target.save(update_fields=['role', 'admin_scope'])
        SystemAuditEvent.objects.create(actor=request.user, target=target, action='account.responsibility_changed',
            details={'before': previous, 'after': {'role': target.role, 'admin_scope': target.admin_scope}})
    return JsonResponse({'user': identity_data(target)})
