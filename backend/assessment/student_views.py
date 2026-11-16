from accounts.identity import display_name, role_label
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from common import api
from courses.models import Course, Enrollment
from learning.services import course_progress, step_completed, visible_steps
from learning.models import StepProgress
from codejudge.models import CodeProblem
from .views import access, submission_data, attempt_data


@require_GET
@api
def student_report(request, course_id, student_id):
    course = get_object_or_404(Course, pk=course_id)
    run = access(request, course, manage=True)
    enrollment = get_object_or_404(Enrollment.objects.select_related('student', 'last_step'), course=course, run=run, student_id=student_id)
    from .quiz_services import finalize_due_attempts
    from .models import QuizAttempt
    finalize_due_attempts(QuizAttempt.objects.filter(enrollment=enrollment))
    student = enrollment.student
    published = set(visible_steps(course).values_list('id', flat=True))
    theory_dates = dict(StepProgress.objects.filter(enrollment=enrollment).values_list('step_id', 'completed_at'))
    lessons = []
    for lesson in course.lessons.select_related('module').prefetch_related('steps').order_by('module__position', 'position', 'id'):
        steps = []
        for step in lesson.steps.select_related('assignment', 'quiz', 'code_problem'):
            done = step_completed(step, enrollment)
            completed_at = theory_dates.get(step.id)
            if done and step.kind == 'assignment' and step.assignment_id:
                completed_at = step.assignment.submissions.filter(enrollment=enrollment, status='graded', score__gte=step.assignment.max_score * step.pass_percent / 100.0).order_by('graded_at').values_list('graded_at', flat=True).first()
            elif done and step.kind == 'quiz' and step.quiz_id:
                from django.db.models import F
                completed_at = step.quiz.attempts.filter(enrollment=enrollment, status='finished', score__gte=F('max_score') * step.pass_percent / 100.0).order_by('finished_at').values_list('finished_at', flat=True).first()
            elif done and step.kind == 'code' and step.code_problem_id:
                completed_at = step.code_problem.submissions.filter(enrollment=enrollment, status='accepted').order_by('created_at').values_list('created_at', flat=True).first()
            steps.append({'id': step.id, 'title': step.title, 'kind': step.kind, 'required': step.required,
                          'is_published': step.id in published, 'completed': done, 'completed_at': completed_at})
        required = [s for s in steps if s['required'] and s['is_published']]
        legacy_date = enrollment.lessonprogress_records.filter(lesson=lesson).values_list('completed_at', flat=True).first() if not steps else None
        lessons.append({'id': lesson.id, 'title': lesson.title, 'module': lesson.module.title if lesson.module else 'Основной раздел',
                        'steps': steps, 'completed': all(s['completed'] for s in required) if required else bool(legacy_date),
                        'completed_at': max((s['completed_at'] for s in required if s['completed_at']), default=legacy_date) if (required and all(s['completed'] for s in required)) or legacy_date else None})
    assignments = [{'id': a.id, 'title': a.title, 'max_score': a.max_score,
                    'submissions': [submission_data(s) for s in a.submissions.filter(enrollment=enrollment).select_related('student').prefetch_related('reviews')]}
                   for a in course.assignments.all()]
    quizzes = []
    for quiz in course.quizzes.prefetch_related('questions'):
        questions = list(quiz.questions.all())
        attempts = []
        for attempt in quiz.attempts.filter(enrollment=enrollment):
            answers = []
            for question in questions:
                selected = attempt.answers.get(str(question.id))
                valid = type(selected) is int and 0 <= selected < len(question.options)
                answers.append({'id': question.id, 'body': question.body, 'options': question.options,
                                'selected_index': selected if valid else None,
                                'selected_answer': question.options[selected] if valid else None,
                                'correct_index': question.correct_index,
                                'correct': valid and selected == question.correct_index})
            attempts.append({**attempt_data(attempt), 'started_at': attempt.started_at, 'answers': answers})
        quizzes.append({'id': quiz.id, 'title': quiz.title, 'attempts': attempts})
    code = [{'id': p.id, 'title': p.title, 'submissions': list(p.submissions.filter(enrollment=enrollment).values('id', 'code', 'status', 'passed', 'total', 'created_at'))}
            for p in CodeProblem.objects.filter(course=course)]
    return JsonResponse({'student': {'id': student.id, 'username': student.username, 'display_name': display_name(student), 'role_label': role_label(student)},
                         'run': {'id': run.id, 'title': run.title}, 'status': enrollment.status,
                         'enrolled_at': enrollment.enrolled_at, 'last_seen_at': enrollment.last_seen_at,
                         'last_step': enrollment.last_step.title if enrollment.last_step else None,
                         'progress': course_progress(course, enrollment), 'lessons': lessons,
                         'assignments': assignments, 'quizzes': quizzes, 'code_problems': code})
