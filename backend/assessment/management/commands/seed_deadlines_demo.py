import json
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from courses.models import Course, CourseRun, Enrollment
from learning.models import Module, Lesson, Step
from assessment.models import Assignment, Submission, AssignmentExtension, GradeReview, Quiz, Question


class Command(BaseCommand):
    help = 'Create a separate demo of deadlines without modifying existing courses or accounts'

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        teacher = User.objects.filter(username='demo_teacher').first()
        student = User.objects.filter(username='demo_student').first()
        peer = User.objects.filter(username='demo_peer').first()
        if not all([teacher, student, peer]):
            raise CommandError('Сначала создайте демо-аккаунты командой seed_platform_demo')
        course = Course.objects.filter(title='Демо: сроки, проверки и доработки', teacher=teacher).first()
        now = timezone.now()
        if course is None:
            course = Course.objects.create(title='Демо: сроки, проверки и доработки', description='Отдельные примеры: обычная сдача, опоздание, доработка, ожидание проверки и просрочка преподавателя.', teacher=teacher, is_published=True)
            run = CourseRun.objects.create(course=course, title='Учебная группа · сроки', kind='cohort', ends_at=now+timedelta(days=30))
            run.teachers.add(teacher)
            e = Enrollment.objects.create(course=course, run=run, student=student)
            p = Enrollment.objects.create(course=course, run=run, student=peer)
            module = Module.objects.create(course=course, title='Сдача и обратная связь', is_published=True)
            configs = [
                ('Работа без опоздания', now+timedelta(days=2), False, None),
                ('Можно сдать с опозданием', now-timedelta(hours=2), True, now+timedelta(days=2)),
                ('Исправить после комментария', now-timedelta(days=1), False, None),
                ('Работа ожидает проверки', now+timedelta(days=2), False, None),
                ('Пример задержки проверки', now-timedelta(days=2), True, now+timedelta(days=1)),
            ]
            works = []
            for position, (title, due, late, cutoff) in enumerate(configs, 1):
                assignment = Assignment.objects.create(course=course, title=title, description='Объясните решение своими словами или приложите файл. Срок сдачи и ожидаемая проверка указаны ниже.', due_at=due, allow_late=late, cutoff_at=cutoff, review_hours=48, max_attempts=3, is_published=True)
                lesson = Lesson.objects.create(course=course, module=module, title=title, position=position, is_published=True)
                Step.objects.create(lesson=lesson, title=title, kind='assignment', assignment=assignment, is_published=True)
                works.append(assignment)
            revision_due = now+timedelta(days=3)
            returned = Submission.objects.create(assignment=works[2], enrollment=e, student=student, attempt_no=1, text_answer='Черновик решения. Нужно добавить объяснение.', status='returned', feedback='Добавьте пояснение каждого шага и отправьте исправленную работу.', graded_by=teacher, graded_at=now-timedelta(hours=1), revision_due_at=revision_due, reviewer=teacher, due_at_snapshot=works[2].due_at)
            Submission.objects.filter(pk=returned.id).update(submitted_at=now-timedelta(days=2))
            GradeReview.objects.create(submission=returned, reviewer=teacher, action='returned', score=None, feedback=returned.feedback, revision_due_at=revision_due)
            AssignmentExtension.objects.create(assignment=works[2], enrollment=e, deadline_at=revision_due, reason='Доработка работы', granted_by=teacher)
            waiting = Submission.objects.create(assignment=works[3], enrollment=e, student=student, attempt_no=1, text_answer='Готовое решение отправлено преподавателю.', review_due_at=now+timedelta(hours=47), reviewer=teacher, due_at_snapshot=works[3].due_at)
            Submission.objects.filter(pk=waiting.id).update(submitted_at=now-timedelta(hours=1))
            overdue = Submission.objects.create(assignment=works[4], enrollment=p, student=peer, attempt_no=1, text_answer='Работа сдана вовремя, преподаватель задерживает проверку.', review_due_at=now-timedelta(days=1), reviewer=teacher, due_at_snapshot=works[4].due_at)
            Submission.objects.filter(pk=overdue.id).update(submitted_at=now-timedelta(days=3))
            quiz = Quiz.objects.create(course=course, title='Тест: сохранение ответов по таймеру', time_limit_sec=60, max_attempts=5, is_published=True)
            Question.objects.create(quiz=quiz, body='Сколько будет 2 + 2?', options=['3', '4'], correct_index=1, position=1)
            Question.objects.create(quiz=quiz, body='Что случится после окончания таймера?', options=['Ответы пропадут', 'Система проверит сохранённые ответы'], correct_index=1, position=2)
            lesson = Lesson.objects.create(course=course, module=module, title='Тест по таймеру', position=6, is_published=True)
            Step.objects.create(lesson=lesson, title=quiz.title, kind='quiz', quiz=quiz, is_published=True)
        run = course.runs.get(kind='cohort')
        self.stdout.write(json.dumps({'course_id': course.id, 'run_id': run.id,
            'assignments': list(course.assignments.values('id', 'title')), 'quiz_id': course.quizzes.first().id}, ensure_ascii=True))
