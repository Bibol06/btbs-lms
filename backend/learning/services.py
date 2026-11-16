from django.utils import timezone
from common import ApiError
from courses.access import can_manage_run
from .models import Step, StepProgress


def visible_steps(course):
    return Step.objects.filter(lesson__course=course, is_published=True, lesson__is_published=True).exclude(lesson__module__is_published=False)


def step_completed(step, enrollment):
    if not enrollment:
        return False
    if getattr(step, '_progress_enrollment', None) == enrollment.id:
        return bool(step._theory_done if step.kind in ['text', 'video', 'file'] else step._assignment_done if step.kind == 'assignment' else step._quiz_done if step.kind == 'quiz' else step._code_done if step.kind == 'code' else False)
    if step.kind in ['text', 'video', 'file']:
        return StepProgress.objects.filter(enrollment=enrollment, step=step).exists()
    if step.kind == 'assignment' and step.assignment_id:
        return step.assignment.submissions.filter(enrollment=enrollment, status='graded', score__gte=step.assignment.max_score * step.pass_percent / 100.0).exists()
    if step.kind == 'quiz' and step.quiz_id:
        from django.db.models import F
        return step.quiz.attempts.filter(enrollment=enrollment, status='finished', score__gte=F('max_score') * step.pass_percent / 100.0).exists()
    if step.kind == 'code' and step.code_problem_id:
        return step.code_problem.submissions.filter(enrollment=enrollment, status='accepted').exists()
    return False


def with_step_progress(queryset, enrollment):
    """Correlated EXISTS computes all completion flags in one SQL round trip."""
    if enrollment is None:
        return queryset
    from django.db.models import Exists, OuterRef, Value, F
    from assessment.models import Submission, QuizAttempt
    from codejudge.models import CodeSubmission
    return queryset.annotate(
        _progress_enrollment=Value(enrollment.id),
        _theory_done=Exists(StepProgress.objects.filter(enrollment=enrollment, step_id=OuterRef('pk'))),
        _assignment_done=Exists(Submission.objects.filter(enrollment=enrollment, assignment_id=OuterRef('assignment_id'), status='graded', score__gte=OuterRef('assignment__max_score') * OuterRef('pass_percent') / 100.0)),
        _quiz_done=Exists(QuizAttempt.objects.filter(enrollment=enrollment, quiz_id=OuterRef('quiz_id'), status='finished', score__gte=F('max_score') * OuterRef('pass_percent') / 100.0)),
        _code_done=Exists(CodeSubmission.objects.filter(enrollment=enrollment, problem_id=OuterRef('code_problem_id'), status='accepted')),
    )


def course_progress(course, enrollment):
    steps = list(with_step_progress(visible_steps(course).filter(required=True), enrollment).select_related('assignment', 'quiz', 'code_problem'))
    checks = list(enrollment.run.checkpoints.filter(required=True, quiz__is_published=True)) if enrollment else []
    thresholds = {c.quiz_id: c.pass_percent for c in checks}
    if not steps:
        # Compatibility for older courses/tests with lessons and no steps yet.
        total = course.lessons.filter(is_published=True).count()
        done = enrollment.lessonprogress_records.filter(lesson__is_published=True).count() if enrollment else 0
    else:
        total = len(steps)
        done = 0
        for step in steps:
            if step.kind == 'quiz' and thresholds.get(step.quiz_id, 0) > step.pass_percent:
                from django.db.models import F
                done += int(step.quiz.attempts.filter(enrollment=enrollment, status='finished', max_score__gt=0,
                    score__gte=F('max_score') * thresholds[step.quiz_id] / 100.0).exists())
            else:
                done += int(step_completed(step, enrollment))
    if enrollment:
        from django.db.models import F
        placed = {s.quiz_id for s in steps if s.kind == 'quiz'}
        for check in checks:
            if check.quiz_id in placed:
                continue
            total += 1
            done += int(check.quiz.attempts.filter(enrollment=enrollment, status='finished', max_score__gt=0,
                score__gte=F('max_score') * check.pass_percent / 100.0).exists())
    return {'completed': done, 'total': total, 'percent': round(done * 100 / total) if total else 0}


def refresh_completion(enrollment):
    progress = course_progress(enrollment.course, enrollment)
    desired = 'completed' if progress['total'] and progress['completed'] == progress['total'] else 'active'
    if enrollment.status not in ['archived', 'removed'] and enrollment.status != desired:
        enrollment.status = desired
        enrollment.save(update_fields=['status'])
    from analytics.tracking import capture_progress
    capture_progress(enrollment, progress)
    return progress


