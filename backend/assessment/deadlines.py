from datetime import timedelta

from django.utils import timezone
from common import ApiError, boolean, date, integer
from .models import ActivitySchedule, AssignmentExtension


def assignment_settings(assignment, run):
    return ActivitySchedule.objects.filter(run=run, assignment=assignment).first() or assignment


def deadline_values(data, current=None):
    due = date(data, 'due_at') if 'due_at' in data else getattr(current, 'due_at', None)
    cutoff = date(data, 'cutoff_at') if 'cutoff_at' in data else getattr(current, 'cutoff_at', None)
    late = boolean(data, 'allow_late', getattr(current, 'allow_late', False))
    if cutoff and due and cutoff < due:
        raise ApiError('Закрытие приёма не может быть раньше срока сдачи')
    return {'due_at': due, 'cutoff_at': cutoff, 'allow_late': late,
            'review_hours': integer(data, 'review_hours', 1, 720, getattr(current, 'review_hours', 48))}


def submission_window(assignment, enrollment, settings=None, now=None):
    now = now or timezone.now()
    settings = settings or assignment_settings(assignment, enrollment.run)
    personal = AssignmentExtension.objects.filter(assignment=assignment, enrollment=enrollment).first()
    due = personal.deadline_at if personal else settings.due_at
    cutoff = personal.deadline_at if personal else settings.cutoff_at if settings.allow_late else settings.due_at
    # An explicit personal extension can outlive the group's submission period.
    if not personal and enrollment.run.ends_at:
        cutoff = min(cutoff, enrollment.run.ends_at) if cutoff else enrollment.run.ends_at
        if due and cutoff < due:
            due = cutoff
    if enrollment.status not in ['active', 'completed']:
        phase = 'unavailable'
    elif enrollment.run.starts_at and now < enrollment.run.starts_at:
        phase = 'not_started'
    elif cutoff and now >= cutoff:
        phase = 'closed'
    elif due and now >= due:
        phase = 'late'
    else:
        phase = 'open'
    return {'due_at': due, 'closes_at': cutoff, 'allow_late': settings.allow_late and not personal,
            'source': 'personal' if personal else 'group' if isinstance(settings, ActivitySchedule) else 'course',
            'note': personal.reason if personal else '', 'phase': phase, 'can_submit': phase in ['open', 'late']}


def default_reviewer(run):
    from django.contrib.auth import get_user_model
    from communication.services import teacher_ids
    candidates = teacher_ids(run)
    group_teacher = run.teachers.filter(is_active=True).order_by('id').first()
    if group_teacher:
        return group_teacher
    if run.course.teacher_id in candidates:
        return run.course.teacher
    return get_user_model().objects.filter(id__in=candidates, is_active=True).order_by('id').first()


def review_state(submission, now=None):
    if submission.status != 'submitted':
        return submission.status
    now = now or timezone.now()
    if submission.review_due_at and submission.review_due_at <= now:
        return 'overdue'
    if submission.review_due_at and submission.review_due_at <= now + timedelta(hours=24):
        return 'soon'
    return 'pending'


def grant_extension(assignment, enrollment, actor, deadline_at, reason=''):
    if not deadline_at or deadline_at <= timezone.now():
        raise ApiError('Укажите новый срок в будущем')
    if enrollment.status not in ['active', 'completed']:
        raise ApiError('Нельзя продлить срок ученику с отозванным или архивным доступом')
    extension, _ = AssignmentExtension.objects.update_or_create(assignment=assignment, enrollment=enrollment,
        defaults={'deadline_at': deadline_at, 'reason': reason, 'granted_by': actor})
    from communication.services import audit, notify, course_target
    audit(actor, assignment.course, 'assignment.deadline_extended', {'assignment_id': assignment.id, 'enrollment_id': enrollment.id, 'deadline_at': deadline_at.isoformat(), 'reason': reason})
    notify(f'extension:{extension.id}:{extension.updated_at.isoformat()}', 'deadline', assignment.course, {enrollment.student_id},
           'Назначен индивидуальный срок сдачи', course_target(assignment.course, enrollment.run, 'assignments'), enrollment.run)
    return extension
