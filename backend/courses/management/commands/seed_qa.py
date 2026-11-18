"""Seed the isolated QA database (config.qa_settings only): every role, every step kind, edge data.

    python manage.py seed_qa --settings=config.qa_settings [--video path/to/sample.mp4]

Accounts and ids are written to settings.LMS_QA_ACCESS_FILE for the Playwright suite.
"""
import io
import json
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

PASSWORD = 'qa-Passw0rd!'
LONG = ('Очень длинное название шага, чтобы проверить перенос и многоточие в программе курса, плеере урока, '
        'карточках и таблицах — оно ровно на грани допустимой длины и не должно вылезать за пределы контейнера')[:200]


def pdf_bytes(title, pages=2):
    from PIL import Image, ImageDraw
    images = []
    for n in range(pages):
        img = Image.new('RGB', (1280, 720), 'white')
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 1280, 10], fill='#087f88')
        draw.text((80, 80), f'{title} — {n + 1}/{pages}', fill='#102542')
        images.append(img)
    buffer = io.BytesIO()
    images[0].save(buffer, 'PDF', save_all=True, append_images=images[1:])
    return buffer.getvalue()


class Command(BaseCommand):
    help = 'Seed the QA database with accounts for every role and courses covering every step kind and edge case.'

    def add_arguments(self, parser):
        parser.add_argument('--video', type=Path, help='Small .mp4/.webm copied into QA media for video playback checks')

    def handle(self, *args, **options):
        access_file = getattr(settings, 'LMS_QA_ACCESS_FILE', None)
        if not access_file or not connection.settings_dict['NAME'].startswith('lms_qa'):
            raise CommandError('seed_qa runs only with --settings=config.qa_settings on an lms_qa database')
        User = get_user_model()
        if User.objects.filter(username='qa_student').exists():
            self.stdout.write(f'QA data already present. Accounts: {access_file}')
            return
        with transaction.atomic():
            data = self.build(User, options.get('video'))
        Path(access_file).parent.mkdir(parents=True, exist_ok=True)
        Path(access_file).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'QA data created. Accounts: {access_file}'))

    def build(self, User, video):
        from assessment.models import Assignment, Question, Quiz, QuizAttempt, Submission
        from codejudge.models import CodeProblem, TestCase
        from communication.models import Announcement, Comment, Discussion
        from courses.models import Course, CourseMember, CourseRun, Enrollment
        from learning.models import Lesson, LessonMaterial, Module, Step

        def user(username, role='student', first='', last='', **extra):
            return User.objects.create_user(username=username, password=PASSWORD, role=role, first_name=first, last_name=last,
                                            email=f'{username}@qa.invalid', **extra)

        people = {
            'student': user('qa_student', first='Айгерим', last='Студентова'),
            'student_peer': user('qa_peer', first='Иван', last='Однокурсников'),
            'student_empty': user('qa_student_empty', first='Новый', last='Ученик'),
            'teacher': user('qa_teacher', 'teacher', 'Асель', 'Преподавателева'),
            'editor': user('qa_editor', 'teacher', 'Ерлан', 'Редакторов'),
            'group_teacher': user('qa_group_teacher', 'teacher', 'Марат', 'Группов'),
            'admin_full': user('qa_admin_full', 'admin', 'Полный', 'Админ', admin_scope='full'),
            'admin_learning': user('qa_admin_learning', 'admin', 'Учебный', 'Админ', admin_scope='learning'),
            'admin_system': user('qa_admin_system', 'admin', 'Системный', 'Админ', admin_scope='system'),
        }
        now = timezone.now()
        main = Course.objects.create(title='QA: Python основы', description='Курс для автоматической проверки интерфейса.',
                                     is_published=True, teacher=people['teacher'])
        CourseMember.objects.create(course=main, user=people['editor'])
        self_paced = CourseRun.objects.create(course=main)
        cohort = CourseRun.objects.create(course=main, kind='cohort', title='QA группа', starts_at=now - timedelta(days=7))
        cohort.teachers.add(people['group_teacher'])
        m1 = Module.objects.create(course=main, title='Модуль 1. Знакомство', position=1, is_published=True)
        m2 = Module.objects.create(course=main, title='Модуль 2. Практика', position=2, is_published=True, prerequisite=m1)
        intro = Lesson.objects.create(course=main, module=m1, title='Введение в Python', position=1, is_published=True)
        practice = Lesson.objects.create(course=main, module=m1, title='Практика: ввод и вывод', position=2, is_published=True)
        later = Lesson.objects.create(course=main, module=m2, title='Списки', position=3, is_published=True)
        slides = LessonMaterial(lesson=intro, title='Слайды: введение')
        slides.file.save('qa-slides.pdf', ContentFile(pdf_bytes('QA slides')), save=True)
        steps = {}
        steps['text'] = Step.objects.create(lesson=intro, title='Что такое Python', kind='text', position=1, is_published=True,
                                            content='Python — язык программирования.\n\nВ этом уроке мы напишем первую программу.')
        steps['video'] = Step.objects.create(lesson=intro, title='Видеолекция', kind='video', position=2, is_published=True,
                                             video_url='https://www.youtube.com/watch?v=kqtD5dpn9C8',
                                             transcript='00:00 Введение\nО чём курс.\n01:20 Установка\nКак установить Python.')
        steps['file'] = Step.objects.create(lesson=intro, title='Слайды лекции', kind='file', position=3, is_published=True, material=slides)
        if video and Path(video).is_file():
            clip = LessonMaterial(lesson=intro, title='Видео: первая программа')
            clip.file.save('qa-video' + Path(video).suffix.lower(), ContentFile(Path(video).read_bytes()), save=True)
            steps['video_file'] = Step.objects.create(lesson=intro, title='Видео из файла', kind='file', position=4, is_published=True, material=clip)
        quiz = Quiz.objects.create(course=main, title='Проверка: основы', is_published=True, max_attempts=3)
        for n, (body, options, correct) in enumerate([('Что выведет print(2 + 3)?', ['23', '5', 'Ошибка'], 1),
                                                     ('Какая функция читает ввод?', ['input()', 'print()', 'read()'], 0),
                                                     ('Тип значения 3.5?', ['int', 'str', 'float'], 2)], 1):
            Question.objects.create(quiz=quiz, body=body, position=n, options=options, correct_index=correct)
        assignment = Assignment.objects.create(course=main, title='Домашняя работа: калькулятор', description='Опишите решение и приложите файл.',
                                               is_published=True, due_at=now + timedelta(days=5), max_attempts=3)
        problem = CodeProblem.objects.create(course=main, title='Сумма двух чисел', statement='Прочитайте два числа и выведите их сумму.',
                                             starter_code='a = int(input())\nb = int(input())\n', max_attempts=10,
                                             context='Числа подаются на отдельных строках.', instructions=['Прочитайте числа', 'Выведите сумму'],
                                             hints=['Используйте int(input()).'])
        TestCase.objects.create(problem=problem, stdin='2\n3\n', expected='5', is_sample=True, position=1)
        TestCase.objects.create(problem=problem, stdin='-1\n1\n', expected='0', position=2)
        steps['quiz'] = Step.objects.create(lesson=practice, title='Тест по основам', kind='quiz', quiz=quiz, position=1, is_published=True)
        steps['assignment'] = Step.objects.create(lesson=practice, title='Домашняя работа', kind='assignment', assignment=assignment, position=2, is_published=True)
        steps['code'] = Step.objects.create(lesson=practice, title='Задача на Python', kind='code', code_problem=problem, position=3, is_published=True)
        steps['locked'] = Step.objects.create(lesson=later, title='Списки и циклы', kind='text', position=1, is_published=True, content='Списки хранят набор значений.')

        # Edge data: the kinds of titles that broke the UI before.
        edge = Course.objects.create(title='QA: C++ (данные с ошибками)', description='', is_published=True, teacher=people['teacher'])
        edge_run = CourseRun.objects.create(course=edge)
        em = Module.objects.create(course=edge, title='1', position=1, is_published=True)
        el = Lesson.objects.create(course=edge, module=em, title='1', position=1, is_published=True)
        Step.objects.create(lesson=el, title='Уроки_Python_с_нуля_#1 – Программирование (360p, h264).mp4', kind='text', position=1, is_published=True, content='Текст')
        Step.objects.create(lesson=el, title=LONG, kind='text', position=2, is_published=True, content='Текст')
        Step.objects.create(lesson=el, title='шаг 1', kind='text', position=3, is_published=True, content='Текст')
        Step.objects.create(lesson=el, title='шаг 1', kind='text', position=4, is_published=True, content='Текст')
        empty = Course.objects.create(title='QA: Пустой курс', description='Курс без уроков.', is_published=True, teacher=people['teacher'])
        CourseRun.objects.create(course=empty)
        draft = Course.objects.create(title='QA: Черновик курса', description='', is_published=False, teacher=people['teacher'])
        CourseRun.objects.create(course=draft)

        Enrollment.objects.create(course=main, run=cohort, student=people['student'])
        peer = Enrollment.objects.create(course=main, run=cohort, student=people['student_peer'])
        Enrollment.objects.create(course=edge, run=edge_run, student=people['student'])
        Submission.objects.create(enrollment=peer, student=people['student_peer'], assignment=assignment, attempt_no=1,
                                  status='submitted', text_answer='Мой калькулятор складывает числа.', review_due_at=now + timedelta(hours=10))
        QuizAttempt.objects.create(enrollment=peer, student=people['student_peer'], quiz=quiz, attempt_no=1, status='finished',
                                   score=2, max_score=3, deadline_at=now, finished_at=now, answers={})
        discussion = Discussion.objects.create(lesson=intro, run=cohort)
        Comment.objects.create(discussion=discussion, author=people['student_peer'], body='Почему print пишет с новой строки?')
        Announcement.objects.create(course=main, run=cohort, author=people['teacher'], title='Добро пожаловать', body='Начинаем во вторник.',
                                    is_published=True, published_at=now)
        return {
            'password': PASSWORD,
            'accounts': {role: u.username for role, u in people.items()},
            'courses': {'main': main.id, 'edge': edge.id, 'empty': empty.id, 'draft': draft.id},
            'runs': {'self_paced': self_paced.id, 'cohort': cohort.id, 'edge': edge_run.id},
            'steps': {kind: s.id for kind, s in steps.items()},
            'lessons': {'intro': intro.id, 'practice': practice.id, 'later': later.id, 'edge': el.id},
            'problem': problem.id, 'quiz': quiz.id, 'assignment': assignment.id,
        }
