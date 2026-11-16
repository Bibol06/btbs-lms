from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from common import api, authenticated, body, text, integer, boolean, raw_text, ApiError, query_integer
from courses.models import Course, CourseImage, default_run
from courses.access import can_manage_course, require_run, resolve_run
from learning.models import Module, Lesson, Step, LessonMaterial
from assessment.models import Assignment, Quiz, Question
from assessment.views import question_values
from codejudge.models import CodeProblem, TestCase
from communication.services import audit
from .models import BankQuestion, AssignmentRubric
from .services import course_scope, manager


@require_http_methods(['GET', 'POST'])
@api
def bank(request):
    authenticated(request); manager(request.user)
    editable = course_scope(request.user).filter(id__in=[c.id for c in course_scope(request.user) if can_manage_course(request.user, c)])
    if request.method == 'POST':
        data = body(request)
        course = get_object_or_404(editable, pk=integer(data, 'course_id', 1, 2**63-1))
        value = question_values({'questions': [data]})[0]; value.pop('position')
        with transaction.atomic():
            previous = None
            if data.get('previous_id'):
                previous = get_object_or_404(BankQuestion.objects.select_for_update(), pk=integer(data, 'previous_id', 1, 2**63-1), course=course)
                if not previous.is_current:
                    raise ApiError('Вопрос уже изменён другим редактором. Обновите банк.', 409)
                previous.is_current = False; previous.save(update_fields=['is_current'])
            values = {'course': course, **value, 'category': text(data, 'category', 100), 'is_ready': boolean(data, 'is_ready', True)}
            if previous:
                values.update(family=previous.family, version=previous.version+1)
            row = BankQuestion.objects.create(**values)
            audit(request.user, course, 'question_bank.saved', {'question_id': row.id, 'version': row.version})
        return JsonResponse({'id': row.id, 'version': row.version}, status=201)
    rows = BankQuestion.objects.filter(course__in=editable, is_current=True).select_related('course').order_by('-id')
    if request.GET.get('course_id'):
        rows = rows.filter(course_id=query_integer(request, 'course_id', 1, 2**63-1))
    if request.GET.get('q'):
        from django.db.models import Q
        rows = rows.filter(Q(body__icontains=request.GET['q'][:150]) | Q(category__icontains=request.GET['q'][:150]))
    page = query_integer(request, 'page', 1, 100000, 1); total = rows.count()
    return JsonResponse({'questions': list(rows[(page-1)*30:page*30].values('id', 'course_id', 'course__title', 'version', 'body', 'category', 'options', 'correct_index', 'is_ready')),
        'courses': list(editable.values('id', 'title')), 'total': total, 'next_page': page+1 if page*30 < total else None})


