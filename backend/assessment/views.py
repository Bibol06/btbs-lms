from django.views.decorators.clickjacking import xframe_options_sameorigin
from accounts.identity import display_name, role_label, identity_data
from datetime import timedelta
from pathlib import Path

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from common import api, authenticated, body, text, integer, boolean, date, ApiError
from courses.access import can_manage_course, can_manage_run, resolve_run, require_run, require_learning_enrollment
from courses.models import Course, Enrollment
from learning.models import Lesson
from learning.upload_views import valid_file_signature
from .models import Assignment, Submission, Quiz, Question, QuizAttempt, LessonProgress, ActivitySchedule, GradeReview
from .deadlines import deadline_values, submission_window, default_reviewer, review_state, grant_extension
from .quiz_services import finalize_due_attempts, finalize_locked_attempt


def access(request, course, manage=False):
    run = resolve_run(request, course)
    require_run(request, run, manage=manage)
    return run


def student_enrollment(request, course):
    return require_learning_enrollment(request, resolve_run(request, course), lock=True)


def activity_settings(activity, run, kind):
    override = ActivitySchedule.objects.filter(run=run, **{kind: activity}).first()
    return override or activity


def require_content_editor(request, course):
    authenticated(request)
    if not can_manage_course(request.user, course):
        raise ApiError('Нет прав редактора содержания курса', 403)


def submission_data(s):
    return {'id': s.id, 'review_version': s.review_version, 'rubric_result': s.rubric_result, 'student_id': s.student_id, 'student': display_name(s.student), 'student_role_label': role_label(s.student),
            'attempt_no': s.attempt_no, 'text_answer': s.text_answer,
            'file_url': f'/api/study/submissions/{s.id}/file/' if s.file else '',
            'file_name': Path(s.file.name).name if s.file else '',
            'submitted_at': s.submitted_at, 'score': s.score, 'feedback': s.feedback,
            'graded_at': s.graded_at, 'status': s.status, 'is_late': s.is_late, 'due_at_snapshot': s.due_at_snapshot,
            'review_due_at': s.review_due_at, 'review_state': review_state(s), 'reviewer_id': s.reviewer_id,
            'reviewer': display_name(s.reviewer) if s.reviewer else None, 'reviewer_role_label': role_label(s.reviewer, teaching=True), 'revision_due_at': s.revision_due_at, 'reviews': [{'action': r.action, 'score': r.score, 'feedback': r.feedback, 'rubric_result': r.rubric_result, 'created_at': r.created_at, 'reviewer__username': r.reviewer.username if r.reviewer else '', 'reviewer': display_name(r.reviewer), 'reviewer_role_label': role_label(r.reviewer, teaching=True), 'revision_due_at': r.revision_due_at} for r in reviews_of(s)]}


def reviews_of(s):
    # List views prefetch reviews into s.prefetched_reviews (newest first).
    reviews = getattr(s, 'prefetched_reviews', None)
    return reviews if reviews is not None else s.reviews.select_related('reviewer').order_by('-id')


def attempt_data(a):
    return {'id': a.id, 'attempt_no': a.attempt_no, 'status': a.status, 'auto_submitted': a.auto_submitted,
            'score': a.score, 'max_score': a.max_score, 'deadline_at': a.deadline_at,
            'finished_at': a.finished_at, 'server_now': timezone.now()}


def progress_data(course, student_id, run=None):
    from courses.models import default_run
    from learning.services import course_progress
    enrollment = Enrollment.objects.filter(course=course, student_id=student_id, run=run or default_run(course)).first()
    return course_progress(course, enrollment)


