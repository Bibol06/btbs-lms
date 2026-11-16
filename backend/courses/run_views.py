from accounts.identity import display_name, role_label, identity_data
import secrets
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods

from common import api, authenticated, body, text, boolean, date, ApiError
from .access import can_manage_course, can_manage_run, require_run
from .models import Course, CourseRun, CourseMember, Enrollment, CourseBookmark, default_run


def run_data(run, user):
    manage = can_manage_run(user, run)
    enrollment = run.enrollments.filter(student=user).first() if user.is_authenticated else None
    return {'id': run.id, 'title': run.title, 'kind': run.kind, 'release_mode': run.release_mode, 'starts_at': run.starts_at,
            'ends_at': run.ends_at, 'is_open': run.is_open, 'can_manage': manage,
            'join_code': run.join_code if manage else '', 'enrollment_id': enrollment.id if enrollment else None,
            'enrollment_status': enrollment.status if enrollment else None,
            'teachers': [identity_data(u, teaching=True) for u in run.teachers.all()] if manage else []}


@require_http_methods(['GET', 'POST'])
@api
def runs(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if not course.is_published and not can_manage_course(request.user, course) and not (request.user.is_authenticated and course.runs.filter(teachers=request.user).exists()):
        raise ApiError('Курс не найден', 404)
    default_run(course)
    if request.method == 'POST':
        authenticated(request)
        if not can_manage_course(request.user, course):
            raise ApiError('Нет прав на создание группы', 403)
        data = body(request)
        starts, ends = date(data, 'starts_at'), date(data, 'ends_at')
        if starts and ends and ends <= starts:
            raise ApiError('Окончание должно быть позже начала')
        run = CourseRun.objects.create(course=course, kind='cohort', title=text(data, 'title', 200, required=True),
            starts_at=starts, ends_at=ends, join_code=secrets.token_urlsafe(16))
        return JsonResponse({'run': run_data(run, request.user)}, status=201)
    qs = course.runs.all()
    if not can_manage_course(request.user, course):
        scope = Q(kind='self_paced')
        if request.user.is_authenticated:
            scope |= Q(enrollments__student=request.user) | Q(teachers=request.user)
        qs = qs.filter(scope).distinct()
    return JsonResponse({'runs': [run_data(r, request.user) for r in qs.order_by('id')], 'can_edit_content': can_manage_course(request.user, course)})


@require_http_methods(['GET', 'PATCH'])
@api
def run_detail(request, run_id):
    run = get_object_or_404(CourseRun.objects.select_related('course'), pk=run_id)
    require_run(request, run, manage=True)
    if request.method == 'PATCH':
        data = body(request)
        run.title = text(data, 'title', 200, True, run.title)
        run.is_open = boolean(data, 'is_open', run.is_open)
        starts = date(data, 'starts_at') if 'starts_at' in data else run.starts_at
        ends = date(data, 'ends_at') if 'ends_at' in data else run.ends_at
        if starts and ends and ends <= starts:
            raise ApiError('Окончание должно быть позже начала')
        with transaction.atomic():
            if run.starts_at != starts and run.checkpoints.filter(quiz__attempts__enrollment__run=run).exists():
                raise ApiError('Начало группы нельзя переносить после контрольных попыток')
            run.starts_at, run.ends_at = starts, ends
            if starts and run.module_releases.filter(due_at__lte=starts).exists():
                raise ApiError('Дедлайн модуля должен быть позже открытия и начала обучения')
            if ends and run.module_releases.filter(due_at__gt=ends).exists():
                raise ApiError('Дедлайн модуля должен быть не позже окончания обучения')
            from .pacing import checkpoint_dates
            for check in run.checkpoints.all():
                check.run = run
                opens, closes = checkpoint_dates(check)
                if not opens or not closes or closes <= opens or starts and opens < starts or ends and closes > ends:
                    raise ApiError('Окно теста должно находиться в пределах обучения группы')
            run.save()
            from .pacing import sync_checkpoint_schedules
            sync_checkpoint_schedules(run)
            from communication.services import audit
            audit(request.user, run.course, 'run.updated', {'run_id': run.id})
    return JsonResponse({'run': run_data(run, request.user), 'students': [{'id': e.id, 'student__username': e.student.username, 'student': display_name(e.student), 'role_label': role_label(e.student), 'status': e.status} for e in run.enrollments.select_related('student')]})


@require_POST
@api
def run_students(request, run_id):
    run = get_object_or_404(CourseRun.objects.select_related('course'), pk=run_id)
    require_run(request, run, manage=True)
    data = body(request)
    user = get_object_or_404(get_user_model(), username=text(data, 'username', 150, True), is_active=True)
    enrollment, created = Enrollment.objects.get_or_create(course=run.course, run=run, student=user)
    if enrollment.status in ['archived', 'removed']:
        enrollment.status = 'active'
        enrollment.save(update_fields=['status'])
    return JsonResponse({'id': enrollment.id, 'message': 'Студент добавлен' if created else 'Студент уже записан'})


@require_http_methods(['GET', 'POST', 'DELETE'])
@api
def team(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    authenticated(request)
    if not can_manage_course(request.user, course):
        raise ApiError('Нет прав на команду курса', 403)
    if request.method != 'GET':
        # Editors cannot grant further access; only the owner/platform admin can.
        from .access import is_platform_admin
        if not (is_platform_admin(request.user) or course.teacher_id == request.user.id or course.team.filter(user=request.user, role='owner').exists()):
            raise ApiError('Назначать преподавателей может владелец курса', 403)
        data = body(request)
        user = get_object_or_404(get_user_model(), username=text(data, 'username', 150, True), is_active=True)
        run_id = data.get('run_id')
        with transaction.atomic():
            if run_id:
                run = get_object_or_404(CourseRun, pk=run_id, course=course)
                if request.method == 'DELETE':
                    run.teachers.remove(user)
                else:
                    run.teachers.add(user)
            elif request.method == 'DELETE':
                if course.teacher_id == user.id or course.team.filter(user=user, role='owner').exists():
                    raise ApiError('Владельца нельзя удалить этим действием')
                course.team.filter(user=user).delete()
            else:
                CourseMember.objects.get_or_create(course=course, user=user, defaults={'role': 'editor'})
            from communication.services import audit
            audit(request.user, course, 'team.changed', {'user_id': user.id, 'run_id': run_id, 'action': request.method})
    return JsonResponse({'team': [{'user__username': m.user.username, 'display_name': display_name(m.user), 'role_label': role_label(m.user, teaching=True), 'role': m.role} for m in course.team.select_related('user')], 'owner': display_name(course.teacher) if course.teacher else None})


@require_POST
@api
def join_group(request):
    authenticated(request)
    run = get_object_or_404(CourseRun, join_code=text(body(request), 'code', 64, True), kind='cohort', is_open=True, course__is_published=True)
    if run.ends_at and timezone.now() >= run.ends_at:
        raise ApiError('Группа уже завершила обучение')
    enrollment, _ = Enrollment.objects.get_or_create(course=run.course, run=run, student=request.user)
    if enrollment.status == 'removed':
        raise ApiError('Доступ к группе отозван. Обратитесь к преподавателю.', 403)
    if enrollment.status == 'archived':
        enrollment.status = 'active'
        enrollment.save(update_fields=['status'])
    return JsonResponse({'course_id': run.course_id, 'run_id': run.id, 'enrollment_id': enrollment.id})


@require_http_methods(['PATCH'])
@api
def enrollment_status(request, enrollment_id):
    authenticated(request)
    enrollment = get_object_or_404(Enrollment.objects.select_related('run__course'), pk=enrollment_id)
    state = body(request).get('status')
    manager = can_manage_run(request.user, enrollment.run)
    if enrollment.student_id != request.user.id:
        if not manager:
            raise ApiError('Нет доступа к этой записи', 403)
        if state not in ['active', 'removed']:
            raise ApiError('Можно восстановить или отозвать доступ')
    else:
        if enrollment.status == 'removed' and not manager:
            raise ApiError('Доступ может восстановить преподаватель', 403)
        if state not in (['active', 'removed', 'archived'] if manager else ['active', 'archived']):
            raise ApiError('Неверное состояние записи')
    with transaction.atomic():
        enrollment.status = state
        enrollment.save(update_fields=['status'])
        if manager:
            from communication.services import audit
            audit(request.user, enrollment.course, 'enrollment.status_changed', {'enrollment_id': enrollment.id, 'status': state})
    return JsonResponse({'status': state})


@require_http_methods(['POST', 'DELETE'])
@api
def bookmark(request, course_id):
    authenticated(request)
    course = get_object_or_404(Course, pk=course_id, is_published=True)
    kind = body(request).get('kind')
    if kind not in ['favorite', 'wishlist']:
        raise ApiError('Неверный список')
    if request.method == 'POST':
        CourseBookmark.objects.get_or_create(course=course, user=request.user, kind=kind)
    else:
        CourseBookmark.objects.filter(course=course, user=request.user, kind=kind).delete()
    return JsonResponse({'message': 'Список обновлён'})