def progress_steps(course_ids):
    # Completion needs identifiers and thresholds, never lesson bodies or quiz text.
    return list(Step.objects.filter(lesson__course_id__in=course_ids, is_published=True,
        lesson__is_published=True, required=True).exclude(lesson__module__is_published=False)
        .select_related('lesson', 'assignment').only('id', 'lesson_id', 'lesson__course_id',
            'kind', 'pass_percent', 'assignment_id', 'assignment__max_score', 'quiz_id', 'code_problem_id')
        .order_by('id'))


def course_progress_many(enrollments, *, steps=None):
    """Batch equivalent of course_progress; shared by analytics and snapshots."""
    from collections import defaultdict
    from assessment.models import Submission, QuizAttempt, LessonProgress
    from codejudge.models import CodeSubmission
    from .models import Lesson
    ids = [e.id for e in enrollments]
    courses = {e.course_id for e in enrollments}
    if steps is None:
        steps = progress_steps(courses)
    by_course = defaultdict(list)
    for step in steps:
        by_course[step.lesson.course_id].append(step)
    theory = set(StepProgress.objects.filter(enrollment_id__in=ids).values_list('enrollment_id', 'step_id'))
    assignments, quizzes = defaultdict(list), defaultdict(list)
    assignment_ids = {s.assignment_id for s in steps if s.kind == 'assignment' and s.assignment_id}
    for e, a, score in Submission.objects.filter(enrollment_id__in=ids, assignment_id__in=assignment_ids, status='graded', score__isnull=False).values_list('enrollment_id', 'assignment_id', 'score'):
        assignments[e, a].append(score)
    from courses.models import RunCheckpoint
    checks_by_run = defaultdict(list)
    for check in RunCheckpoint.objects.filter(run_id__in={e.run_id for e in enrollments}, required=True, quiz__is_published=True):
        checks_by_run[check.run_id].append(check)
    quiz_ids = {s.quiz_id for s in steps if s.kind == 'quiz' and s.quiz_id} | {c.quiz_id for rows in checks_by_run.values() for c in rows}
    for e, q, score, total in QuizAttempt.objects.filter(enrollment_id__in=ids, quiz_id__in=quiz_ids, status='finished').values_list('enrollment_id', 'quiz_id', 'score', 'max_score'):
        quizzes[e, q].append((score, total))
    problem_ids = {s.code_problem_id for s in steps if s.kind == 'code' and s.code_problem_id}
    code = set(CodeSubmission.objects.filter(enrollment_id__in=ids, problem_id__in=problem_ids, status='accepted').values_list('enrollment_id', 'problem_id'))
    legacy_totals, legacy_done = defaultdict(int), defaultdict(int)
    legacy_courses = courses - by_course.keys()
    legacy_ids = [e.id for e in enrollments if e.course_id in legacy_courses]
    for cid in Lesson.objects.filter(course_id__in=legacy_courses, is_published=True).values_list('course_id', flat=True):
        legacy_totals[cid] += 1
    for eid in LessonProgress.objects.filter(enrollment_id__in=legacy_ids, lesson__is_published=True).values_list('enrollment_id', flat=True):
        legacy_done[eid] += 1
    result = {}
    for enrollment in enrollments:
        completed = set()
        thresholds = {c.quiz_id: c.pass_percent for c in checks_by_run[enrollment.run_id]}
        for step in by_course[enrollment.course_id]:
            passed = (enrollment.id, step.id) in theory if step.kind in ('text', 'video', 'file') else any(s*100 >= step.assignment.max_score*step.pass_percent for s in assignments[enrollment.id, step.assignment_id]) if step.kind == 'assignment' and step.assignment_id else any(total > 0 and score*100 >= total*max(step.pass_percent, thresholds.get(step.quiz_id, 0)) for score, total in quizzes[enrollment.id, step.quiz_id]) if step.kind == 'quiz' and step.quiz_id else (enrollment.id, step.code_problem_id) in code if step.kind == 'code' and step.code_problem_id else False
            if passed:
                completed.add(step.id)
        total = len(by_course[enrollment.course_id]) or legacy_totals[enrollment.course_id]
        done = len(completed) if by_course[enrollment.course_id] else legacy_done[enrollment.id]
        placed = {s.quiz_id for s in by_course[enrollment.course_id] if s.kind == 'quiz'}
        for check in checks_by_run[enrollment.run_id]:
            if check.quiz_id in placed:
                continue
            total += 1
            done += int(any(maximum > 0 and score*100 >= maximum*check.pass_percent for score, maximum in quizzes[enrollment.id, check.quiz_id]))
        result[enrollment.id] = {'completed': done, 'total': total, 'percent': round(done*100/total) if total else 0, 'step_ids': completed}
    return result


