from django.db import transaction
from django.utils import timezone
from .models import Quiz, QuizAttempt


def finalize_locked_attempt(attempt, quiz):
    """The caller holds quiz and attempt locks. Late request data is never used."""
    if attempt.status != 'active' or attempt.deadline_at > timezone.now():
        return False
    questions = list(quiz.questions.all())
    attempt.score = sum(type(attempt.answers.get(str(q.id))) is int and attempt.answers[str(q.id)] == q.correct_index for q in questions)
    attempt.status = 'finished'
    attempt.auto_submitted = True
    attempt.finished_at = attempt.deadline_at
    attempt.save(update_fields=['score', 'status', 'auto_submitted', 'finished_at'])
    from learning.services import refresh_completion
    refresh_completion(attempt.enrollment)
    from analytics.tracking import record
    record(attempt.student, 'quiz_finished_auto', enrollment=attempt.enrollment, dedupe=f'quiz-auto:{attempt.id}', active=False)
    from communication.services import notify, course_target
    notify(f'quiz-auto-finished:{attempt.id}', 'grade', quiz.course, {attempt.student_id},
           'Тест завершён по таймеру. Сохранённые ответы проверены.', course_target(quiz.course, attempt.enrollment.run, 'quizzes'), attempt.enrollment.run)
    return True


def finalize_due_attempts(queryset=None):
    queryset = queryset if queryset is not None else QuizAttempt.objects.all()
    refs = list(queryset.filter(status='active', deadline_at__lte=timezone.now()).values_list('id', 'quiz_id'))
    for attempt_id, quiz_id in refs:
        with transaction.atomic():
            quiz = Quiz.objects.select_for_update().filter(pk=quiz_id).first()
            attempt = QuizAttempt.objects.select_for_update().filter(pk=attempt_id).first()
            if quiz and attempt:
                finalize_locked_attempt(attempt, quiz)