@require_POST
@api
def clone_course(request, course_id):
    authenticated(request)
    source = get_object_or_404(Course, pk=course_id)
    if not can_manage_course(request.user, source):
        raise ApiError('Копирование доступно редактору курса', 403)
    data = body(request)
    from course_media import copied_course_files
    with copied_course_files() as copy_file, transaction.atomic():
        source = Course.objects.select_for_update().get(pk=source.id)
        target = Course.objects.create(title=text(data, 'title', 200, True), description=source.description, teacher=request.user, is_published=False,
            content_language=source.content_language, content_translation=source.content_translation)
        run = default_run(target)
        assignments, quizzes, problems, materials, modules, lessons = {}, {}, {}, {}, {}, {}
        for a in source.assignments.all():
            assignments[a.id] = Assignment.objects.create(course=target, title=a.title, description=a.description,
                max_score=a.max_score, max_attempts=a.max_attempts, review_hours=a.review_hours, is_published=a.is_published)
            rubric = AssignmentRubric.objects.filter(assignment=a).first()
            if rubric:
                AssignmentRubric.objects.create(assignment=assignments[a.id], criteria=rubric.criteria, version=1)
        for q in source.quizzes.all():
            quizzes[q.id] = Quiz.objects.create(course=target, title=q.title, max_attempts=q.max_attempts, time_limit_sec=q.time_limit_sec, is_published=q.is_published)
            Question.objects.bulk_create([Question(quiz=quizzes[q.id], body=v.body, options=v.options, correct_index=v.correct_index, position=v.position) for v in q.questions.all()])
        for p in CodeProblem.objects.filter(course=source):
            problems[p.id] = CodeProblem.objects.create(course=target, title=p.title, statement=p.statement, starter_code=p.starter_code, max_attempts=p.max_attempts)
            TestCase.objects.bulk_create([TestCase(problem=problems[p.id], stdin=t.stdin, expected=t.expected, is_sample=t.is_sample, position=t.position) for t in p.test_cases.all()])
        for m in source.modules.all():
            modules[m.id] = Module.objects.create(course=target, title=m.title, position=m.position, is_published=m.is_published)
        for m in source.modules.exclude(prerequisite=None):
            if m.prerequisite_id in modules:
                modules[m.id].prerequisite = modules[m.prerequisite_id]; modules[m.id].save(update_fields=['prerequisite'])
        for lesson in source.lessons.all():
            lessons[lesson.id] = Lesson.objects.create(course=target, module=modules.get(lesson.module_id), title=lesson.title, content=lesson.content,
                video_url=lesson.video_url, position=lesson.position, is_published=lesson.is_published)
            for f in lesson.materials.all():
                copied = LessonMaterial(lesson=lessons[lesson.id], title=f.title, is_inline=f.is_inline)
                copied.file = copy_file(f.file, copied)
                copied.save()
                materials[f.id] = copied
        from learning.image_views import rewrite_image_references
        target.description = rewrite_image_references(target.description, materials)
        from courses.image_views import rewrite_description_images
        description_images = {}
        for image in source.description_images.all():
            copied = CourseImage(course=target, title=image.title)
            copied.file = copy_file(image.file, copied)
            copied.save()
            description_images[image.id] = copied
        target.description = rewrite_description_images(target.description, description_images)
        target.save(update_fields=['description'])
        for copied_lesson in lessons.values():
            copied_lesson.content = rewrite_image_references(copied_lesson.content, materials)
            copied_lesson.save(update_fields=['content'])
        for s in Step.objects.filter(lesson__course=source):
            Step.objects.create(lesson=lessons[s.lesson_id], title=s.title, kind=s.kind, content=rewrite_image_references(s.content, materials), video_url=s.video_url,
                material=materials.get(s.material_id), assignment=assignments.get(s.assignment_id), quiz=quizzes.get(s.quiz_id),
                code_problem=problems.get(s.code_problem_id), position=s.position, is_published=s.is_published, required=s.required, pass_percent=s.pass_percent)
        audit(request.user, target, 'course.cloned', {'source_id': source.id})
    return JsonResponse({'course_id': target.id, 'run_id': run.id, 'title': target.title}, status=201)


