from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods
from common import api, authenticated, body, text, integer, boolean, ApiError, query_integer
from accounts.identity import display_name
from courses.access import require_run, resolve_run, require_learning_enrollment, can_manage_course, can_manage_run
from courses.models import Course, CourseRun, Enrollment
from learning.models import Lesson
from learning.services import require_lesson_visible
from assessment.models import Assignment, Submission
from assessment.views import submission_data, grade_submission
from assessment.deadline_views import managed_runs, pending_reviews
from communication.services import audit
from .models import AttentionPolicy, LessonPulse, AssignmentRubric
from .services import manager, home_data, question_rows, course_scope


@require_GET
@api
def home(request):
    authenticated(request)
    return JsonResponse(home_data(request.user, request.GET.get('personal') == '1'))


@require_GET
@api
def questions(request):
    authenticated(request); manager(request.user)
    run_id = query_integer(request, 'run_id', 1, 2**63-1) if request.GET.get('run_id') else None
    if run_id:
        get_object_or_404(managed_runs(request.user), pk=run_id)
    rows = question_rows(request.user, run_id)
    state = request.GET.get('state', 'waiting')
    if state not in ['all', 'waiting', 'answered', 'resolved']:
        raise ApiError('Неизвестный статус вопроса')
    if state != 'all':
        rows = [r for r in rows if r['state'] == state]
    page = query_integer(request, 'page', 1, 100000, 1)
    return JsonResponse({'questions': rows[(page-1)*20:page*20], 'total': len(rows), 'page': page,
                         'next_page': page+1 if page*20 < len(rows) else None})


@require_http_methods(['GET', 'PUT'])
@api
def policy(request, run_id):
    authenticated(request); manager(request.user)
    run = get_object_or_404(managed_runs(request.user), pk=run_id)
    if request.method == 'PUT':
        data = body(request)
        values = {'inactive_days': integer(data, 'inactive_days', 0, 365), 'missing_count': integer(data, 'missing_count', 0, 100),
                  'low_score_percent': integer(data, 'low_score_percent', 0, 100), 'updated_by': request.user}
        with transaction.atomic():
            row, _ = AttentionPolicy.objects.update_or_create(run=run, defaults=values)
            audit(request.user, run.course, 'attention.policy_updated', {'run_id': run.id, **{k: v for k, v in values.items() if k != 'updated_by'}})
    else:
        row = AttentionPolicy.objects.filter(run=run).first()
    return JsonResponse({'inactive_days': row.inactive_days if row else 0, 'missing_count': row.missing_count if row else 2,
                         'low_score_percent': row.low_score_percent if row else 0, 'run': run.title})


@require_http_methods(['GET', 'PUT'])
@api
def pulse(request, lesson_id):
    lesson = get_object_or_404(Lesson.objects.select_related('course'), pk=lesson_id)
    run = resolve_run(request, lesson.course); require_run(request, run)
    require_lesson_visible(request.user, lesson, run)
    managing = can_manage_run(request.user, run)
    if managing:
        if request.method != 'GET':
            raise ApiError('Оценку понятности оставляет студент в своём прохождении', 403)
        rows = LessonPulse.objects.filter(lesson=lesson, enrollment__run=run).select_related('enrollment__student').order_by('-updated_at')
        return JsonResponse({'can_manage': True, 'total': rows.count(), 'counts': {r['choice']: r['n'] for r in rows.values('choice').annotate(n=Count('id'))},
            'notes': [{'id': p.id, '_content_kind': 'lesson_feedback', 'course_id': lesson.course_id,
                       'student': display_name(p.enrollment.student), 'choice': p.choice, 'note': p.note,
                       'updated_at': p.updated_at} for p in rows.exclude(note='')[:20]]})
    e = require_learning_enrollment(request, run, allow_after_end=True)
    if request.method == 'PUT':
        data = body(request)
        choice = text(data, 'choice', 12, True)
        if choice not in ['clear', 'hard', 'example']:
            raise ApiError('Выберите оценку понятности')
        LessonPulse.objects.update_or_create(lesson=lesson, enrollment=e, defaults={'choice': choice, 'note': text(data, 'note', 1000)})
    p = LessonPulse.objects.filter(lesson=lesson, enrollment=e).first()
    return JsonResponse({'can_manage': False, 'choice': p.choice if p else '', 'note': p.note if p else ''})


def rubric_data(assignment):
    r = AssignmentRubric.objects.filter(assignment=assignment).first()
    return {'version': r.version if r else 0, 'criteria': r.criteria if r else [], 'locked': assignment.submissions.exists(), 'max_score': assignment.max_score}


@require_http_methods(['GET', 'PUT'])
@api
def rubric(request, assignment_id):
    assignment = get_object_or_404(Assignment.objects.select_related('course'), pk=assignment_id)
    run = resolve_run(request, assignment.course); require_run(request, run)
    if not can_manage_run(request.user, run):
        from learning.services import require_activity_visible
        require_activity_visible(request.user, assignment, run, 'assignment')
    if request.method == 'PUT':
        if not can_manage_course(request.user, assignment.course):
            raise ApiError('Критерии изменяет редактор курса', 403)
        data = body(request)
        with transaction.atomic():
            assignment = Assignment.objects.select_for_update().get(pk=assignment.id)
            current = rubric_data(assignment)
            if current['locked']:
                raise ApiError('После первой сдачи критерии зафиксированы. Создайте новое задание.', 409)
            if integer(data, 'version', 0, 2**31-1) != current['version']:
                raise ApiError('Критерии уже изменились. Обновите страницу.', 409)
            values = data.get('criteria')
            if not isinstance(values, list) or len(values) > 20:
                raise ApiError('Укажите до 20 критериев')
            criteria = []
            for i, v in enumerate(values):
                if not isinstance(v, dict):
                    raise ApiError('Неверный критерий')
                criteria.append({'id': str(i+1), 'label': text(v, 'label', 200, True), 'max': integer(v, 'max', 1, 10000)})
            if criteria and sum(v['max'] for v in criteria) != assignment.max_score:
                raise ApiError('Сумма критериев должна совпадать с максимальным баллом задания')
            AssignmentRubric.objects.update_or_create(assignment=assignment, defaults={'version': current['version']+1, 'criteria': criteria})
            audit(request.user, assignment.course, 'assignment.rubric_updated', {'assignment_id': assignment.id, 'version': current['version']+1})
    return JsonResponse(rubric_data(assignment))


