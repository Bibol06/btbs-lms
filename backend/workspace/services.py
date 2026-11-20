from datetime import timedelta
from django.db.models import Q, F, Max
from django.utils import timezone
from accounts.identity import display_name
from common import ApiError
from courses.access import can_teach, is_platform_admin
from courses.models import Course, Enrollment
from assessment.deadline_views import managed_runs, student_tasks, pending_reviews, review_item, load_task_sources, tasks_by_enrollment
from communication.models import Comment
from communication.presentation import comment_content
from assessment.models import GradeReview, QuizAttempt
from .models import AttentionPolicy


def course_scope(user):
    return Course.objects.all() if is_platform_admin(user) else Course.objects.filter(
        Q(teacher=user) | Q(team__user=user) | Q(runs__teachers=user)).distinct()


def manager(user):
    if not can_teach(user):
        raise ApiError('Раздел доступен преподавателю и администратору', 403)


def question_rows(user, run_id=None):
    runs = managed_runs(user)
    if run_id:
        runs = runs.filter(id=run_id)
    comments = list(Comment.objects.filter(discussion__run__in=runs).select_related(
        'author', 'discussion__lesson__course', 'discussion__run').order_by('id'))
    roots, grouped = {}, {}
    for c in comments:
        roots[c.id] = roots.get(c.parent_id, c.parent_id) if c.parent_id else c.id
        grouped.setdefault(roots[c.id], []).append(c)
    rows = []
    for root_id, thread in grouped.items():
        c = thread[0]
        if c.id != root_id or c.is_hidden or c.is_staff_reply:
            continue
        public = [r for r in thread if not r.is_hidden]
        teacher_at = max((r.created_at for r in public if r.is_staff_reply), default=None)
        student_at = max((r.created_at for r in public if r.author_id == c.author_id), default=c.created_at)
        state = 'resolved' if c.is_resolved else 'answered' if teacher_at and teacher_at >= student_at else 'waiting'
        run = c.discussion.run
        rows.append({**comment_content(c, run.course_id), 'student': display_name(c.author), 'student_id': c.author_id,
            'course': run.course.title, 'course_id': run.course_id, 'run': run.title, 'run_id': run.id,
            'lesson': c.discussion.lesson.title, 'state': state, 'created_at': c.created_at,
            'replies': len(public)-1, 'target': f'/#course={run.course_id}&run={run.id}&lesson={c.discussion.lesson_id}&comment={c.id}'})
    return sorted(rows, key=lambda r: (r['state'] != 'waiting', r['created_at']))


def attention_rows(user, runs):
    now = timezone.now()
    from analytics.models import TrackingCoverage
    coverage = TrackingCoverage.objects.order_by('started_at').first()
    policies = {p.run_id: p for p in AttentionPolicy.objects.filter(run__in=runs)}
    from analytics.models import ActivityEvent
    from communication.models import Message
    from .models import LessonPulse
    active_kinds = ['step_view', 'step_completed', 'step_reopened', 'assignment_submitted', 'quiz_started', 'quiz_answered', 'quiz_finished', 'code_submitted']
    activity = {r['enrollment_id']: r['last'] for r in ActivityEvent.objects.filter(
        enrollment__run__in=runs, user_id=F('enrollment__student_id'), kind__in=active_kinds).values('enrollment_id').annotate(last=Max('occurred_at'))}
    for source in [LessonPulse.objects.filter(enrollment__run__in=runs).values('enrollment_id').annotate(last=Max('updated_at')),
                   Message.objects.filter(conversation__enrollment__run__in=runs, author_id=F('conversation__enrollment__student_id')).values('conversation__enrollment_id').annotate(last=Max('created_at'))]:
        for r in source:
            eid = r.get('enrollment_id') or r['conversation__enrollment_id']
            activity[eid] = max(activity.get(eid) or r['last'], r['last'])
    comments = {(r['discussion__run_id'], r['author_id']): r['last'] for r in Comment.objects.filter(discussion__run__in=runs).values('discussion__run_id', 'author_id').annotate(last=Max('created_at'))}
    enrollments = [e for e in Enrollment.objects.filter(run__in=runs, status='active', course__is_published=True).select_related('run', 'course', 'student')
                   if not ((e.run.starts_at and e.run.starts_at > now) or (e.run.ends_at and e.run.ends_at <= now))]
    # Deadlines and quiz results are computed for all students at once, not per enrollment.
    missing = {e.id for e in enrollments if (policies[e.run_id].missing_count if e.run_id in policies else 2)}
    tasks = {}
    if missing:
        from courses.access import managed_enrollment_ids
        sources = load_task_sources(Enrollment.objects.filter(id__in=missing).select_related('course', 'run__course', 'student'))
        tasks = tasks_by_enrollment(sources, managed_enrollment_ids, timezone.now())
    low_score = [e for e in enrollments if e.run_id in policies and policies[e.run_id].low_score_percent]
    latest_scores, diagnostic = {}, {}
    if low_score:
        from learning.services import visible_steps
        for course in {e.course_id: e.course for e in low_score}.values():
            placements = visible_steps(course).exclude(quiz=None)
            diagnostic[course.id] = set(placements.filter(pass_percent=0).values_list('quiz_id', flat=True)) - set(placements.filter(pass_percent__gt=0).values_list('quiz_id', flat=True))
        for a in QuizAttempt.objects.filter(enrollment__in=low_score, status='finished', max_score__gt=0).order_by('enrollment_id', 'quiz_id', '-finished_at', '-id'):
            latest_scores.setdefault(a.enrollment_id, {}).setdefault(a.quiz_id, 100*a.score/a.max_score)
    rows = []
    for e in enrollments:
        policy = policies.get(e.run_id)
        reasons = []
        if e.id in missing:
            missed = [t for t in tasks[e.id] if t['kind'] != 'module' and t.get('due_at') and t['due_at'] < now and t['state'] not in ['graded', 'waiting', 'not_started']]
            if len(missed) >= (policy.missing_count if policy else 2):
                reasons.append(f'Не завершено в срок заданий: {len(missed)}')
        if policy and policy.inactive_days and coverage:
            since = max(v for v in [e.last_seen_at, activity.get(e.id), comments.get((e.run_id, e.student_id)), e.enrolled_at, e.run.starts_at, coverage.started_at] if v)
            days = (now-since).days
            if days >= policy.inactive_days:
                reasons.append(f'Нет наблюдаемой активности в курсе {days} дн.')
        if policy and policy.low_score_percent:
            scores = [score for quiz_id, score in latest_scores.get(e.id, {}).items() if quiz_id not in diagnostic[e.course_id]]
            if scores and sum(scores)/len(scores) < policy.low_score_percent:
                reasons.append(f'Средний результат последних тестов: {round(sum(scores)/len(scores))}%')
        if reasons:
            rows.append({'id': e.id, 'student': display_name(e.student), 'course': e.course.title, 'run': e.run.title,
                'reasons': reasons, 'target': f'/#course={e.course_id}&run={e.run_id}&tab=results&student={e.student_id}'})
    return rows


