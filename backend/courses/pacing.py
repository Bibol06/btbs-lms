"""Group-relative dates; no jobs or global course-date mutations are needed."""
from datetime import timedelta
from django.utils import timezone
from assessment.models import ActivitySchedule
from common import ApiError


def module_release(module, run):
    row = run._module_release_map.get(module.id) if hasattr(run, '_module_release_map') else run.module_releases.filter(module=module).first()
    if run.release_mode != 'weekly':
        return {'week': None, 'opens_at': row.opens_at if run.release_mode == 'dates' and row else module.opens_at,
                'due_at': row.due_at if row else None, 'scheduled': True}
    return {'week': row.week if row else None,
            'opens_at': (row.opens_at or run.starts_at + timedelta(weeks=row.week-1)) if row and run.starts_at else None,
            'due_at': row.due_at if row else None,
            'scheduled': bool(row and run.starts_at)}


def module_deadline_states(run, enrollments, now=None):
    """Soft deadlines never revoke access or change assessment/grade rules."""
    now = now or timezone.now()
    if not enrollments:
        return {}
    deadlines = run._deadline_rows if hasattr(run, '_deadline_rows') else list(run.module_releases.filter(due_at__isnull=False, module__is_published=True).select_related('module'))
    if not deadlines:
        return {}
    from learning.services import course_progress_many, visible_steps
    from assessment.models import Submission, LessonProgress
    from learning.models import Lesson
    progress = course_progress_many(enrollments)
    by_module = {row.module_id: [] for row in deadlines}
    for step in visible_steps(run.course).filter(required=True, lesson__module_id__in=by_module).select_related('lesson'):
        by_module[step.lesson.module_id].append(step)
    legacy = {row.module_id: [] for row in deadlines}
    for lesson in Lesson.objects.filter(course=run.course, is_published=True, module_id__in=by_module, steps__isnull=True):
        legacy[lesson.module_id].append(lesson.id)
    ids = [e.id for e in enrollments]
    latest = {}
    for answer in Submission.objects.filter(enrollment_id__in=ids).order_by('enrollment_id', 'assignment_id', '-submitted_at', '-id'):
        latest.setdefault((answer.enrollment_id, answer.assignment_id), answer.status)
    legacy_done = set(LessonProgress.objects.filter(enrollment_id__in=ids).values_list('enrollment_id', 'lesson_id'))
    result = {}
    for e in enrollments:
        for row in deadlines:
            steps = by_module[row.module_id]
            done = [s for s in steps if s.id in progress[e.id]['step_ids']]
            missing = [s for s in steps if s.id not in progress[e.id]['step_ids']]
            total = len(steps) + len(legacy[row.module_id])
            completed = len(done) + sum((e.id, lid) in legacy_done for lid in legacy[row.module_id])
            # Waiting for the teacher is distinct from an unfinished student task.
            waiting = bool(missing) and completed + len(missing) == total and all(
                s.kind == 'assignment' and latest.get((e.id, s.assignment_id)) == 'submitted' for s in missing)
            finished = bool(total) and completed == total
            state = 'completed' if finished else 'waiting' if waiting else 'overdue' if total and row.due_at <= now else 'open'
            result[e.id, row.module_id] = {'state': state, 'completed': finished,
                'completed_steps': completed, 'total_steps': total, 'overdue': state == 'overdue'}
    return result


def require_module_open(module, run):
    release = module_release(module, run)
    if not release['scheduled']:
        raise ApiError('Модуль ещё не включён в учебный план группы', 403)
    if release['opens_at'] and timezone.now() < release['opens_at']:
        raise ApiError('Модуль ещё не открыт', 403)


def checkpoint_dates(row):
    if not row.run.starts_at:
        return row.opens_at, row.closes_at
    last_week = row.period * (4 if row.kind == 'monthly' else 1)
    return (row.opens_at or row.run.starts_at + timedelta(days=last_week*7+(0 if row.kind == 'monthly' else -2)),
            row.closes_at or row.run.starts_at + timedelta(days=last_week*7+(2 if row.kind == 'monthly' else 0)))


def sync_checkpoint_schedules(run):
    for row in run.checkpoints.select_related('run', 'quiz'):
        starts, ends = checkpoint_dates(row)
        schedule, created = ActivitySchedule.objects.get_or_create(run=run, quiz=row.quiz,
            defaults={'max_attempts': row.quiz.max_attempts, 'time_limit_sec': row.quiz.time_limit_sec})
        schedule.opens_at, schedule.closes_at = starts, ends
        schedule.save(update_fields=['opens_at', 'closes_at'])
