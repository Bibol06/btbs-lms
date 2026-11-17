from collections import defaultdict
from datetime import date, datetime, time, timedelta
from statistics import median

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.identity import identity_data
from assessment.deadline_views import managed_runs
from assessment.models import Submission, QuizAttempt, GradeReview, Question
from common import ApiError, authenticated, query_integer
from courses.access import can_teach, is_platform_admin
from courses.models import CourseRun, Enrollment
from learning.models import Lesson
from learning.services import course_progress_many
from codejudge.models import CodeSubmission
from .models import ActivityEvent, ProgressSnapshot, TrackingCoverage, LessonEvaluation
from .tracking import report_zone, user_role


def period(request):
    zone = report_zone()
    today = timezone.now().astimezone(zone).date()
    name = request.GET.get('period', 'month')
    if name == 'custom':
        try:
            start, end = date.fromisoformat(request.GET.get('from', '')), date.fromisoformat(request.GET.get('to', ''))
        except ValueError:
            raise ApiError('Укажите даты начала и окончания')
    elif name in ('week', 'month', 'quarter'):
        end = today
        start = end-timedelta(days={'week': 6, 'month': 29, 'quarter': 89}[name])
    else:
        raise ApiError('Неизвестный период')
    if end < start or (end-start).days > 365 or end > today:
        raise ApiError('Период: до 366 дней, без будущих дат')
    return {'from': start, 'to': end, 'start': datetime.combine(start, time.min, zone),
            'end': datetime.combine(end+timedelta(days=1), time.min, zone), 'timezone': str(zone),
            'days': [start+timedelta(days=i) for i in range((end-start).days+1)]}


def context(request):
    authenticated(request)
    role = request.GET.get('role') or user_role(request.user)
    if role not in ('student', 'teacher', 'admin'):
        raise ApiError('Неизвестный кабинет')
    if role == 'admin' and not is_platform_admin(request.user) or role == 'teacher' and not can_teach(request.user):
        raise ApiError('Нет доступа к аналитике этого кабинета', 403)
    if role == 'student':
        runs = CourseRun.objects.filter(enrollments__student=request.user).distinct()
    elif role == 'teacher' and is_platform_admin(request.user):
        runs = CourseRun.objects.filter(Q(teachers=request.user) | Q(course__teacher=request.user) | Q(course__team__user=request.user)).distinct()
    else:
        runs = managed_runs(request.user)
    options = list(runs.select_related('course').order_by('course__title', 'id'))
    if request.GET.get('course_id'):
        runs = runs.filter(course_id=query_integer(request, 'course_id', 1, 2**63-1))
    if request.GET.get('run_id'):
        selected = get_object_or_404(runs, pk=query_integer(request, 'run_id', 1, 2**63-1))
        runs = runs.filter(pk=selected.pk)
    enrollments = Enrollment.objects.filter(run__in=runs).select_related('student', 'course', 'run', 'last_step')
    if role == 'student':
        enrollments = enrollments.filter(student=request.user)
    if request.GET.get('historical') != '1':
        enrollments = enrollments.filter(status__in=['active', 'completed'])
    if request.GET.get('enrollment_id'):
        selected = get_object_or_404(enrollments, pk=query_integer(request, 'enrollment_id', 1, 2**63-1))
        enrollments = enrollments.filter(pk=selected.id)
    return role, runs, list(enrollments.order_by('student__last_name', 'student__first_name', 'id')), options, period(request)


def meta(dates):
    coverage = TrackingCoverage.objects.order_by('id').first()
    return {'from': dates['from'], 'to': dates['to'], 'timezone': dates['timezone'], 'as_of': timezone.now(),
            'coverage_start': coverage.started_at if coverage else None, 'metric_version': 1}


def in_period(value, dates):
    return value is not None and dates['start'] <= value < dates['end']


def day(value):
    return value.astimezone(report_zone()).date()


