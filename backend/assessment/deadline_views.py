from accounts.identity import display_name, role_label
from datetime import timedelta, datetime

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from common import api, authenticated, body, integer, query_integer, text, date, ApiError
from courses.access import require_run, resolve_run, is_platform_admin
from courses.models import CourseRun, Enrollment
from learning.services import require_activity_visible
from .models import Assignment, Submission, QuizAttempt
from .deadlines import submission_window, grant_extension, review_state
from .quiz_services import finalize_due_attempts


def managed_runs(user):
    qs = CourseRun.objects.select_related('course')
    return qs if is_platform_admin(user) else qs.filter(Q(teachers=user) | Q(course__teacher=user) | Q(course__team__user=user)).distinct()


def pending_reviews(user):
    return Submission.objects.filter(enrollment__run__in=managed_runs(user), status='submitted').select_related('student', 'reviewer', 'assignment__course', 'enrollment__run')


def review_item(s):
    return {'id': s.id, 'student': display_name(s.student), 'student_role_label': role_label(s.student), 'course_id': s.assignment.course_id,
            'course': s.assignment.course.title, 'run_id': s.enrollment.run_id, 'run': s.enrollment.run.title,
            'assignment': s.assignment.title, 'submitted_at': s.submitted_at, 'review_due_at': s.review_due_at,
            'review_state': review_state(s), 'reviewer_id': s.reviewer_id, 'reviewer_role_label': role_label(s.reviewer, teaching=True),
            'reviewer': (display_name(s.reviewer)) if s.reviewer else None, 'is_late': s.is_late,
            'target': f'/#course={s.assignment.course_id}&run={s.enrollment.run_id}&tab=assignments&submission={s.id}'}


@require_GET
@api
def review_queue(request):
    authenticated(request)
    from courses.access import can_teach
    if not can_teach(request.user):
        raise ApiError('Проверка работ доступна преподавателю и администратору', 403)
    qs = pending_reviews(request.user)
    for key, field in [('course_id', 'assignment__course_id'), ('run_id', 'enrollment__run_id'), ('reviewer_id', 'reviewer_id')]:
        if request.GET.get(key):
            qs = qs.filter(**{field: query_integer(request, key, 1, 2**63-1)})
    if request.GET.get('mine') == '1':
        qs = qs.filter(reviewer=request.user)
    if request.GET.get('unassigned') == '1':
        qs = qs.filter(reviewer__isnull=True)
    now = timezone.now()
    counts = {'all': qs.count(), 'overdue': qs.filter(review_due_at__lte=now).count(),
              'soon': qs.filter(review_due_at__gt=now, review_due_at__lte=now + timedelta(hours=24)).count()}
    state = request.GET.get('state', 'all')
    if state == 'overdue':
        qs = qs.filter(review_due_at__lte=now)
    elif state == 'soon':
        qs = qs.filter(review_due_at__gt=now, review_due_at__lte=now + timedelta(hours=24))
    elif state != 'all':
        raise ApiError('Неизвестный фильтр очереди')
    try:
        page = int(request.GET.get('page', 1))
    except ValueError:
        raise ApiError('Неверная страница')
    if not 1 <= page <= 100000:
        raise ApiError('Неверная страница')
    total = qs.count()
    records = qs.order_by(F('review_due_at').asc(nulls_last=True), 'submitted_at', 'id')[(page-1)*30:page*30]
    return JsonResponse({'total': total, 'counts': counts, 'page': page, 'next_page': page + 1 if page*30 < total else None,
                         'works': [review_item(s) for s in records]})


@require_http_methods(['GET', 'POST'])
@api
def extensions(request, assignment_id):
    assignment = get_object_or_404(Assignment.objects.select_related('course'), pk=assignment_id)
    run = resolve_run(request, assignment.course)
    require_run(request, run, manage=True)
    if request.method == 'POST':
        data = body(request)
        with transaction.atomic():
            enrollment = get_object_or_404(Enrollment.objects.select_for_update(), pk=integer(data, 'enrollment_id', 1, 2**63-1), run=run)
            grant_extension(assignment, enrollment, request.user, date(data, 'deadline_at'), text(data, 'reason', 500))
        return JsonResponse({'message': 'Индивидуальный срок сохранён. Ученик получит уведомление.'})
    return JsonResponse({'students': [{'id': e.id, 'student': display_name(e.student),
                                      'window': submission_window(assignment, e)}
                                     for e in run.enrollments.filter(status__in=['active', 'completed']).select_related('student', 'run').order_by('student__username')]})


@require_http_methods(['PATCH'])
@api
def assign_reviewer(request, submission_id):
    with transaction.atomic():
        s = get_object_or_404(Submission.objects.select_for_update(), pk=submission_id)
        require_run(request, s.enrollment.run, manage=True)
        if s.status != 'submitted':
            raise ApiError('Работа уже проверена или возвращена ученику')
        data = body(request)
        from communication.services import teacher_ids, audit, notify, course_target
        if 'reviewer_id' in data:
            reviewer = get_object_or_404(get_user_model(), pk=integer(data, 'reviewer_id', 1, 2**63-1), is_active=True)
            if reviewer.id not in teacher_ids(s.enrollment.run):
                raise ApiError('Ответственный должен быть преподавателем этой группы', 403)
            s.reviewer = reviewer
        if 'review_due_at' in data:
            due = date(data, 'review_due_at')
            if not due or due <= timezone.now():
                raise ApiError('Укажите будущую дату проверки')
            s.review_due_at = due
        s.save(update_fields=['reviewer', 'review_due_at'])
        audit(request.user, s.assignment.course, 'submission.reviewer_assigned', {'submission_id': s.id, 'reviewer_id': s.reviewer_id,
                'review_due_at': s.review_due_at.isoformat() if s.review_due_at else None})
        if s.reviewer_id and s.reviewer_id != request.user.id:
            notify(f'review-assigned:{s.id}:{s.reviewer_id}:{s.review_due_at}', 'submission', s.assignment.course, {s.reviewer_id},
                   'Вам назначена работа на проверку', course_target(s.assignment.course, s.enrollment.run, 'assignments'), s.enrollment.run)
    return JsonResponse({'message': 'Ответственный и срок проверки сохранены', 'work': review_item(s)})


