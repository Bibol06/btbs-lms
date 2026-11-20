from accounts.identity import display_name, role_label
from django.db.models import Exists, OuterRef, Q, Value
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from common import api, authenticated, body, text, boolean, ApiError
from .access import can_manage_course, is_enrolled, is_platform_admin, can_teach
from .models import Course, Enrollment, CourseMember, default_run
from .image_views import validate_description_images


def course_queryset(user):
    qs = Course.objects.select_related('teacher')
    if user.is_authenticated:
        from .models import CourseRun
        qs = qs.annotate(enrolled=Exists(Enrollment.objects.filter(course_id=OuterRef('pk'), student=user, status__in=['active', 'completed'])),
            _team_editor=Exists(CourseMember.objects.filter(course_id=OuterRef('pk'), user=user)),
            _run_teacher=Exists(CourseRun.objects.filter(course_id=OuterRef('pk'), teachers=user)),
            _permission_user_id=Value(user.pk))
    return qs


def serialize_course(course, user):
    manage = can_manage_course(user, course)
    count = getattr(course, 'all_lessons' if manage else 'public_lessons', None)
    if count is None:
        count = course.lessons.count() if manage else course.lessons.filter(is_published=True).count()
    return {
        'id': course.id, 'title': course.title, 'description': course.description,
        'content_language': course.content_language, 'content_translation': course.content_translation,
        'teacher': (display_name(course.teacher)) if course.teacher else None,
        'teacher_id': course.teacher_id, 'teacher_role_label': role_label(course.teacher, teaching=True),
        'is_published': course.is_published,
        'can_edit_content': manage,
        'is_enrolled': bool(course.enrolled) if hasattr(course, 'enrolled') else is_enrolled(user, course),
        'can_manage': manage or bool(user.is_authenticated and (course._run_teacher if getattr(course, '_permission_user_id', None) == user.pk else course.runs.filter(teachers=user).exists())), 'lessons_count': count,
    }


@require_GET
@ensure_csrf_cookie
@api
def courses_list(request):
    qs = course_queryset(request.user)
    if not is_platform_admin(request.user):
        scope = Q(is_published=True)
        if request.user.is_authenticated:
            scope |= Q(teacher=request.user) | Q(team__user=request.user) | Q(runs__teachers=request.user)
        qs = qs.filter(scope).distinct()
    from .catalog_cache import attach_counts
    result = [serialize_course(c, request.user) for c in attach_counts(list(qs.order_by('-created_at', '-id')))]
    attach_catalog_progress(result, request.user)
    return JsonResponse({'courses': result, 'total': len(result)})


def attach_catalog_progress(rows, user):
    """Percent done for the learner's own enrolled courses, computed in one batch (catalog cards)."""
    enrolled = [row['id'] for row in rows if row['is_enrolled'] and not row['can_manage']]
    if not user.is_authenticated or not enrolled:
        return
    from learning.services import course_progress_many
    latest = {}
    for enrollment in Enrollment.objects.filter(student=user, course_id__in=enrolled, status__in=['active', 'completed']).order_by('id'):
        latest[enrollment.course_id] = enrollment
    progress = course_progress_many(list(latest.values()))
    for row in rows:
        enrollment = latest.get(row['id'])
        if enrollment:
            row['progress'] = progress[enrollment.id]['percent']
            row['progress_run_id'] = enrollment.run_id


@require_POST
@api
def enroll_course(request, course_id):
    authenticated(request)
    course = get_object_or_404(Course, pk=course_id)
    if can_manage_course(request.user, course):
        return JsonResponse({'message': 'У вас уже есть доступ', 'enrolled': True, 'course_id': course.id})
    if not course.is_published:
        raise ApiError('Курс ещё не опубликован', 403)
    run = default_run(course)
    if not run.is_open:
        raise ApiError('Запись на курс закрыта', 403)
    enrollment, _ = Enrollment.objects.get_or_create(student=request.user, course=course, run=run)
    if enrollment.status == 'removed':
        raise ApiError('Доступ к курсу отозван. Обратитесь к преподавателю.', 403)
    if enrollment.status == 'archived':
        enrollment.status = 'active'
        enrollment.save(update_fields=['status'])
    return JsonResponse({'message': 'Вы записаны на курс', 'enrolled': True, 'course_id': course.id})


@require_http_methods(['GET', 'POST'])
@api
def teacher_courses(request):
    authenticated(request)
    if not can_teach(request.user):
        raise ApiError('Доступ только для преподавателей', 403)
    if request.method == 'GET':
        qs = course_queryset(request.user)
        if not is_platform_admin(request.user):
            qs = qs.filter(Q(teacher=request.user) | Q(team__user=request.user) | Q(runs__teachers=request.user)).distinct()
        from .catalog_cache import attach_counts
        result = [serialize_course(c, request.user) for c in attach_counts(list(qs.order_by('-id')))]
        return JsonResponse({'courses': result, 'total': len(result)})
    data = body(request)
    language, translation_mode = course_language_settings(data)
    description = text(data, 'description', 10000)
    validate_description_images(description)
    course = Course.objects.create(
        title=text(data, 'title', 200, required=True),
        description=description,
        teacher=request.user,
        content_language=language, content_translation=translation_mode,
    )
    CourseMember.objects.get_or_create(course=course, user=request.user, defaults={'role': 'owner'})
    default_run(course)
    return JsonResponse({'message': 'Курс создан', 'course': serialize_course(course, request.user)}, status=201)


def course_language_settings(data, course=None):
    language = data.get('content_language', course.content_language if course else 'ru')
    mode = data.get('content_translation', course.content_translation if course else 'original')
    if not isinstance(language, str) or language not in {'ru', 'kk', 'en', 'other'}:
        raise ApiError('Выберите язык материалов курса')
    if not isinstance(mode, str) or mode not in {'original', 'localized'}:
        raise ApiError('Выберите режим перевода курса')
    return language, mode


@require_http_methods(['GET', 'PATCH'])
@api
def edit_teacher_course(request, course_id):
    authenticated(request)
    course = get_object_or_404(Course, pk=course_id)
    if not can_manage_course(request.user, course):
        raise ApiError('Нет прав на изменение курса', 403)
    if request.method == 'GET':
        return JsonResponse({'course': serialize_course(course, request.user)})
    data = body(request)
    course.content_language, course.content_translation = course_language_settings(data, course)
    course.title = text(data, 'title', 200, required=True, default=course.title)
    course.description = text(data, 'description', 10000, default=course.description)
    if 'description' in data:
        validate_description_images(course.description, course)
    course.is_published = boolean(data, 'is_published', course.is_published)
    course.save(update_fields=['title', 'description', 'is_published', 'content_language', 'content_translation'])
    return JsonResponse({'message': 'Курс обновлён', 'course': serialize_course(course, request.user)})
