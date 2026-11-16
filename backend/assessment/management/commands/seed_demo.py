"""Add isolated demonstration data without changing existing users or courses."""
import json
import secrets
from accounts.management.commands.set_example_names import EXAMPLE_NAMES
from pathlib import Path
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from courses.models import Course, Enrollment
from learning.models import Lesson
from assessment.models import Assignment, Submission, Quiz, Question, LessonProgress


class Command(BaseCommand):
    help = 'Create a local demo course and separate accounts; credentials go to .local/demo-access.json'

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Демо-данные разрешены только при DEBUG=True')
        destination = Path(settings.BASE_DIR).parent / '.local/demo-access.json'
        if destination.exists():
            self.stdout.write('Демо уже создано. Доступы: .local/demo-access.json')
            return
        User = get_user_model()
        users, credentials = {}, {}
        with transaction.atomic():
            for role in ['teacher', 'student', 'admin']:
                username = f'demo_{role}'
                if User.objects.filter(username__iexact=username).exists():
                    username += '_' + secrets.token_hex(2)
                password = secrets.token_urlsafe(15)
                first, last = EXAMPLE_NAMES[f'demo_{role}']
                users[role] = User.objects.create_user(username=username, password=password, role=role, first_name=first, last_name=last)
                credentials[role] = {'username': username, 'password': password}
            course = Course.objects.create(title='Демо: полный учебный цикл',
                description='Уроки, домашние задания, тесты и журнал. Отдельный курс для проверки новых возможностей.',
                teacher=users['teacher'], is_published=True)
            Enrollment.objects.create(course=course, student=users['student'])
            first = Lesson.objects.create(course=course, title='Знакомство с учебным курсом',
                content='Добро пожаловать!\n\n1. Изучите уроки и отметьте их пройденными.\n2. Откройте «Задания» и отправьте решение.\n3. Пройдите тест.\n4. Посмотрите свои результаты.\n\nПреподаватель проверяет работы во вкладке «Задания», а общие результаты — в журнале.',
                position=1, is_published=True)
            Lesson.objects.create(course=course, title='Практика: простые вычисления',
                content='Сложение объединяет значения: 2 + 2 = 4.\nУмножение повторяет сложение: 3 × 2 = 6.\n\nПримените эти правила в задании и тесте.',
                position=2, is_published=True)
            Lesson.objects.create(course=course, title='Черновик будущего урока', content='Этот урок виден только преподавателю.', position=3)
            LessonProgress.objects.create(lesson=first, student=users['student'])
            Assignment.objects.create(course=course, title='Практическая работа',
                description='Вычислите 12 + 8 и 7 × 6. Объясните решение текстом или приложите PDF.',
                due_at=timezone.now() + timedelta(days=7), max_attempts=3, is_published=True)
            graded = Assignment.objects.create(course=course, title='Пример проверенной работы',
                description='Пример того, как выглядят оценка и комментарий преподавателя.', is_published=True)
            Submission.objects.create(assignment=graded, student=users['student'], attempt_no=1,
                text_answer='2 + 2 = 4. Я сложил два и два.', score=95,
                feedback='Верно. В следующих заданиях продолжайте объяснять ход решения.', graded_by=users['teacher'], graded_at=timezone.now())
            quiz = Quiz.objects.create(course=course, title='Проверка знаний', time_limit_sec=300, max_attempts=3, is_published=True)
            Question.objects.create(quiz=quiz, body='Сколько будет 2 + 2?', options=['3', '4', '5', '6'], correct_index=1, position=1)
            Question.objects.create(quiz=quiz, body='Сколько будет 3 × 2?', options=['5', '8', '6', '9'], correct_index=2, position=2)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps({'course_id': course.id, 'accounts': credentials}, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('Демо создано. Доступы сохранены в .local/demo-access.json'))