def refresh_completions(enrollments):
    """Batch dashboard refresh, with the same row locks as snapshot writers."""
    import hashlib
    from collections import defaultdict
    from django.db import transaction
    from courses.models import Enrollment
    from analytics.models import ProgressSnapshot
    from .models import Lesson
    if not enrollments:
        return {}
    with transaction.atomic():
        locked = list(Enrollment.objects.select_for_update().filter(pk__in=[e.pk for e in enrollments]).order_by('pk'))
        course_ids = {e.course_id for e in locked}
        steps = progress_steps(course_ids)
        progress = course_progress_many(locked, steps=steps)
        specs = defaultdict(list)
        for step in steps:
            specs[step.lesson.course_id].append((step.id, step.kind, step.pass_percent,
                step.assignment_id, step.quiz_id, step.code_problem_id))
        for cid, lid in Lesson.objects.filter(course_id__in=course_ids - specs.keys(), is_published=True).order_by('position', 'id').values_list('course_id', 'id'):
            specs[cid].append(lid)
        fingerprints = {cid: hashlib.sha256(repr(specs[cid]).encode()).hexdigest() for cid in course_ids}
        previous = {s.enrollment_id: s for s in ProgressSnapshot.objects.filter(enrollment_id__in=[e.pk for e in locked]).order_by('enrollment_id', '-captured_at', '-id').distinct('enrollment_id')}
        changed, snapshots = [], []
        for e in locked:
            p = progress[e.pk]
            desired = 'completed' if p['total'] and p['completed'] == p['total'] else 'active'
            if e.status not in ['archived', 'removed'] and e.status != desired:
                e.status = desired; changed.append(e)
            old = previous.get(e.pk); fingerprint = fingerprints[e.course_id]
            if old is None or (old.completed, old.total, old.program_fingerprint) != (p['completed'], p['total'], fingerprint):
                snapshots.append(ProgressSnapshot(enrollment=e, completed=p['completed'], total=p['total'], program_fingerprint=fingerprint,
                    reason='baseline' if old is None else 'content' if old.program_fingerprint != fingerprint else 'progress'))
        if changed:
            Enrollment.objects.bulk_update(changed, ['status'])
        ProgressSnapshot.objects.bulk_create(snapshots)
        statuses = {e.pk: e.status for e in locked}
        for e in enrollments:
            e.status = statuses[e.pk]
        return {eid: {key: value for key, value in p.items() if key != 'step_ids'} for eid, p in progress.items()}


def require_lesson_visible(user, lesson, run, *, manager=None):
    if lesson.course_id != run.course_id:
        raise ApiError('Урок другого курса', 404)
    if (manager if manager is not None else can_manage_run(user, run)):
        return
    if run.starts_at and timezone.now() < run.starts_at:
        raise ApiError('Обучение ещё не началось', 403)
    if not lesson.is_published:
        raise ApiError('Урок не опубликован', 404)
    module = lesson.module
    if module:
        if not module.is_published:
            raise ApiError('Модуль не опубликован', 404)
        from courses.pacing import require_module_open
        require_module_open(module, run)
        if module.prerequisite_id:
            if not module.prerequisite.is_published:
                raise ApiError('Предыдущий модуль ещё не опубликован', 403)
            from courses.models import Enrollment
            enrollment = Enrollment.objects.filter(run=run, student=user).first()
            prerequisites = visible_steps(run.course).filter(lesson__module=module.prerequisite, required=True)
            if any(not step_completed(s, enrollment) for s in prerequisites):
                raise ApiError('Сначала завершите обязательные шаги предыдущего модуля', 403)


def require_activity_visible(user, activity, run, kind):
    # If an activity is used in steps, at least one published, unlocked placement is required.
    if can_manage_run(user, run):
        return
    if run.starts_at and timezone.now() < run.starts_at:
        raise ApiError('Обучение ещё не началось', 403)
    if kind == 'quiz' and activity.checkpoints.exists():
        if activity.checkpoints.filter(run=run).exists():
            return
        if not activity.steps.exists():
            raise ApiError('Тест не назначен этой группе', 403)
    placements = activity.steps.all()
    if not placements.exists():
        return
    for step in placements.filter(is_published=True).select_related('lesson__module'):
        try:
            require_lesson_visible(user, step.lesson, run)
            return
        except ApiError:
            pass
    raise ApiError('Этот учебный шаг ещё недоступен', 403)
