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
    return module_deadline_states_many([(run, enrollments)], now)


def module_deadline_states_many(groups, now=None):
    """Batch form of module_deadline_states for several (run, enrollments) pairs.

    Query count does not depend on the number of runs: progress, steps, legacy
    lessons, submissions and lesson marks are each loaded once for all groups.
    """
    now = now or timezone.now()
    groups = [(run, list(enrollments)) for run, enrollments in groups if enrollments]
    deadline_groups = []
    for run, enrollments in groups:
        deadlines = run._deadline_rows if hasattr(run, '_deadline_rows') else list(run.module_releases.filter(due_at__isnull=False, module__is_published=True).select_related('module'))
        if deadlines:
            deadline_groups.append((run, enrollments, deadlines))
    if not deadline_groups:
        return {}
    from learning.services import course_progress_many
    from assessment.models import Submission, LessonProgress
    from learning.models import Lesson, Step
    all_enrollments = [e for _, enrollments, _ in deadline_groups for e in enrollments]
    progress = course_progress_many(all_enrollments)
    module_course = {row.module_id: run.course_id for run, _, deadlines in deadline_groups for row in deadlines}
    by_module = {module_id: [] for module_id in module_course}
    # Same filter as learning.services.visible_steps(course), applied to all courses at once.
    for step in (Step.objects.filter(lesson__course_id__in=set(module_course.values()), is_published=True, lesson__is_published=True,
                                     required=True, lesson__module_id__in=by_module)
                 .exclude(lesson__module__is_published=False).select_related('lesson')):
        if step.lesson.course_id == module_course[step.lesson.module_id]:
            by_module[step.lesson.module_id].append(step)
    legacy = {module_id: [] for module_id in module_course}
    for course_id, module_id, lesson_id in Lesson.objects.filter(course_id__in=set(module_course.values()), is_published=True,
                                                                 module_id__in=by_module, steps__isnull=True).values_list('course_id', 'module_id', 'id'):
        if course_id == module_course[module_id]:
            legacy[module_id].append(lesson_id)
    ids = [e.id for e in all_enrollments]
    latest = {}
    for enrollment_id, assignment_id, status in Submission.objects.filter(enrollment_id__in=ids).order_by('enrollment_id', 'assignment_id', '-submitted_at', '-id').values_list('enrollment_id', 'assignment_id', 'status'):
        latest.setdefault((enrollment_id, assignment_id), status)
    legacy_done = set(LessonProgress.objects.filter(enrollment_id__in=ids).values_list('enrollment_id', 'lesson_id'))
    result = {}
    for run, enrollments, deadlines in deadline_groups:
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