@require_http_methods(['GET', 'POST'])
@api
def preview(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if not request.GET.get('run_id'):
        from assessment.deadline_views import managed_runs
        authenticated(request)
        run = managed_runs(request.user).filter(course=course).order_by('-kind', 'id').first()
        if not run:
            raise ApiError('Нет доступного запуска курса для предпросмотра', 403)
    else:
        run = resolve_run(request, course)
    require_run(request, run, manage=True)
    steps = Step.objects.filter(lesson__course=course, lesson__is_published=True, is_published=True).exclude(lesson__module__is_published=False).select_related(
        'lesson__module', 'assignment', 'quiz', 'code_problem', 'material')
    rows = []
    now = timezone.now()
    completed = set()
    data = body(request) if request.method == 'POST' else {}
    if request.method == 'POST':
        ids = data.get('completed', [])
        if not isinstance(ids, list) or len(ids) > 2000 or any(type(i) is not int for i in ids):
            raise ApiError('Неверные пробные отметки')
        completed = set(ids)
    for s in steps.order_by('lesson__module__position', 'lesson__position', 'position'):
        if s.assignment_id and not s.assignment.is_published or s.quiz_id and not s.quiz.is_published:
            continue
        module = s.lesson.module
        reason = 'Обучение ещё не началось' if run.starts_at and run.starts_at > now else 'Обучение завершено' if run.ends_at and run.ends_at <= now else ''
        if module:
            from courses.pacing import module_release
            release = module_release(module, run)
            if not release['scheduled'] or release['opens_at'] and release['opens_at'] > now:
                reason = 'Модуль откроется позже'
        if module and module.prerequisite_id:
            required = set(steps.filter(lesson__module_id=module.prerequisite_id, required=True).values_list('id', flat=True))
            if not module.prerequisite.is_published or not required.issubset(completed):
                reason = 'Сначала завершите предыдущий модуль в предпросмотре'
        row = {'id': s.id, 'title': s.title, 'kind': s.kind, 'module': module.title if module else 'Программа курса', 'lesson': s.lesson.title,
            'reason': reason, 'action_reason': '', 'required': s.required, 'content': s.content, 'video_url': s.video_url, 'pass_percent': s.pass_percent}
        if s.material:
            from learning.views import serialize_material
            row['material'] = {**serialize_material(s.material), 'url': f'/api/learning/materials/{s.material_id}/open/?run_id={run.id}'}
        if s.assignment:
            from assessment.views import activity_settings
            schedule = activity_settings(s.assignment, run, 'assignment')
            cutoff = schedule.cutoff_at if schedule.allow_late else schedule.due_at
            if cutoff and cutoff <= now:
                row['action_reason'] = 'Приём работ закрыт по расписанию запуска'
            row['assignment'] = {'title': s.assignment.title, 'description': s.assignment.description, 'max_score': s.assignment.max_score}
        if s.quiz:
            from assessment.views import activity_settings
            schedule = activity_settings(s.quiz, run, 'quiz')
            if schedule.opens_at and schedule.opens_at > now:
                row['action_reason'] = 'Тест ещё не открыт по расписанию запуска'
            elif schedule.closes_at and schedule.closes_at <= now:
                row['action_reason'] = 'Срок прохождения теста завершён'
            row['questions'] = list(s.quiz.questions.values('id', 'body', 'options'))
        if s.code_problem:
            row['problem'] = {'title': s.code_problem.title, 'statement': s.code_problem.statement, 'starter_code': s.code_problem.starter_code,
                              'samples': list(s.code_problem.test_cases.filter(is_sample=True).values('stdin', 'expected'))}
        rows.append(row)
    if request.method == 'POST' and data.get('step_id'):
        step_id = integer(data, 'step_id', 1, 2**63-1)
        row = next((r for r in rows if r['id'] == step_id), None)
        if not row:
            raise ApiError('Шаг скрыт от ученика', 404)
        if row['reason']:
            raise ApiError(row['reason'], 403)
        if row['action_reason']:
            raise ApiError(row['action_reason'], 403)
        s = steps.get(pk=step_id)
        if s.kind == 'quiz':
            answers = data.get('answers', {})
            if not isinstance(answers, dict):
                raise ApiError('Неверные ответы')
            questions = list(s.quiz.questions.all())
            score = sum(type(answers.get(str(q.id))) is int and answers[str(q.id)] == q.correct_index for q in questions)
            return JsonResponse({'score': score, 'total': len(questions), 'passed': bool(questions) and score*100 >= len(questions)*s.pass_percent, 'message': 'Пробный результат. В журнал не записан.'})
        if s.kind == 'code':
            from codejudge.views import CAPACITY
            from codejudge.runner import run_python
            if not CAPACITY.acquire(blocking=False):
                raise ApiError('Проверяющая система занята', 429)
            try:
                tests = list(s.code_problem.test_cases.all())
                output = run_python(raw_text(data, 'code', 20000, True), [t.stdin for t in tests])
                passed = sum(r['status'] == 'ok' and r['stdout'].strip() == t.expected.strip() for t, r in zip(tests, output))
                return JsonResponse({'score': passed, 'total': len(tests), 'passed': bool(tests) and passed == len(tests), 'message': 'Пробная проверка. Учебная отправка не создана.'})
            finally:
                CAPACITY.release()
        if s.kind == 'assignment' and boolean(data, 'simulate_review', False):
            score = integer(data, 'preview_score', 0, s.assignment.max_score)
            return JsonResponse({'score': score, 'total': s.assignment.max_score, 'passed': score*100 >= s.assignment.max_score*s.pass_percent,
                                 'message': 'Сымитирована проверка преподавателя. Реальная оценка не создаётся.'})
        return JsonResponse({'passed': s.kind != 'assignment', 'message': 'Пробная отправка: реальная работа и оценка не создаются.' if s.kind == 'assignment' else 'Пробная отметка сохранена только в предпросмотре.'})
    return JsonResponse({'course': course.title, 'run': run.title, 'run_id': run.id, 'steps': rows})
