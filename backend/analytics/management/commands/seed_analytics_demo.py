import json
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from courses.models import Course, CourseRun, Enrollment, default_run
from learning.models import Module, Lesson, Step
from assessment.models import Quiz, Question
from analytics.models import LessonEvaluation


class Command(BaseCommand):
    help = 'Create an isolated before/after demo; attempts are made through the real API, never backdated.'

    def handle(self, *args, **kwargs):
        if not settings.DEBUG:
            raise CommandError('Local demonstration only')
        destination = Path(settings.BASE_DIR).parent/'.local/analytics-demo.json'
        if destination.exists():
            self.stdout.write('Analytics demo already exists')
            return
        access = json.loads((destination.parent/'demo-access.json').read_text(encoding='utf-8-sig'))
        User = get_user_model()
        teacher = User.objects.get(username=access['accounts']['teacher']['username'])
        student = User.objects.get(username=access['accounts']['student']['username'])
        with transaction.atomic():
            course = Course.objects.create(title='Демо: аналитика усвоения материала', teacher=teacher, is_published=True,
                description='Демонстрация настоящего прохождения: входной тест, материал и итоговый тест. Даты и результаты не переносятся в прошлое.')
            default_run(course)
            run = CourseRun.objects.create(course=course, title='Группа · аналитика', kind='cohort')
            enrollment = Enrollment.objects.create(course=course, run=run, student=student)
            module = Module.objects.create(course=course, title='Сравнение до и после', is_published=True)
            before = Lesson.objects.create(course=course, module=module, title='Входная диагностика', position=1, is_published=True)
            material = Lesson.objects.create(course=course, module=module, title='Сложение и умножение: объяснение', position=2, is_published=True)
            after = Lesson.objects.create(course=course, module=module, title='Проверка после материала', position=3, is_published=True)
            quizzes = []
            for title in ('Входной тест: вычисления', 'Итоговый тест: вычисления'):
                quiz = Quiz.objects.create(course=course, title=title, is_published=True, time_limit_sec=300, max_attempts=5)
                Question.objects.create(quiz=quiz, body='Сколько будет 2 + 3?', options=['5', '6'], correct_index=0, position=1)
                Question.objects.create(quiz=quiz, body='Сколько будет 3 × 4?', options=['7', '12'], correct_index=1, position=2)
                quizzes.append(quiz)
            pre_step = Step.objects.create(lesson=before, title='Пройти входной тест', kind='quiz', quiz=quizzes[0], is_published=True, pass_percent=0)
            text_step = Step.objects.create(lesson=material, title='Изучить объяснение', kind='text', is_published=True,
                content='Сложение объединяет количества: 2 + 3 = 5. Умножение — повторное сложение: 3 × 4 = 4 + 4 + 4 = 12. Проверьте понимание в итоговом тесте.')
            post_step = Step.objects.create(lesson=after, title='Пройти итоговый тест', kind='quiz', quiz=quizzes[1], is_published=True)
            LessonEvaluation.objects.create(lesson=material, run=run, pre_quiz=quizzes[0], post_quiz=quizzes[1], updated_by=teacher)
        metadata = {'course_id': course.id, 'run_id': run.id, 'enrollment_id': enrollment.id, 'lesson_id': material.id,
                    'pre_quiz_id': quizzes[0].id, 'post_quiz_id': quizzes[1].id,
                    'pre_step_id': pre_step.id, 'material_step_id': text_step.id, 'post_step_id': post_step.id}
        destination.write_text(json.dumps(metadata, ensure_ascii=True, indent=2), encoding='utf-8')
        self.stdout.write('Created isolated analytics demo: .local/analytics-demo.json')