def series(enrollments, runs, role, user, dates):
    ids = [e.id for e in enrollments]
    items = {d: {'date': d, 'submissions': 0, 'quizzes': 0, 'reviews': 0, 'learning_actions': 0, 'progress': None,
                 'known_enrollments': 0, 'program_changes': 0} for d in dates['days']}
    for stamp in Submission.objects.filter(enrollment_id__in=ids, submitted_at__gte=dates['start'], submitted_at__lt=dates['end']).values_list('submitted_at', flat=True):
        items[day(stamp)]['submissions'] += 1
    for stamp in QuizAttempt.objects.filter(enrollment_id__in=ids, status='finished', finished_at__gte=dates['start'], finished_at__lt=dates['end']).values_list('finished_at', flat=True):
        items[day(stamp)]['quizzes'] += 1
    for stamp in GradeReview.objects.filter(submission__enrollment_id__in=ids, created_at__gte=dates['start'], created_at__lt=dates['end']).values_list('created_at', flat=True):
        items[day(stamp)]['reviews'] += 1
    events = ActivityEvent.objects.filter(occurred_at__gte=dates['start'], occurred_at__lt=dates['end'])
    events = events.filter(user=user) if role == 'student' else events.filter(run__in=runs)
    events = events.exclude(kind__in=['platform_active', 'step_view'])
    if ids:
        events = events.filter(Q(enrollment_id__in=ids) | Q(enrollment__isnull=True))
    else:
        events = events.none()
    for stamp in events.values_list('occurred_at', flat=True):
        items[day(stamp)]['learning_actions'] += 1
    snapshots = list(ProgressSnapshot.objects.filter(enrollment_id__in=ids, captured_at__lt=dates['end']).order_by('captured_at', 'id')
                     .only('id', 'enrollment_id', 'captured_at', 'completed', 'total', 'reason'))
    current, index = {}, 0
    for d in dates['days']:
        for_snapshot_end = datetime.combine(d+timedelta(days=1), time.min, report_zone())
        while index < len(snapshots) and snapshots[index].captured_at < for_snapshot_end:
            snap = snapshots[index]
            current[snap.enrollment_id] = snap
            if day(snap.captured_at) == d and snap.reason == 'content':
                items[d]['program_changes'] += 1
            index += 1
        values = [s.completed*100/s.total for s in current.values() if s.total]
        items[d]['known_enrollments'] = len(values)
        items[d]['progress'] = round(sum(values)/len(values), 1) if values else None
    return list(items.values())


def run_teacher_ids(runs):
    """Union of communication.services.teacher_ids(run) over runs, in three queries."""
    from courses.models import CourseMember
    runs = list(runs.select_related('course__teacher'))
    ids = set(CourseRun.teachers.through.objects.filter(courserun_id__in=[r.id for r in runs], user__is_active=True).values_list('user_id', flat=True))
    ids |= set(CourseMember.objects.filter(course_id__in={r.course_id for r in runs}, user__is_active=True).values_list('user_id', flat=True))
    ids |= {r.course.teacher_id for r in runs if r.course.teacher_id and r.course.teacher.is_active}
    return ids


