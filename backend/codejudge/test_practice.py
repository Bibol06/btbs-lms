"""Practice screen data: context, instructions, hints and lesson slides. No WASI runtime needed."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from courses.models import Course, CourseRun, Enrollment
from learning.models import Lesson, LessonMaterial, Module, Step
from .models import CodeProblem, TestCase as ProblemCase


class PracticeScreenTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.teacher = User.objects.create_user(username='practice_teacher', role='teacher')
        cls.student = User.objects.create_user(username='practice_student')
        cls.course = Course.objects.create(title='Python', teacher=cls.teacher, is_published=True)
        cls.group = CourseRun.objects.create(course=cls.course, title='Group', kind='cohort')
        Enrollment.objects.create(course=cls.course, run=cls.group, student=cls.student)
        module = Module.objects.create(course=cls.course, title='Basics', position=1, is_published=True)
        other = Module.objects.create(course=cls.course, title='Later', position=2, is_published=True)
        cls.lecture = Lesson.objects.create(course=cls.course, module=module, title='Lecture', position=1, is_published=True)
        practice = Lesson.objects.create(course=cls.course, module=module, title='Practice', position=2, is_published=True)
        draft = Lesson.objects.create(course=cls.course, module=module, title='Draft', position=3, is_published=False)
        later = Lesson.objects.create(course=cls.course, module=other, title='Later', position=4, is_published=True)
        cls.slides = LessonMaterial.objects.create(lesson=cls.lecture, title='Slides', file='lesson_materials/slides.pdf')
        LessonMaterial.objects.create(lesson=cls.lecture, title='Video', file='lesson_materials/talk.mp4')
        LessonMaterial.objects.create(lesson=cls.lecture, title='Picture', file='lesson_materials/p.pdf', is_inline=True)
        cls.draft_slides = LessonMaterial.objects.create(lesson=draft, title='Draft slides', file='lesson_materials/draft.pdf')
        LessonMaterial.objects.create(lesson=later, title='Other module', file='lesson_materials/later.pdf')
        cls.problem = CodeProblem.objects.create(course=cls.course, title='Sum', statement='Add', context='scores is loaded',
                                                 instructions=['Sum', 'Print'], hints=['Use sum()'])
        ProblemCase.objects.create(problem=cls.problem, stdin='', expected='1', is_sample=True)
        Step.objects.create(lesson=practice, title='Sum', kind='code', code_problem=cls.problem, is_published=True)

    def detail(self, user):
        self.client.force_login(user)
        response = self.client.get(f'/api/code/problems/{self.problem.id}/?run_id={self.group.id}')
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_student_gets_practice_fields_and_module_slides(self):
        data = self.detail(self.student)
        self.assertEqual((data['problem']['context'], data['problem']['instructions'], data['problem']['hints']),
                         ('scores is loaded', ['Sum', 'Print'], ['Use sum()']))
        # Only visible PDFs of the same module: no video, inline image, draft lesson or other module.
        self.assertEqual([s['id'] for s in data['slides']], [self.slides.id])
        self.assertEqual(data['slides'][0]['url'], f'/api/learning/materials/{self.slides.id}/open/?run_id={self.group.id}')

    def test_teacher_also_sees_draft_lesson_slides(self):
        self.assertEqual([s['id'] for s in self.detail(self.teacher)['slides']], [self.slides.id, self.draft_slides.id])

    def test_teacher_saves_practice_fields_and_bad_values_are_rejected(self):
        self.client.force_login(self.teacher)
        url = f'/api/code/courses/{self.course.id}/problems/?run_id={self.group.id}'
        payload = {'title': 'New', 'statement': 'Do it', 'test_cases': [{'stdin': '', 'expected': 'x'}],
                   'context': ' data ready ', 'instructions': ['First', '  ', 'Second'], 'hints': ['h1']}
        created = self.client.post(url, json.dumps(payload), content_type='application/json')
        self.assertEqual(created.status_code, 201)
        problem = CodeProblem.objects.get(pk=created.json()['id'])
        self.assertEqual((problem.context, problem.instructions, problem.hints), ('data ready', ['First', 'Second'], ['h1']))
        for bad in ({'instructions': 'not a list'}, {'hints': ['x'] * 6}, {'instructions': ['x' * 501]}, {'hints': [5]}):
            response = self.client.post(url, json.dumps({**payload, **bad}), content_type='application/json')
            self.assertEqual(response.status_code, 400, bad)
        edit = self.client.patch(f'/api/code/problems/{problem.id}/?run_id={self.group.id}',
                                 json.dumps({**payload, 'instructions': ['Only one'], 'hints': []}), content_type='application/json')
        self.assertEqual(edit.status_code, 200)
        problem.refresh_from_db()
        self.assertEqual((problem.instructions, problem.hints), (['Only one'], []))