def student_tasks(user, enrollment_ids=None):
    from django.db.models import Prefetch
    from courses.models import RunModuleRelease
    from .models import Assignment, Quiz
    now = timezone.now()
    tasks = []
    enrollments = Enrollment.objects.filter(student=user, status__in=['active', 'completed'], course__is_published=True).select_related('course', 'run')
    if enrollment_ids is not None:
        enrollments = enrollments.filter(id__in=enrollment_ids)
    enrollments = enrollments.prefetch_related(
        Prefetch('course__assignments', queryset=Assignment.objects.filter(is_published=True), to_attr='_agenda_assignments'),
        Prefetch('course__quizzes', queryset=Quiz.objects.filter(is_published=True), to_attr='_agenda_quizzes'),
        Prefetch('run__module_releases', queryset=RunModuleRelease.objects.filter(due_at__isnull=False, module__is_published=True).select_related('module'), to_attr='_deadline_rows'))
    for e in enrollments:
        base = {'course_id': e.course_id, 'course': e.course.title, 'run_id': e.run_id, 'run': e.run.title}
        from courses.pacing import module_deadline_states, module_release
        module_states = module_deadline_states(e.run, [e], now)
        for row in e.run._deadline_rows:
            state = module_states.get((e.id, row.module_id))
            if not state:
                continue
            release = module_release(row.module, e.run)
            opened = not ((e.run.starts_at and now < e.run.starts_at) or (release['opens_at'] and now < release['opens_at']))
            phase = 'graded' if state['completed'] else 'waiting' if state['state'] == 'waiting' else 'module_overdue' if state['overdue'] else 'open' if opened else 'not_started'
            tasks.append({**base, 'id': f'module:{row.module_id}:{e.id}', 'kind': 'module', 'title': row.module.title,
                          'state': phase, 'due_at': row.due_at, 'closes_at': None, 'opens_at': release['opens_at'],
                          'completed_steps': state['completed_steps'], 'total_steps': state['total_steps'],
                          'target': f'/#course={e.course_id}&run={e.run_id}&tab=plan'})
        for a in e.course._agenda_assignments:
            try:
                require_activity_visible(user, a, e.run, 'assignment')
            except ApiError:
                continue
            latest = a.submissions.filter(enrollment=e).select_related('reviewer').first()
            window = submission_window(a, e, now=now)
            state = 'waiting' if latest and latest.status == 'submitted' else 'graded' if latest and latest.status == 'graded' else 'revision' if latest and latest.status == 'returned' and window['can_submit'] else window['phase']
            tasks.append({**base, 'id': f'assignment:{a.id}:{e.id}', 'kind': 'assignment', 'title': a.title, 'state': state,
                          'due_at': window['due_at'], 'closes_at': window['closes_at'], 'source': window['source'],
                          'review_due_at': latest.review_due_at if latest and latest.status == 'submitted' else None,
                          'review_overdue': bool(latest and latest.status == 'submitted' and latest.review_due_at and latest.review_due_at <= now),
                          'reviewer': display_name(latest.reviewer) if latest and latest.reviewer else None, 'reviewer_role_label': role_label(latest.reviewer, teaching=True) if latest and latest.reviewer else '',
                          'target': f'/#course={e.course_id}&run={e.run_id}&tab=assignments&activity={a.id}'})
        for q in e.course._agenda_quizzes:
            try:
                require_activity_visible(user, q, e.run, 'quiz')
            except ApiError:
                continue
            from .models import ActivitySchedule
            settings = ActivitySchedule.objects.filter(run=e.run, quiz=q).first() or q
            active = q.attempts.filter(enrollment=e, status='active').first()
            finished = q.attempts.filter(enrollment=e, status='finished').exists()
            closes = settings.closes_at
            if e.run.ends_at:
                closes = min(closes, e.run.ends_at) if closes else e.run.ends_at
            if active:
                closes = active.deadline_at
            state = 'active_quiz' if active else 'graded' if finished else 'closed' if closes and closes <= now else 'not_started' if settings.opens_at and settings.opens_at > now else 'open'
            tasks.append({**base, 'id': f'quiz:{q.id}:{e.id}', 'kind': 'quiz', 'title': q.title, 'state': state,
                          'due_at': closes, 'closes_at': closes, 'opens_at': settings.opens_at,
                          'target': f'/#course={e.course_id}&run={e.run_id}&tab=quizzes&activity={q.id}'})
    return sorted(tasks, key=lambda item: (item['state'] == 'graded', item.get('review_due_at') or item['closes_at'] or item['due_at'] or datetime.max.replace(tzinfo=now.tzinfo)))


@require_GET
@api
def agenda(request):
    authenticated(request)
    finalize_due_attempts(QuizAttempt.objects.filter(student=request.user))
    tasks = student_tasks(request.user)
    review = pending_reviews(request.user)
    now = timezone.now()
    return JsonResponse({'student_tasks': tasks, 'review_counts': {'pending': review.count(), 'overdue': review.filter(review_due_at__lte=now).count()},
                         'server_now': now})