def dashboard_data(request):
    role, runs, enrollments, options, dates = context(request)
    ids = [e.id for e in enrollments]
    progress = course_progress_many(enrollments)
    submissions = Submission.objects.filter(enrollment_id__in=ids)
    pending = submissions.filter(status='submitted')
    now = timezone.now()
    quizzes = QuizAttempt.objects.filter(enrollment_id__in=ids, status='finished')
    reviews = GradeReview.objects.filter(submission__enrollment_id__in=ids)
    # First review is not the same as edits of the same grade.
    durations, first_checks = [], 0
    teacher_stats = defaultdict(lambda: {'reviews': 0, 'works': set(), 'first': 0, 'durations': []})
    seen = set()
    for review in reviews.select_related('submission').order_by('created_at', 'id'):
        if in_period(review.created_at, dates) and review.reviewer_id:
            teacher_stats[review.reviewer_id]['reviews'] += 1
            teacher_stats[review.reviewer_id]['works'].add(review.submission_id)
        if review.submission_id in seen:
            continue
        seen.add(review.submission_id)
        if in_period(review.created_at, dates):
            first_checks += 1
            duration = max(0, (review.created_at-review.submission.submitted_at).total_seconds()/3600)
            durations.append(duration)
            if review.reviewer_id:
                teacher_stats[review.reviewer_id]['first'] += 1
                teacher_stats[review.reviewer_id]['durations'].append(duration)
    rows = []
    page = query_integer(request, 'page', 1, 100000, 1)
    shown = enrollments[(page-1)*20:page*20]
    pending_by_enrollment = dict(pending.filter(enrollment__in=shown).values('enrollment_id').annotate(n=Count('id')).values_list('enrollment_id', 'n')) if shown else {}
    for e in shown:
        p = progress[e.id]
        rows.append({**identity_data(e.student), 'enrollment_id': e.id, 'course_id': e.course_id, 'course': e.course.title,
            'run_id': e.run_id, 'run': e.run.title, 'status': e.status, 'progress': {k: p[k] for k in ('completed', 'total', 'percent')},
            'pending': pending_by_enrollment.get(e.id, 0), 'last_seen_at': e.last_seen_at,
            'target': f'/#course={e.course_id}&run={e.run_id}&tab=results&student={e.student_id}' if role != 'student' else f'/#course={e.course_id}&run={e.run_id}&tab=results',
            })
    values = [p['percent'] for p in progress.values() if p['total']]
    summary = {'students': len({e.student_id for e in enrollments}), 'enrollments': len(enrollments),
        'progress': round(sum(values)/len(values), 1) if values else None,
        'completed': sum(p['total'] > 0 and p['completed'] == p['total'] for p in progress.values()),
        'pending': pending.count(), 'overdue': pending.filter(review_due_at__lte=now).count(),
        'submitted': submissions.filter(submitted_at__gte=dates['start'], submitted_at__lt=dates['end']).count(),
        'quizzes': quizzes.filter(finished_at__gte=dates['start'], finished_at__lt=dates['end']).count(),
        'reviews': reviews.filter(created_at__gte=dates['start'], created_at__lt=dates['end']).count(),
        'first_reviews': first_checks, 'median_review_hours': round(median(durations), 1) if durations else None,
        'late': submissions.filter(submitted_at__gte=dates['start'], submitted_at__lt=dates['end'], is_late=True).count()}
    previous_end = dates['start']
    previous_start = previous_end-(dates['end']-dates['start'])
    previous = {'from': previous_start.date(), 'to': (previous_end-timedelta(days=1)).date(),
        'submitted': submissions.filter(submitted_at__gte=previous_start, submitted_at__lt=previous_end).count(),
        'quizzes': quizzes.filter(finished_at__gte=previous_start, finished_at__lt=previous_end).count(),
        'reviews': reviews.filter(created_at__gte=previous_start, created_at__lt=previous_end).count()}
    material_data = materials(enrollments, progress, runs, dates, request) if role != 'student' else {'lessons': [], 'total': 0, 'next_page': None}
    teacher_work = []
    if role == 'admin':
        people = set(teacher_stats) | run_teacher_ids(runs)
        assigned = defaultdict(lambda: [0, 0])
        for reviewer_id, due in pending.filter(reviewer_id__in=people).values_list('reviewer_id', 'review_due_at'):
            assigned[reviewer_id][0] += 1
            assigned[reviewer_id][1] += bool(due and due <= now)
        for person in get_user_model().objects.filter(id__in=people).order_by('last_name', 'first_name', 'id'):
            values = teacher_stats[person.id]
            teacher_work.append({**identity_data(person, teaching=True), 'pending': assigned[person.id][0],
                'overdue': assigned[person.id][1], 'reviews': values['reviews'],
                'unique_works': len(values['works']), 'first_reviews': values['first'],
                'median_hours': round(median(values['durations']), 1) if values['durations'] else None})
    choices = Enrollment.objects.filter(run__in=runs, status__in=['active', 'completed']).select_related('student', 'course', 'run')
    if role == 'student':
        choices = choices.filter(student=request.user)
    return {**meta(dates), 'role': role, 'summary': summary, 'previous': previous, 'series': series(enrollments, runs, role, request.user, dates), 'teacher_work': teacher_work,
        'learners': rows, 'total': len(enrollments), 'page': page, 'next_page': page+1 if page*20 < len(enrollments) else None,
        'options': {'runs': [{'id': r.id, 'course_id': r.course_id, 'course': r.course.title, 'title': r.title} for r in options],
                    'enrollments': [{'id': e.id, 'name': identity_data(e.student)['display_name'], 'course': e.course.title, 'run': e.run.title} for e in choices.order_by('student__last_name', 'id')[:300]]},
        'materials': material_data}


