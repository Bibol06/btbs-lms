from django.db import transaction
from django.db.models import Q
from .models import Event, Notification, NotificationPreference, AuditEvent


def audit(actor, course, action, context=None):
    AuditEvent.objects.create(actor=actor, course=course, action=action, context=context or {})


def teacher_ids(run):
    ids = set(run.teachers.filter(is_active=True).values_list('id', flat=True))
    ids.update(run.course.team.filter(user__is_active=True).values_list('user_id', flat=True))
    if run.course.teacher_id and run.course.teacher.is_active:
        ids.add(run.course.teacher_id)
    return ids


def notify(key, kind, course, recipients, title, target, run=None):
    """Persist source event and all in-app deliveries atomically and idempotently."""
    with transaction.atomic():
        event, created = Event.objects.get_or_create(key=key, defaults={'kind': kind, 'course': course, 'run': run, 'title': title, 'target': target})
        if not created:
            return event
        muted = set(p.user_id for p in NotificationPreference.objects.filter(course=course, user_id__in=recipients) if kind in p.muted_kinds)
        Notification.objects.bulk_create([Notification(event=event, recipient_id=user_id) for user_id in set(recipients) - muted], ignore_conflicts=True)
        return event


def course_target(course, run=None, tab='lessons', lesson_id=None):
    url = f'/#course={course.id}&tab={tab}'
    if run:
        url += f'&run={run.id}'
    if lesson_id:
        url += f'&lesson={lesson_id}'
    return url


def notify_published_step(step):
    lesson = step.lesson
    course = lesson.course
    if not (course.is_published and lesson.is_published and step.is_published):
        return
    if lesson.module_id and not lesson.module.is_published:
        return
    recipients = set(course.enrollments.filter(status__in=['active', 'completed'], student__is_active=True).values_list('student_id', flat=True))
    notify(f'step-published:{step.id}', 'material', course, recipients, 'Добавлен новый учебный шаг', course_target(course, lesson_id=lesson.id))
