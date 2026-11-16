from django.utils import timezone
from django.shortcuts import get_object_or_404
from common import ApiError, authenticated


def is_platform_admin(user):
    from accounts.permissions import is_learning_admin
    return is_learning_admin(user)


def can_teach(user):
    return bool(user.is_authenticated and user.is_active and (user.role == 'teacher' or is_platform_admin(user)
        or user.courses_taught.exists() or user.course_memberships.exists() or user.teaching_runs.exists()))


def can_manage_course(user, course):
    if not user.is_authenticated or not user.is_active:
        return False
    return is_platform_admin(user) or course.teacher_id == user.id or (course._team_editor if getattr(course, '_permission_user_id', None) == user.pk else course.team.filter(user=user).exists())


def can_manage_run(user, run):
    return can_manage_course(user, run.course) or bool(user.is_authenticated and user.is_active and run.teachers.filter(pk=user.pk).exists())


def is_enrolled(user, course, run=None):
    if not user.is_authenticated or not user.is_active:
        return False
    qs = course.enrollments.filter(student=user, status__in=['active', 'completed'])
    return (qs.filter(run=run) if run else qs).exists()


def can_access_full_content(user, course):
    return can_manage_course(user, course) or (course.is_published and is_enrolled(user, course)) or bool(user.is_authenticated and user.is_active and course.runs.filter(teachers=user).exists())


def resolve_run(request, course):
    from .models import CourseRun, default_run
    value = request.GET.get('run_id')
    if not value:
        return default_run(course)
    try:
        value = int(value)
    except (ValueError, TypeError):
        raise ApiError('Неверный запуск курса')
    return get_object_or_404(CourseRun.objects.select_related('course'), pk=value, course=course)


def require_run(request, run, manage=False):
    authenticated(request)
    manager = can_manage_run(request.user, run)
    if manage:
        if not manager:
            raise ApiError('Нет доступа к управлению этой группой', 403)
        return
    if manager:
        return
    if not run.course.is_published or not is_enrolled(request.user, run.course, run):
        raise ApiError('Нет доступа к этому прохождению курса', 403)


def require_learning_enrollment(request, run, lock=False, allow_after_end=False):
    from .models import Enrollment
    require_run(request, run)
    qs = Enrollment.objects.select_for_update() if lock else Enrollment.objects
    enrollment = qs.filter(run=run, student=request.user, status__in=['active', 'completed']).first()
    if enrollment is None:
        raise ApiError('Запишитесь на этот запуск курса для выполнения заданий', 403)
    if run.starts_at and timezone.now() < run.starts_at:
        raise ApiError('Обучение ещё не началось', 403)
    if not allow_after_end and run.ends_at and timezone.now() >= run.ends_at:
        raise ApiError('Срок обучения в группе завершён', 403)
    return enrollment