def materials(enrollments, progress, runs, dates, request):
    ids = [e.id for e in enrollments]
    page = query_integer(request, 'lesson_page', 1, 100000, 1)
    lessons = Lesson.objects.filter(course_id__in=runs.values('course_id'), is_published=True).exclude(module__is_published=False).select_related('course').prefetch_related('steps').order_by('course_id', 'position', 'id')
    total = lessons.count()
    selected = list(lessons[(page-1)*15:page*15])
    events = ActivityEvent.objects.filter(enrollment_id__in=ids, kind='step_view', step__kind__in=['text', 'video', 'file'], actor_role='student').order_by('occurred_at')
    first_views, viewers = defaultdict(list), defaultdict(set)
    for event in events.filter(lesson_id__in=[l.id for l in selected]):
        first_views[event.enrollment_id, event.lesson_id].append(event.occurred_at)
        if in_period(event.occurred_at, dates):
            viewers[event.lesson_id].add(event.enrollment_id)
    evaluations = list(LessonEvaluation.objects.filter(run__in=runs, lesson__in=selected))
    # Only the activities of this page's lessons are read; every lookup below is keyed by them.
    page_steps = [s for lesson in selected for s in lesson.steps.all() if s.is_published]
    quiz_ids = {s.quiz_id for s in page_steps if s.kind == 'quiz' and s.quiz_id}
    quiz_ids |= {q for ev in evaluations if ev.pre_quiz_id and ev.post_quiz_id for q in (ev.pre_quiz_id, ev.post_quiz_id)}
    assignment_ids = {s.assignment_id for s in page_steps if s.kind == 'assignment' and s.assignment_id}
    problem_ids = {s.code_problem_id for s in page_steps if s.kind == 'code' and s.code_problem_id}
    quiz_attempts = list(QuizAttempt.objects.filter(enrollment_id__in=ids, quiz_id__in=quiz_ids, status='finished', max_score__gt=0).order_by('started_at', 'id')) if quiz_ids else []
    quiz_by_pair, first_quiz = defaultdict(list), {}
    for attempt in quiz_attempts:
        quiz_by_pair[attempt.enrollment_id, attempt.quiz_id].append(attempt)
        first_quiz.setdefault((attempt.enrollment_id, attempt.quiz_id), attempt)
    first_assignment = {}
    for s in Submission.objects.filter(enrollment_id__in=ids, assignment_id__in=assignment_ids, status='graded', score__isnull=False).select_related('assignment').order_by('attempt_no', 'id'):
        # A returned first attempt remains a revision, not a fabricated first success.
        first_assignment.setdefault((s.enrollment_id, s.assignment_id), s)
    first_code = {}
    for s in CodeSubmission.objects.filter(enrollment_id__in=ids, problem_id__in=problem_ids).exclude(status__in=['running', 'service_error']).order_by('created_at', 'id'):
        first_code.setdefault((s.enrollment_id, s.problem_id), s)
    attempts = defaultdict(int)
    for a in quiz_attempts:
        if in_period(a.finished_at, dates):
            attempts[a.enrollment_id, 'quiz', a.quiz_id] += 1
    for e, aid, stamp in Submission.objects.filter(enrollment_id__in=ids, assignment_id__in=assignment_ids, submitted_at__gte=dates['start'], submitted_at__lt=dates['end']).values_list('enrollment_id', 'assignment_id', 'submitted_at'):
        attempts[e, 'assignment', aid] += 1
    for e, pid in CodeSubmission.objects.filter(enrollment_id__in=ids, problem_id__in=problem_ids, created_at__gte=dates['start'], created_at__lt=dates['end']).exclude(status__in=['running', 'service_error']).values_list('enrollment_id', 'problem_id'):
        attempts[e, 'code', pid] += 1
    questions = defaultdict(list)
    for q in Question.objects.filter(quiz_id__in={a.quiz_id for a in quiz_attempts}):
        questions[q.quiz_id].append(q)
    by_course = defaultdict(list)
    for e in enrollments:
        by_course[e.course_id].append(e)
    rows = []
    for lesson in selected:
        steps = [s for s in lesson.steps.all() if s.is_published]
        required = {s.id for s in steps if s.required}
        opened = viewers[lesson.id]
        completed = sum(bool(required) and required <= progress[eid]['step_ids'] for eid in opened)
        observations, lesson_attempts, errors = {}, {}, {}
        for e in by_course[lesson.course_id]:
            for step in steps:
                activity_id = step.quiz_id if step.kind == 'quiz' else step.assignment_id if step.kind == 'assignment' else step.code_problem_id if step.kind == 'code' else None
                if activity_id and attempts[e.id, step.kind, activity_id]:
                    lesson_attempts[e.id, step.kind, activity_id] = attempts[e.id, step.kind, activity_id]
                if step.kind == 'quiz' and step.pass_percent > 0:
                    a = first_quiz.get((e.id, step.quiz_id))
                    if a and in_period(a.finished_at, dates):
                        observations[e.id, 'quiz', step.quiz_id] = a.score*100 >= a.max_score*step.pass_percent
                        for q in questions[a.quiz_id]:
                            value = errors.setdefault(q.id, {'question_id': q.id, 'body': q.body, 'wrong': 0, 'unanswered': 0, 'samples': 0, 'seen': set()})
                            if e.id in value['seen']:
                                continue
                            value['seen'].add(e.id)
                            value['samples'] += 1
                            answer = a.answers.get(str(q.id))
                            if type(answer) is not int or not 0 <= answer < len(q.options):
                                value['unanswered'] += 1
                            elif answer != q.correct_index:
                                value['wrong'] += 1
                elif step.kind == 'assignment':
                    a = first_assignment.get((e.id, step.assignment_id))
                    if a and a.attempt_no == 1 and in_period(a.graded_at, dates):
                        observations[e.id, 'assignment', step.assignment_id] = a.score*100 >= a.assignment.max_score*step.pass_percent
                elif step.kind == 'code':
                    a = first_code.get((e.id, step.code_problem_id))
                    if a and in_period(a.created_at, dates):
                        observations[e.id, 'code', step.code_problem_id] = a.status == 'accepted'
        before, after = [], []
        for evaluation in [ev for ev in evaluations if ev.lesson_id == lesson.id and ev.pre_quiz_id and ev.post_quiz_id]:
            for e in enrollments:
                if e.run_id != evaluation.run_id:
                    continue
                for pre in quiz_by_pair[e.id, evaluation.pre_quiz_id]:
                    if not pre.finished_at:
                        continue
                    exposed = next((stamp for stamp in first_views[e.id, lesson.id] if stamp >= pre.finished_at), None)
                    if not exposed:
                        continue
                    post = next((a for a in quiz_by_pair[e.id, evaluation.post_quiz_id] if a.started_at >= exposed and in_period(a.finished_at, dates)), None)
                    if post:
                        before.append(pre.score*100/pre.max_score)
                        after.append(post.score*100/post.max_score)
                        break
        n = len(observations)
        success = round(sum(observations.values())*100/n, 1) if n else None
        rows.append({'id': lesson.id, 'title': lesson.title, 'course': lesson.course.title, 'opened': len(opened), 'completed': completed,
            'first_attempt_success': success, 'attempt_samples': n, 'attention': n >= 5 and success < 60,
            'attempts': sum(lesson_attempts.values()), 'mean_attempts': round(sum(lesson_attempts.values())/len(lesson_attempts), 1) if lesson_attempts else None,
            'common_errors': [{k: v for k, v in item.items() if k != 'seen'} for item in sorted(errors.values(), key=lambda item: -(item['wrong']+item['unanswered'])) if item['wrong']+item['unanswered']][:3],
            'comparison': {'pairs': len(before), 'before': round(sum(before)/len(before), 1) if before else None,
                           'after': round(sum(after)/len(after), 1) if after else None,
                           'change': round(sum(after)/len(after)-sum(before)/len(before), 1) if before else None},
            'evaluation_configured': any(ev.lesson_id == lesson.id for ev in evaluations),
            'target': f'/#course={lesson.course_id}&lesson={lesson.id}'})
    return {'lessons': rows, 'total': total, 'page': page, 'next_page': page+1 if page*15 < total else None}
