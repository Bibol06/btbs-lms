import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from courses.models import Course, CourseRun, Enrollment
from .models import Lesson, Module, Step


class StepTranscriptTests(TestCase):
    def test_editor_saves_transcript_and_learner_receives_it(self):
        User = get_user_model()
        teacher = User.objects.create_user(username='t_transcript', role='teacher')
        student = User.objects.create_user(username='s_transcript')
        course = Course.objects.create(title='C', teacher=teacher, is_published=True)
        run = CourseRun.objects.create(course=course)
        Enrollment.objects.create(course=course, run=run, student=student)
        module = Module.objects.create(course=course, title='M', position=1, is_published=True)
        lesson = Lesson.objects.create(course=course, module=module, title='L', position=1, is_published=True)
        self.client.force_login(teacher)
        created = self.client.post(f'/api/learning/lessons/{lesson.id}/steps/', json.dumps({
            'title': 'Lecture', 'kind': 'video', 'video_url': 'https://www.youtube.com/watch?v=abc', 'is_published': True,
            'transcript': '  00:00 Intro\nHello\n  '}), content_type='application/json')
        self.assertEqual(created.status_code, 201)
        step = Step.objects.get(pk=created.json()['id'])
        self.assertEqual(step.transcript, '00:00 Intro\nHello')
        # A PATCH without the field keeps the transcript.
        self.client.patch(f'/api/learning/steps/{step.id}/?run_id={run.id}', json.dumps({'title': 'Lecture 2'}), content_type='application/json')
        step.refresh_from_db()
        self.assertEqual((step.title, step.transcript), ('Lecture 2', '00:00 Intro\nHello'))
        too_long = self.client.patch(f'/api/learning/steps/{step.id}/?run_id={run.id}', json.dumps({'transcript': 'x' * 50001}), content_type='application/json')
        self.assertEqual(too_long.status_code, 400)
        self.client.force_login(student)
        data = self.client.get(f'/api/learning/steps/{step.id}/?run_id={run.id}').json()['step']
        self.assertEqual(data['transcript'], '00:00 Intro\nHello')
