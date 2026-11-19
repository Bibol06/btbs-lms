from django.contrib.auth import get_user_model
from django.test import TestCase

from courses.models import Course, CourseRun
from learning.models import Lesson, Module, Step


class PreviewNumberingTests(TestCase):
    """QA-014: outline labels must be unique numbers, not module/lesson titles like "1 · 1"."""

    def test_steps_get_module_lesson_step_numbers(self):
        teacher = get_user_model().objects.create_user(username='t_numbers', role='teacher')
        course = Course.objects.create(title='C++', teacher=teacher, is_published=True)
        run = CourseRun.objects.create(course=course)
        first = Module.objects.create(course=course, title='1', position=1, is_published=True)
        second = Module.objects.create(course=course, title='1', position=2, is_published=True)
        a = Lesson.objects.create(course=course, module=first, title='1', position=1, is_published=True)
        b = Lesson.objects.create(course=course, module=first, title='1', position=2, is_published=True)
        c = Lesson.objects.create(course=course, module=second, title='1', position=3, is_published=True)
        for lesson, count in ((a, 2), (b, 1), (c, 1)):
            for n in range(count):
                Step.objects.create(lesson=lesson, title='шаг 1', position=n + 1, is_published=True, content='x')
        self.client.force_login(teacher)
        steps = self.client.get(f'/api/workspace/courses/{course.id}/preview/?run_id={run.id}').json()['steps']
        numbers = [(s['module_number'], s['lesson_number'], s['step_number']) for s in steps]
        self.assertEqual(numbers, [(1, 1, 1), (1, 1, 2), (1, 2, 1), (2, 1, 1)])
        self.assertEqual(len(set(numbers)), len(numbers))