@require_http_methods(['GET', 'PUT'])
@api
def review(request, submission_id):
    authenticated(request); manager(request.user)
    s = get_object_or_404(Submission.objects.select_related('assignment__course', 'enrollment__run', 'student', 'reviewer'),
                          pk=submission_id, enrollment__run__in=managed_runs(request.user))
    if request.method == 'PUT':
        integer(body(request), 'expected_version', 0, 2**31-1)
        return grade_submission(request, s.id)
    next_s = pending_reviews(request.user).exclude(id=s.id).order_by('review_due_at', 'submitted_at').first()
    return JsonResponse({'submission': submission_data(s), 'assignment': {'id': s.assignment_id, 'title': s.assignment.title,
        'description': s.assignment.description, 'max_score': s.assignment.max_score}, 'course': s.assignment.course.title,
        'run': s.enrollment.run.title, 'run_id': s.enrollment.run_id, 'course_id': s.assignment.course_id,
        'rubric': rubric_data(s.assignment), 'next_id': next_s.id if next_s else None})


@require_GET
@api
def search(request):
    authenticated(request)
    q = request.GET.get('q', '').strip()[:80]
    if len(q) < 2:
        return JsonResponse({'results': []})
    from courses.access import can_teach
    courses = Course.objects.filter(Q(is_published=True) | Q(id__in=course_scope(request.user))) if can_teach(request.user) else Course.objects.filter(is_published=True)
    results = []
    for c in courses.filter(title__icontains=q).distinct()[:10]:
        target_run = None
        if not can_manage_course(request.user, c):
            enrollment = c.enrollments.filter(student=request.user, status__in=['active', 'completed']).order_by('-last_seen_at').first()
            target_run = enrollment.run_id if enrollment else None
            if can_teach(request.user) and not target_run:
                target_run = managed_runs(request.user).filter(course=c).values_list('id', flat=True).first()
        results.append({'kind': 'Курс', 'title': c.title, 'detail': 'Опубликован' if c.is_published else 'Черновик',
                        'target': f'/#course={c.id}'+(f'&run={target_run}' if target_run else '')})
    if can_teach(request.user):
        rows = Enrollment.objects.filter(run__in=managed_runs(request.user)).select_related('student', 'run', 'course')
        for word in q.split():
            rows = rows.filter(Q(student__last_name__icontains=word) | Q(student__first_name__icontains=word) | Q(student__username__icontains=word))
        results += [{'kind': 'Ученик', 'title': display_name(e.student), 'detail': f'{e.course.title} · {e.run.title}',
            'target': f'/#course={e.course_id}&run={e.run_id}&tab=results&student={e.student_id}'} for e in rows[:10]]
    return JsonResponse({'results': results})


@require_GET
@api
def question_insights(request):
    authenticated(request); manager(request.user)
    from analytics.services import context
    from assessment.models import QuizAttempt, Question
    role, runs, enrollments, options, dates = context(request)
    if role == 'student':
        raise ApiError('Статистика вопросов доступна преподавателю', 403)
    attempts = QuizAttempt.objects.filter(enrollment_id__in=[e.id for e in enrollments], status='finished').select_related('quiz').order_by('quiz_id', 'enrollment_id', 'attempt_no')
    seen, grouped = set(), {}
    for a in attempts:
        key = (a.quiz_id, a.enrollment_id)
        if key in seen:
            continue
        seen.add(key)
        if a.finished_at and dates['from'] <= timezone_local_date(a.finished_at, dates) <= dates['to']:
            grouped.setdefault(a.quiz_id, []).append(a)
    qs = Question.objects.filter(quiz_id__in=grouped).select_related('quiz__course').order_by('quiz_id', 'position', 'id')
    page = query_integer(request, 'page', 1, 100000, 1); total = qs.count()
    rows = []
    for q in qs[(page-1)*20:page*20]:
        records = grouped[q.quiz_id]
        counts = [0]*len(q.options); unanswered = 0
        for a in records:
            answer = a.answers.get(str(q.id))
            if type(answer) is int and 0 <= answer < len(counts): counts[answer] += 1
            else: unanswered += 1
        rows.append({'id': q.id, 'body': q.body, 'quiz': q.quiz.title, 'course': q.quiz.course.title, 'samples': len(records),
            'correct_percent': round(100*counts[q.correct_index]/len(records), 1) if records else None, 'unanswered': unanswered,
            'options': [{'label': label, 'count': counts[i], 'correct': i == q.correct_index} for i, label in enumerate(q.options)]})
    return JsonResponse({'questions': rows, 'total': total, 'next_page': page+1 if page*20 < total else None})


def timezone_local_date(value, dates):
    from zoneinfo import ZoneInfo
    return value.astimezone(ZoneInfo(dates['timezone'])).date()
