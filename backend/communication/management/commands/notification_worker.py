import time
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone
from courses.models import Enrollment
from communication.services import notify, course_target


def remind_deadlines():
    from common import ApiError
    from learning.services import require_activity_visible
    from assessment.deadlines import submission_window
    from assessment.models import Submission
    from communication.services import teacher_ids
    now = timezone.now()
    for enrollment in Enrollment.objects.filter(status='active', course__is_published=True, student__is_active=True).select_related('course', 'run'):
        for assignment in enrollment.course.assignments.filter(is_published=True):
            try:
                require_activity_visible(enrollment.student, assignment, enrollment.run, 'assignment')
            except ApiError:
                continue
            latest = assignment.submissions.filter(enrollment=enrollment).first()
            if latest and latest.status in ['submitted', 'graded']:
                continue
            window = submission_window(assignment, enrollment, now=now)
            due = window['due_at']
            targets = [('due', due)]
            if window['closes_at'] and window['closes_at'] != due:
                targets.append(('closing', window['closes_at']))
            for kind, target in targets:
                if not target:
                    continue
                if target <= now:
                    stage, title = 'overdue', 'Срок сдачи пропущен' if kind == 'due' else 'Приём работ закрыт'
                elif target <= now + timedelta(hours=1):
                    stage, title = '1h', 'До закрытия приёма меньше часа' if kind == 'closing' else 'До сдачи задания меньше часа'
                elif target <= now + timedelta(hours=24):
                    stage, title = '24h', 'До закрытия приёма меньше суток' if kind == 'closing' else 'До сдачи задания осталось меньше суток'
                else:
                    continue
                notify(f'deadline:{assignment.id}:{enrollment.id}:{kind}:{target.isoformat()}:{stage}', 'deadline', enrollment.course,
                    {enrollment.student_id}, title, course_target(enrollment.course, enrollment.run, 'assignments'), enrollment.run)
    pending = Submission.objects.filter(status='submitted', review_due_at__lte=now+timedelta(hours=24)).select_related('assignment__course', 'enrollment__run')
    for s in pending:
        valid = teacher_ids(s.enrollment.run)
        recipients = {s.reviewer_id} if s.reviewer_id in valid else valid
        stage = 'overdue' if s.review_due_at <= now else 'soon'
        notify(f'review-deadline:{s.id}:{s.review_due_at.isoformat()}:{stage}:{",".join(map(str, sorted(recipients)))}', 'deadline', s.assignment.course,
               recipients, 'Проверка работы просрочена' if stage == 'overdue' else 'Приближается срок проверки работы',
               course_target(s.assignment.course, s.enrollment.run, 'assignments'), s.enrollment.run)


class Command(BaseCommand):
    help = 'Persist idempotent in-app deadline reminders; --once for a single pass'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        while True:
            try:
                close_old_connections()
                from assessment.quiz_services import finalize_due_attempts
                finalize_due_attempts()
                remind_deadlines()
            except Exception as exc:
                self.stderr.write(f'Notification worker: {type(exc).__name__}')
                if options['once']:
                    raise
            if options['once']:
                return
            time.sleep(30)