def home_data(user, personal=False):
    role = 'student' if personal or not can_teach(user) else 'admin' if is_platform_admin(user) else 'teacher'
    now = timezone.now()
    if role == 'student':
        from assessment.quiz_services import finalize_due_attempts
        finalize_due_attempts(QuizAttempt.objects.filter(enrollment__student=user))
        tasks = student_tasks(user)
        tasks = [t for t in tasks if t['state'] not in ['graded', 'waiting', 'not_started']]
        tasks.sort(key=lambda t: (t['state'] != 'revision', t.get('due_at') or now+timedelta(days=36500)))
        feedback = GradeReview.objects.filter(submission__student=user,
            submission__enrollment__status__in=['active', 'completed'], submission__assignment__course__is_published=True,
            submission__assignment__is_published=True).select_related('submission__assignment', 'submission__enrollment__run', 'reviewer').order_by('-id')[:6]
        from learning.services import require_activity_visible
        visible_feedback = []
        for r in feedback:
            s = r.submission
            try:
                require_activity_visible(user, s.assignment, s.enrollment.run, 'assignment')
            except ApiError:
                continue
            visible_feedback.append({'id': r.id, 'title': s.assignment.title, 'teacher': display_name(r.reviewer),
                'score': r.score, 'max_score': s.assignment.max_score, 'body': r.feedback,
                'created_at': r.created_at, 'state': r.action,
                'target': f'/#course={s.assignment.course_id}&run={s.enrollment.run_id}&tab=assignments&submission={s.id}'})
        e = Enrollment.objects.filter(student=user, status='active', course__is_published=True).filter(Q(run__starts_at__isnull=True) | Q(run__starts_at__lte=now)).filter(Q(run__ends_at__isnull=True) | Q(run__ends_at__gt=now)).select_related('last_step__lesson__module', 'course', 'run').order_by(F('last_seen_at').desc(nulls_last=True), '-enrolled_at').first()
        if e and e.last_step:
            from learning.services import require_lesson_visible
            try:
                if not e.last_step.is_published:
                    raise ApiError('Шаг скрыт')
                require_lesson_visible(user, e.last_step.lesson, e.run)
            except ApiError:
                e.last_step = None
        resume = {'enrollment_id': e.id, 'title': e.course.title, 'lesson': e.last_step.title if e.last_step else 'Начните с первого доступного шага',
            'target': f'/#course={e.course_id}&run={e.run_id}'+(f'&step={e.last_step_id}' if e.last_step_id else '')} if e else None
        return {'role': role, 'resume': resume, 'tasks': tasks, 'feedback': visible_feedback, 'server_now': now}
    runs = managed_runs(user)
    from assessment.quiz_services import finalize_due_attempts
    finalize_due_attempts(QuizAttempt.objects.filter(enrollment__run__in=runs))
    works = list(pending_reviews(user).order_by('review_due_at', 'submitted_at')[:8])
    rows = question_rows(user)
    signals = attention_rows(user, runs)
    return {'role': role, 'server_now': now, 'works': [{**review_item(s), 'target': f'/#page=review-workspace&submission={s.id}' if role == 'teacher' else review_item(s)['target']} for s in works],
        'questions': [r for r in rows if r['state'] == 'waiting'][:6], 'question_count': sum(r['state'] == 'waiting' for r in rows),
        'attention': signals, 'runs': [{'id': r.id, 'title': r.title, 'course': r.course.title, 'kind': r.kind} for r in runs],
        'counts': {'pending': pending_reviews(user).count(), 'overdue': pending_reviews(user).filter(review_due_at__lte=now).count(),
                   'unassigned': pending_reviews(user).filter(reviewer__isnull=True).count(), 'attention': len(signals)}}