@require_GET
@api
def course_study(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    run = access(request, course)
    manage = can_manage_run(request.user, run)
    finalize_due_attempts(QuizAttempt.objects.filter(quiz__course=course, enrollment__run=run))
    enrollment = Enrollment.objects.filter(run=run, student=request.user).first()
    if enrollment:
        enrollment.run = run
    assignments = course.assignments.all()
    quizzes = course.quizzes.all()
    if not manage:
        assignments = assignments.filter(is_published=True)
        quizzes = quizzes.filter(is_published=True)
    from django.db.models import Count, Exists, Max, OuterRef, Prefetch
    from courses.models import RunCheckpoint
    from learning.models import Step
    from learning.services import require_activity_visible
    from .models import AssignmentExtension
    # Everything below is loaded once per table: only this run's records (and, for a
    # student, only their own) instead of every learner's work for every activity.
    placements = Prefetch('steps', queryset=Step.objects.select_related('lesson__module__prerequisite'))
    run._module_release_map = {row.module_id: row for row in run.module_releases.all()}
    run._prerequisite_cache = {}
    schedules = {('assignment' if row.assignment_id else 'quiz', row.assignment_id or row.quiz_id): row
                 for row in ActivitySchedule.objects.filter(run=run)}
    extensions = {x.assignment_id: x for x in AssignmentExtension.objects.filter(enrollment=enrollment)} if enrollment and not manage else {}
    work = Submission.objects.filter(enrollment__run=run).select_related('student', 'reviewer').prefetch_related(
        Prefetch('reviews', queryset=GradeReview.objects.select_related('reviewer').order_by('-id'), to_attr='prefetched_reviews'))
    if not manage:
        work = work.filter(student=request.user)
    result = []
    for a in assignments.prefetch_related(placements, Prefetch('submissions', queryset=work, to_attr='run_submissions')):
        try:
            require_activity_visible(request.user, a, run, 'assignment', manager=manage)
        except ApiError:
            continue
        settings = schedules.get(('assignment', a.id)) or a
        result.append({'id': a.id, 'title': a.title, 'description': a.description,
                       'due_at': settings.due_at, 'allow_late': settings.allow_late, 'cutoff_at': settings.cutoff_at,
                       'review_hours': settings.review_hours, 'window': submission_window(a, enrollment, settings, personal=extensions.get(a.id)) if enrollment and not manage else None, 'max_score': a.max_score, 'max_attempts': settings.max_attempts,
                       'is_published': a.is_published, 'submissions': [submission_data(s) for s in a.run_submissions]})
    quiz_result = []
    own_attempts = QuizAttempt.objects.filter(student=request.user, enrollment__run=run)
    quizzes = quizzes.prefetch_related(placements, 'questions', Prefetch('attempts', queryset=own_attempts, to_attr='own_attempts'),
                                       Prefetch('checkpoints', queryset=RunCheckpoint.objects.only('id', 'run_id', 'quiz_id')))
    if manage:
        quizzes = quizzes.annotate(any_attempts=Exists(QuizAttempt.objects.filter(quiz=OuterRef('pk'))))
    for q in quizzes:
        try:
            require_activity_visible(request.user, q, run, 'quiz', manager=manage)
        except ApiError:
            continue
        settings = schedules.get(('quiz', q.id)) or q
        questions = q.questions.all()
        item = {'id': q.id, 'title': q.title, 'max_attempts': settings.max_attempts,
                'time_limit_sec': settings.time_limit_sec, 'opens_at': settings.opens_at, 'closes_at': settings.closes_at,
                'is_published': q.is_published, 'questions_count': len(questions),
                'attempts': [attempt_data(a) for a in q.own_attempts],
                'has_attempts': q.any_attempts if manage else False}
        if manage:
            item['questions'] = [{'id': x.id, 'body': x.body, 'options': x.options, 'correct_index': x.correct_index, 'position': x.position} for x in questions]
        quiz_result.append(item)
    from codejudge.models import CodeProblem, CodeSubmission, TestCase as CodeCase
    code_results = []
    problems = list(CodeProblem.objects.filter(course=course, steps__is_published=True, steps__lesson__is_published=True).distinct().prefetch_related(placements))
    ids = [p.id for p in problems]
    case_counts = dict(CodeCase.objects.filter(problem_id__in=ids).values('problem_id').annotate(n=Count('id')).values_list('problem_id', 'n')) if ids else {}
    best = dict(CodeSubmission.objects.filter(problem_id__in=ids, enrollment__student=request.user, enrollment__run=run)
                .exclude(status__in=['running', 'service_error']).values('problem_id').annotate(m=Max('passed')).values_list('problem_id', 'm')) if ids else {}
    for problem in problems:
        try:
            require_activity_visible(request.user, problem, run, 'code', manager=manage)
        except ApiError:
            continue
        code_results.append({'id': problem.id, 'title': problem.title, 'passed': best.get(problem.id), 'total': case_counts.get(problem.id, 0)})
    from communication.services import teacher_ids
    from django.contrib.auth import get_user_model
    reviewers = [{**identity_data(u, teaching=True), 'first_name': u.first_name, 'last_name': u.last_name} for u in get_user_model().objects.filter(id__in=teacher_ids(run))] if manage else []
    return JsonResponse({'reviewers': reviewers, 'assignments': result, 'quizzes': quiz_result, 'can_manage': manage,
                         'code_results': code_results, 'can_edit': can_manage_course(request.user, course), 'progress': progress_data(course, request.user.id, run)})


def assignment_values(data, current=None):
    values = {
        'title': text(data, 'title', 200, required=True, default=current.title if current else ''),
        'description': text(data, 'description', 50000, default=current.description if current else ''),
        'max_score': integer(data, 'max_score', 1, 10000, current.max_score if current else 100),
        'max_attempts': integer(data, 'max_attempts', 1, 100, current.max_attempts if current else 3),
        'is_published': boolean(data, 'is_published', current.is_published if current else False),
        **deadline_values(data, current),
    }
    if current and current.submissions.exists():
        if values['max_score'] != current.max_score or values['max_attempts'] != current.max_attempts:
            raise ApiError('После сдачи работ нельзя менять шкалу оценки или лимит попыток')
    return values


@require_POST
@api
def create_assignment(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    require_content_editor(request, course)
    assignment = Assignment.objects.create(course=course, **assignment_values(body(request)))
    return JsonResponse({'id': assignment.id, 'message': 'Задание создано'}, status=201)


@require_http_methods(['PATCH', 'DELETE'])
@api
def manage_assignment(request, assignment_id):
    with transaction.atomic():
        a = get_object_or_404(Assignment.objects.select_for_update(), pk=assignment_id)
        require_content_editor(request, a.course)
        if request.method == 'DELETE':
            if a.submissions.exists():
                raise ApiError('Задание с работами нельзя удалить. Снимите его с публикации.')
            a.delete()
        else:
            for key, value in assignment_values(body(request), a).items():
                setattr(a, key, value)
            from workspace.models import AssignmentRubric
            rubric = AssignmentRubric.objects.filter(assignment=a).first()
            if rubric and rubric.criteria and sum(c['max'] for c in rubric.criteria) != a.max_score:
                raise ApiError('Максимум должен совпадать с суммой критериев. Сначала измените или очистите критерии.')
            a.save()
    return JsonResponse({'message': 'Задание обновлено'})


@require_POST
@api
def submit_assignment(request, assignment_id):
    authenticated(request)
    with transaction.atomic():
        a = get_object_or_404(Assignment.objects.select_for_update(), pk=assignment_id)
        enrollment = require_learning_enrollment(request, resolve_run(request, a.course), lock=True, allow_after_end=True)
        from learning.services import require_activity_visible
        require_activity_visible(request.user, a, enrollment.run, 'assignment')
        settings = activity_settings(a, enrollment.run, 'assignment')
        if not a.is_published:
            raise ApiError('Задание не опубликовано', 404)
        window = submission_window(a, enrollment, settings)
        if not window['can_submit']:
            raise ApiError('Приём работ закрыт. Попросите преподавателя назначить индивидуальный срок.')
        records = a.submissions.filter(enrollment=enrollment)
        count = records.count()
        if records.exclude(status='returned').count() >= settings.max_attempts:
            raise ApiError('Все попытки сдачи использованы')
        answer = text(request.POST, 'text_answer', 50000)
        file = request.FILES.get('file')
        if not answer and not file:
            raise ApiError('Добавьте текст ответа или файл')
        if file:
            ext = Path(file.name).suffix.lower()
            if ext not in {'.pdf', '.docx', '.pptx', '.jpg', '.jpeg', '.png'}:
                raise ApiError('Ответ: PDF, DOCX, PPTX, JPG или PNG')
            if not 0 < file.size <= 20 * 1024 * 1024 or not valid_file_signature(file, ext):
                raise ApiError('Некорректный файл или размер больше 20 МБ')
        revision = records.filter(status='returned', revision_submission__isnull=True).order_by('-id').first()
        s = Submission(assignment=a, enrollment=enrollment, student=request.user, text_answer=answer, attempt_no=count + 1,
                       due_at_snapshot=window['due_at'], is_late=bool(window['due_at'] and timezone.now() >= window['due_at']),
                       review_due_at=timezone.now() + timedelta(hours=settings.review_hours), reviewer=default_reviewer(enrollment.run),
                       revision_of=revision)
        try:
            if file:
                s.file.save(file.name, file, save=False)
            s.save()
        except Exception:
            if s.file:
                s.file.delete(save=False)
            raise
        from communication.services import notify, teacher_ids, course_target
        notify(f'submission:{s.id}', 'submission', a.course, teacher_ids(enrollment.run), 'Новая работа на проверку', course_target(a.course, enrollment.run, 'assignments'), enrollment.run)
        from analytics.tracking import record
        record(request.user, 'assignment_submitted', enrollment=enrollment, dedupe=f'submission:{s.id}')
    return JsonResponse({'message': 'Работа отправлена', 'submission': submission_data(s)}, status=201)


@require_http_methods(['PUT'])
@api
def grade_submission(request, submission_id):
    with transaction.atomic():
        s = get_object_or_404(Submission.objects.select_for_update(), pk=submission_id)
        require_run(request, s.enrollment.run, manage=True)
        data = body(request)
        if 'expected_version' in data and integer(data, 'expected_version', 0, 2**31-1) != s.review_version:
            raise ApiError('Работа уже изменена другим проверяющим. Обновите её перед сохранением.', 409)
        returned = boolean(data, 'return_for_revision', False)
        s.score = None if returned else integer(data, 'score', 0, s.assignment.max_score)
        from workspace.models import AssignmentRubric
        rubric = AssignmentRubric.objects.filter(assignment=s.assignment).first()
        s.rubric_result = {}
        if not returned and rubric and rubric.criteria:
            scores, comments = data.get('criteria_scores'), data.get('criteria_comments', {})
            if not isinstance(scores, dict) or not isinstance(comments, dict):
                raise ApiError('Оцените каждый критерий')
            result = []
            for c in rubric.criteria:
                result.append({**c, 'score': integer(scores, c['id'], 0, c['max']), 'comment': text(comments, c['id'], 1000)})
            if sum(c['score'] for c in result) != s.score:
                raise ApiError('Итоговый балл должен совпадать с суммой критериев')
            s.rubric_result = {'version': rubric.version, 'criteria': result}
        if returned:
            if s.assignment.submissions.filter(enrollment=s.enrollment, id__gt=s.id).exists():
                raise ApiError('Вернуть на доработку можно только последнюю отправку ученика')
            deadline = date(data, 'revision_due_at') if 'revision_due_at' in data else timezone.now() + timedelta(hours=72)
            grant_extension(s.assignment, s.enrollment, request.user, deadline, 'Доработка работы')
            s.revision_due_at = deadline
        else:
            s.revision_due_at = None
        s.status = 'returned' if returned else 'graded'
        s.feedback = text(data, 'feedback', 10000)
        s.graded_by, s.graded_at = request.user, timezone.now()
        s.review_version += 1
        s.save(update_fields=['score', 'feedback', 'graded_by', 'graded_at', 'status', 'revision_due_at', 'review_version', 'rubric_result'])
        review = GradeReview.objects.create(submission=s, reviewer=request.user, action=s.status, score=s.score, feedback=s.feedback, revision_due_at=s.revision_due_at, rubric_result=s.rubric_result)
        from analytics.tracking import record
        record(request.user, 'assignment_returned' if returned else 'assignment_reviewed', enrollment=s.enrollment, dedupe=f'review:{review.id}')
        from communication.services import notify, course_target
        notify(f'grade:{review.id}', 'grade', s.assignment.course, {s.student_id}, 'Работа возвращена на доработку' if returned else 'Работа проверена', course_target(s.assignment.course, s.enrollment.run, 'assignments'), s.enrollment.run)
        from learning.services import refresh_completion
        refresh_completion(s.enrollment)
    return JsonResponse({'message': 'Оценка сохранена', 'submission': submission_data(s)})


@require_GET
@api
@xframe_options_sameorigin
def submission_file(request, submission_id):
    s = get_object_or_404(Submission.objects.select_related('assignment__course'), pk=submission_id)
    require_run(request, s.enrollment.run)
    if s.student_id != request.user.id and not can_manage_run(request.user, s.enrollment.run):
        raise ApiError('Нет доступа к чужой работе', 403)
    if not s.file:
        raise ApiError('Файла нет', 404)
    from media_storage import private_file_response
    inline = Path(s.file.name).suffix.lower() in {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.mp4', '.webm'}
    return private_file_response(s.file, attachment=not inline, filename=Path(s.file.name).name)


def quiz_values(data, current=None):
    result = {
        'title': text(data, 'title', 200, required=True, default=current.title if current else ''),
        'max_attempts': integer(data, 'max_attempts', 1, 100, current.max_attempts if current else 3),
        'time_limit_sec': integer(data, 'time_limit_sec', 60, 14400, current.time_limit_sec if current else 900),
        'is_published': boolean(data, 'is_published', current.is_published if current else False),
        'opens_at': date(data, 'opens_at') if 'opens_at' in data or not current else current.opens_at,
        'closes_at': date(data, 'closes_at') if 'closes_at' in data or not current else current.closes_at,
    }
    if result['opens_at'] and result['closes_at'] and result['closes_at'] <= result['opens_at']:
        raise ApiError('Закрытие теста должно быть позже открытия')
    return result


def question_values(data):
    questions = data.get('questions')
    if not isinstance(questions, list) or not 1 <= len(questions) <= 100:
        raise ApiError('Добавьте от 1 до 100 вопросов')
    result = []
    for index, q in enumerate(questions):
        if not isinstance(q, dict):
            raise ApiError('Неверный формат вопроса')
        options = q.get('options')
        if not isinstance(options, list) or not 2 <= len(options) <= 8:
            raise ApiError('Нужно от 2 до 8 вариантов ответа')
        if any(not isinstance(v, str) or not v.strip() or len(v) > 1000 for v in options):
            raise ApiError('Заполните все варианты ответа (до 1000 символов)')
        options = [v.strip() for v in options]
        if len(set(options)) != len(options):
            raise ApiError('Варианты ответа не должны повторяться')
        result.append({'body': text(q, 'body', 10000, required=True), 'options': options,
                       'correct_index': integer(q, 'correct_index', 0, len(options) - 1), 'position': index + 1})
    return result


@require_POST
@api
def create_quiz(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    require_content_editor(request, course)
    data = body(request)
    questions = question_values(data)
    with transaction.atomic():
        q = Quiz.objects.create(course=course, **quiz_values(data))
        Question.objects.bulk_create([Question(quiz=q, **v) for v in questions])
    return JsonResponse({'message': 'Тест создан', 'id': q.id}, status=201)


@require_http_methods(['PATCH', 'DELETE'])
@api
def manage_quiz(request, quiz_id):
    with transaction.atomic():
        q = get_object_or_404(Quiz.objects.select_for_update(), pk=quiz_id)
        require_content_editor(request, q.course)
        has_attempts = q.attempts.exists()
        if request.method == 'DELETE':
            if has_attempts:
                raise ApiError('Тест с попытками нельзя удалить. Снимите его с публикации.')
            q.delete()
        else:
            data = body(request)
            values = quiz_values(data, q)
            if has_attempts and ('questions' in data or any(values[k] != getattr(q, k) for k in values if k != 'is_published')):
                raise ApiError('После начала попыток можно менять только публикацию теста')
            questions = question_values(data) if 'questions' in data else None
            for key, value in values.items():
                setattr(q, key, value)
            q.save()
            if questions is not None:
                q.questions.all().delete()
                Question.objects.bulk_create([Question(quiz=q, **v) for v in questions])
    return JsonResponse({'message': 'Тест обновлён'})


@require_POST
@api
def start_quiz(request, quiz_id):
    authenticated(request)
    with transaction.atomic():
        q = get_object_or_404(Quiz.objects.select_for_update(), pk=quiz_id)
        enrollment = require_learning_enrollment(request, resolve_run(request, q.course), lock=True, allow_after_end=True)
        from learning.services import require_activity_visible
        require_activity_visible(request.user, q, enrollment.run, 'quiz')
        settings = activity_settings(q, enrollment.run, 'quiz')
        if not q.questions.exists():
            raise ApiError('В тесте пока нет вопросов')
        now = timezone.now()
        if not q.is_published:
            raise ApiError('Тест не опубликован', 404)
        attempts = q.attempts.filter(enrollment=enrollment)
        elapsed = attempts.select_for_update().filter(status='active', deadline_at__lte=now).first()
        if elapsed and finalize_locked_attempt(elapsed, q):
            return JsonResponse({'attempt': attempt_data(elapsed), 'questions': [], 'answers': {}, 'message': 'Тест завершён по таймеру. Сохранённые ответы проверены.'})
        require_learning_enrollment(request, enrollment.run, lock=True)
        if settings.opens_at and now < settings.opens_at:
            raise ApiError('Тест ещё не открыт')
        if settings.closes_at and now >= settings.closes_at:
            raise ApiError('Тест уже закрыт')
        attempt = attempts.filter(status='active').first()
        if attempt is None:
            if attempts.count() >= settings.max_attempts:
                raise ApiError('Все попытки теста использованы')
            deadline = now + timedelta(seconds=settings.time_limit_sec)
            if settings.closes_at:
                deadline = min(deadline, settings.closes_at)
            if enrollment.run.ends_at:
                deadline = min(deadline, enrollment.run.ends_at)
            attempt = QuizAttempt.objects.create(quiz=q, enrollment=enrollment, student=request.user, attempt_no=attempts.count() + 1,
                                                deadline_at=deadline, max_score=q.questions.count())
            from analytics.tracking import record
            record(request.user, 'quiz_started', enrollment=enrollment, dedupe=f'quiz-start:{attempt.id}')
        questions = list(q.questions.values('id', 'body', 'options', 'position'))
    return JsonResponse({'attempt': attempt_data(attempt), 'questions': questions, 'answers': attempt.answers})


@require_http_methods(['PATCH', 'POST'])
@api
def answer_quiz(request, attempt_id):
    authenticated(request)
    with transaction.atomic():
        # Same lock order as start_quiz; the quiz lock serializes edits and submissions.
        ref = get_object_or_404(QuizAttempt, pk=attempt_id, student=request.user)
        q = Quiz.objects.select_for_update().get(pk=ref.quiz_id)
        a = QuizAttempt.objects.select_for_update().get(pk=attempt_id)
        require_run(request, a.enrollment.run)
        if finalize_locked_attempt(a, q):
            return JsonResponse({'attempt': attempt_data(a), 'message': 'Время истекло. Сохранённые ответы проверены.'})
        if a.status != 'active':
            return JsonResponse({'attempt': attempt_data(a), 'message': 'Попытка уже завершена'})
        require_learning_enrollment(request, a.enrollment.run, lock=True)
        from learning.services import require_activity_visible
        require_activity_visible(request.user, q, a.enrollment.run, 'quiz')
        if not q.is_published:
            raise ApiError('Тест снят с публикации', 403)
        if a.status != 'active':
            return JsonResponse({'attempt': attempt_data(a), 'message': 'Попытка уже завершена'})
        now = timezone.now()
        data = body(request)
        if data.get('finish_saved') is True:
            return JsonResponse({'attempt': attempt_data(a), 'message': 'Время ещё не истекло. Ответы сохранены.'})
        answers = data.get('answers')
        if not isinstance(answers, dict):
            raise ApiError('Неверный формат ответов')
        questions = list(q.questions.all())
        allowed = {str(v.id): v for v in questions}
        if any(k not in allowed or type(v) is not int or not 0 <= v < len(allowed[k].options) for k, v in answers.items()):
            raise ApiError('Ответ не соответствует вопросу этого теста')
        answers_changed = a.answers != answers
        a.answers = answers
        if request.method == 'POST':
            a.score = sum(answers.get(str(v.id)) == v.correct_index for v in questions)
            a.status, a.finished_at = 'finished', now
        a.save(update_fields=['answers', 'score', 'status', 'finished_at'])
        if a.status == 'finished':
            from learning.services import refresh_completion
            refresh_completion(a.enrollment)
        if answers_changed or a.status == 'finished':
            from analytics.tracking import record
            key = f'quiz-finish:{a.id}' if a.status == 'finished' else f'quiz-answer:{a.id}:{int(now.timestamp())//60}'
            record(request.user, 'quiz_finished' if a.status == 'finished' else 'quiz_answered', enrollment=a.enrollment, dedupe=key)
    return JsonResponse({'attempt': attempt_data(a), 'message': 'Тест проверен' if request.method == 'POST' else 'Ответы сохранены'})


@require_POST
@api
def complete_lesson(request, lesson_id):
    lesson = get_object_or_404(Lesson.objects.select_related('course'), pk=lesson_id)
    with transaction.atomic():
        enrollment = student_enrollment(request, lesson.course)
        from learning.services import require_lesson_visible
        require_lesson_visible(request.user, lesson, enrollment.run)
        if not lesson.is_published:
            raise ApiError('Урок не опубликован', 404)
        completed = boolean(body(request), 'completed', True)
        if completed:
            LessonProgress.objects.get_or_create(lesson=lesson, student=request.user, enrollment=enrollment)
        else:
            LessonProgress.objects.filter(lesson=lesson, student=request.user, enrollment=enrollment).delete()
    return JsonResponse({'completed': completed, 'progress': progress_data(lesson.course, request.user.id, enrollment.run)})


@require_GET
@api
def course_report(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    run = access(request, course, manage=True)
    finalize_due_attempts(QuizAttempt.objects.filter(quiz__course=course, enrollment__run=run))
    assignments = list(course.assignments.filter(is_published=True))
    quizzes = list(course.quizzes.filter(is_published=True))
    submissions = list(Submission.objects.filter(assignment__in=assignments, enrollment__run=run).select_related('student'))
    attempts = list(QuizAttempt.objects.filter(quiz__in=quizzes, enrollment__run=run, status='finished'))
    from codejudge.models import CodeProblem, CodeSubmission
    problems = list(CodeProblem.objects.filter(course=course, steps__is_published=True, steps__lesson__is_published=True).distinct())
    code_submissions = list(CodeSubmission.objects.filter(problem__in=problems, enrollment__run=run).exclude(status__in=['running', 'service_error']))
    # Best results are grouped once, so the table costs O(records) instead of
    # O(students x activities x records), and progress is one batch for the whole group.
    best_score, best_quiz, best_code = {}, {}, {}
    for s in submissions:
        if s.score is not None:
            key = (s.student_id, s.assignment_id)
            best_score[key] = max(best_score.get(key, s.score), s.score)
    for a in attempts:
        key = (a.student_id, a.quiz_id)
        best_quiz[key] = max(best_quiz.get(key, a.score), a.score)
    for s in code_submissions:
        key = (s.enrollment_id, s.problem_id)
        best_code[key] = max(best_code.get(key, s.passed), s.passed)
    from learning.services import course_progress_many
    enrollments = list(course.enrollments.filter(run=run).select_related('student').order_by('student__username'))
    for enrollment in enrollments:
        enrollment.run = run
    progress = course_progress_many(enrollments)
    rows = []
    for enrollment in enrollments:
        student = enrollment.student
        rows.append({'student_id': student.id, 'student': student.username,
                     'display_name': display_name(student), 'role_label': role_label(student), 'status': enrollment.status, 'last_seen_at': enrollment.last_seen_at,
                     'progress': {key: progress[enrollment.id][key] for key in ('completed', 'total', 'percent')}, 'assignments': {str(a.id): best_score.get((student.id, a.id)) for a in assignments},
                     'quizzes': {str(q.id): best_quiz.get((student.id, q.id)) for q in quizzes},
                     'code': {str(p.id): best_code.get((enrollment.id, p.id)) for p in problems}})
    from django.db.models import Count
    from codejudge.models import TestCase as CodeCase
    from .models import Question
    question_counts = dict(Question.objects.filter(quiz__in=quizzes).values('quiz_id').annotate(n=Count('id')).values_list('quiz_id', 'n')) if quizzes else {}
    case_counts = dict(CodeCase.objects.filter(problem__in=problems).values('problem_id').annotate(n=Count('id')).values_list('problem_id', 'n')) if problems else {}
    return JsonResponse({'students': rows, 'assignments': [{'id': a.id, 'title': a.title, 'max_score': a.max_score} for a in assignments],
                         'quizzes': [{'id': q.id, 'title': q.title, 'max_score': question_counts.get(q.id, 0)} for q in quizzes],
                         'code_problems': [{'id': p.id, 'title': p.title, 'max_score': case_counts.get(p.id, 0)} for p in problems]})


@require_http_methods(['PUT'])
@api
def schedule(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    run = access(request, course, manage=True)
    data = body(request)
    kind = data.get('kind')
    if kind not in ['assignment', 'quiz']:
        raise ApiError('Неизвестный тип задания')
    activity = get_object_or_404(Assignment if kind == 'assignment' else Quiz, pk=integer(data, 'id', 1, 2**63-1), course=course)
    current = activity_settings(activity, run, kind)
    attempts = integer(data, 'max_attempts', 1, 100, current.max_attempts)
    seconds = integer(data, 'time_limit_sec', 60, 14400, getattr(current, 'time_limit_sec', 900))
    has_records = activity.submissions.filter(enrollment__run=run).exists() if kind == 'assignment' else activity.attempts.filter(enrollment__run=run).exists()
    if has_records and (attempts != current.max_attempts or (kind == 'quiz' and seconds != current.time_limit_sec)):
        raise ApiError('После начала попыток лимиты менять нельзя')
    opens, closes = date(data, 'opens_at'), date(data, 'closes_at')
    if opens and closes and closes <= opens:
        raise ApiError('Закрытие должно быть позже открытия')
    if kind == 'quiz' and run.checkpoints.filter(quiz=activity).exists():
        from courses.pacing import checkpoint_dates
        checkpoint = run.checkpoints.get(quiz=activity)
        if (opens, closes) != checkpoint_dates(checkpoint):
            raise ApiError('Даты контрольного теста меняются в учебном плане группы')
    with transaction.atomic():
        ActivitySchedule.objects.update_or_create(run=run, **{kind: activity}, defaults={
            **deadline_values(data, current), 'opens_at': opens, 'closes_at': closes,
            'max_attempts': attempts, 'time_limit_sec': seconds})
        from communication.services import audit
        audit(request.user, course, 'schedule.updated', {'run_id': run.id, 'kind': kind, 'id': activity.id})
    return JsonResponse({'message': 'Расписание группы сохранено'})


@require_GET
@api
def export_report(request, course_id):
    import csv
    import io
    import json
    from django.http import HttpResponse
    response = course_report(request, course_id)
    if response.status_code != 200:
        return response
    data = json.loads(response.content)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    def safe_cell(value):
        return "'" + value if isinstance(value, str) and value.startswith(('=', '+', '-', '@', '\t', '\r')) else value
    from localization import translate, request_language
    from content_localization import content_text
    from courses.models import Course
    course = get_object_or_404(Course, pk=course_id)
    language = request_language(request)
    writer.writerow([safe_cell(v) for v in [translate('Студент', language), translate('Прогресс, %', language)] + [content_text(a['title'], language, course) for a in data['assignments']] + [content_text(q['title'], language, course) for q in data['quizzes']] + [content_text(p['title'], language, course) for p in data['code_problems']]])
    for row in data['students']:
        name = safe_cell(row['display_name'])
        if name.startswith(('=', '+', '-', '@')):
            name = "'" + name
        writer.writerow([name, row['progress']['percent']] + [row['assignments'].get(str(a['id'])) for a in data['assignments']] + [row['quizzes'].get(str(q['id'])) for q in data['quizzes']] + [row['code'].get(str(p['id'])) for p in data['code_problems']])
    result = HttpResponse('\ufeff' + buffer.getvalue(), content_type='text/csv; charset=utf-8')
    result['Content-Disposition'] = 'attachment; filename="grades.csv"'
    return result


