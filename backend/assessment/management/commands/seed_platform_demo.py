import json
import secrets
from accounts.management.commands.set_example_names import EXAMPLE_NAMES
from pathlib import Path
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from courses.models import Course, CourseRun, Enrollment, CourseMember, default_run
from learning.models import Module, Lesson, Step
from assessment.models import ActivitySchedule
from communication.models import Announcement, Conversation, Participant, Message, Discussion, Comment
from communication.views import publish_announcement
from codejudge.models import CodeProblem, TestCase


class Command(BaseCommand):
    help = 'Extend the isolated demo course with groups, communication and Python steps'

    def handle(self, *args, **kwargs):
        if not settings.DEBUG:
            raise CommandError('Демо разрешено только при DEBUG=True')
        destination = Path(settings.LMS_DEMO_ACCESS_FILE)
        if not destination.exists():
            call_command('seed_demo')
        metadata = json.loads(destination.read_text(encoding='utf-8'))
        if metadata.get('platform_ready'):
            self.stdout.write('Демо платформы уже подготовлено')
            return
        User = get_user_model()
        with transaction.atomic():
            course = Course.objects.get(pk=metadata['course_id'])
            teacher = User.objects.get(username=metadata['accounts']['teacher']['username'])
            student = User.objects.get(username=metadata['accounts']['student']['username'])
            CourseMember.objects.get_or_create(course=course, user=teacher, defaults={'role': 'owner'})
            standalone = default_run(course)
            Enrollment.objects.get_or_create(course=course, run=standalone, student=student)
            people = {}
            for role, name in [('tutor', 'demo_tutor'), ('peer', 'demo_peer')]:
                if User.objects.filter(username__iexact=name).exists():
                    name += '_' + secrets.token_hex(2)
                password = secrets.token_urlsafe(15)
                first, last = EXAMPLE_NAMES[f'demo_{role}']
                people[role] = User.objects.create_user(username=name, password=password, role='teacher' if role == 'tutor' else 'student', first_name=first, last_name=last)
                metadata['accounts'][role] = {'username': name, 'password': password}
            ra = CourseRun.objects.create(course=course, title='Группа A · октябрь', kind='cohort', join_code=secrets.token_urlsafe(16), ends_at=timezone.now()+timedelta(days=30))
            rb = CourseRun.objects.create(course=course, title='Группа B · ноябрь', kind='cohort', join_code=secrets.token_urlsafe(16), ends_at=timezone.now()+timedelta(days=45))
            ra.teachers.add(people['tutor'])
            ea = Enrollment.objects.create(course=course, run=ra, student=student)
            Enrollment.objects.create(course=course, run=rb, student=people['peer'])
            main, _ = Module.objects.get_or_create(course=course, position=1, defaults={'title': 'Основная программа', 'is_published': True})
            for lesson in course.lessons.filter(module__isnull=True):
                lesson.module = main
                lesson.save(update_fields=['module'])
            for lesson in course.lessons.all():
                if not lesson.steps.exists():
                    Step.objects.create(lesson=lesson, title=lesson.title, content=lesson.content, position=1, is_published=lesson.is_published)
            module = Module.objects.create(course=course, title='Практика и проверка знаний', position=2, is_published=True)
            position = max(course.lessons.values_list('position', flat=True), default=0)+1
            lesson = Lesson.objects.create(course=course, module=module, title='Python: сумма двух чисел', position=position, is_published=True)
            problem = CodeProblem.objects.create(course=course, title='Сложение двух чисел', statement='На вход подаются два целых числа, каждое на отдельной строке. Выведите их сумму.', starter_code='a = int(input())\nb = int(input())\n\n# Выведите сумму a и b\n', max_attempts=20)
            TestCase.objects.create(problem=problem, stdin='2\n3\n', expected='5', is_sample=True)
            TestCase.objects.create(problem=problem, stdin='-5\n12\n', expected='7', position=2)
            TestCase.objects.create(problem=problem, stdin='0\n0\n', expected='0', position=3)
            code_step = Step.objects.create(lesson=lesson, title='Решите задачу на Python', kind='code', code_problem=problem, position=1, is_published=True)
            quiz = course.quizzes.filter(is_published=True).first()
            if quiz:
                Step.objects.create(lesson=lesson, title='Итоговый тест', kind='quiz', quiz=quiz, position=2, is_published=True)
            assignment = course.assignments.filter(is_published=True).first()
            if assignment:
                Step.objects.create(lesson=lesson, title='Домашняя работа', kind='assignment', assignment=assignment, position=3, is_published=True)
                ActivitySchedule.objects.create(run=ra, assignment=assignment, due_at=timezone.now()+timedelta(hours=18))
                ActivitySchedule.objects.create(run=rb, assignment=assignment, due_at=timezone.now()+timedelta(days=5))
            news = Announcement.objects.create(course=course, author=teacher, title='Добро пожаловать в обновлённый курс', body='Добавлены модули, шаги, задачи Python, учебные группы и общение. В режиме самостоятельного обучения доступны ваши прежние результаты. У каждой группы отдельные работы, обсуждения и сроки.', is_published=True)
            publish_announcement(news)
            conversation = Conversation.objects.create(enrollment=ea)
            for person in [student, teacher, people['tutor']]:
                Participant.objects.create(conversation=conversation, user=person)
            Message.objects.create(conversation=conversation, author=people['tutor'], body='Привет! Здесь можно задать личный вопрос по обучению в группе A.')
            for run in [ra, rb]:
                thread = Discussion.objects.create(lesson=lesson, run=run)
                Comment.objects.create(discussion=thread, author=teacher, body=f'Обсуждение для «{run.title}». Сообщения другой группы здесь не отображаются.', is_pinned=True)
            metadata.update({'platform_ready': True, 'group_a': ra.id, 'group_b': rb.id, 'python_step': code_step.id})
        destination.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'Демо расширено. Доступы: {destination}'))
