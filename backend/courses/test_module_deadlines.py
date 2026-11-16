import json
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from assessment.models import Assignment, Submission, Quiz, Question, QuizAttempt
from learning.models import Module, Lesson, Step, StepProgress, LessonMaterial
from .models import Course, CourseRun, Enrollment, RunModuleRelease, RunCheckpoint


class ModuleDeadlineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.teacher = User.objects.create_user(username='module_teacher', role='teacher')
        cls.student = User.objects.create_user(username='module_student')
        cls.peer = User.objects.create_user(username='module_peer')
        cls.other_teacher = User.objects.create_user(username='other_module_teacher', role='teacher')
        cls.now = timezone.now()
        cls.course = Course.objects.create(title='Modules', teacher=cls.teacher, is_published=True)
        cls.cohort = CourseRun.objects.create(course=cls.course, title='Group A', kind='cohort')
        cls.other = CourseRun.objects.create(course=cls.course, title='Group B', kind='cohort')
        cls.e = Enrollment.objects.create(course=cls.course, run=cls.cohort, student=cls.student)
        Enrollment.objects.create(course=cls.course, run=cls.other, student=cls.peer)
        cls.first = Module.objects.create(course=cls.course, title='First', is_published=True, opens_at=cls.now+timedelta(days=90))
        cls.second = Module.objects.create(course=cls.course, title='Second', position=2, is_published=True)
        cls.lesson = Lesson.objects.create(course=cls.course, module=cls.first, title='First lesson', is_published=True)
        cls.later_lesson = Lesson.objects.create(course=cls.course, module=cls.second, title='Later lesson', position=2, is_published=True)
        cls.step = Step.objects.create(lesson=cls.lesson, title='Theory', is_published=True)
        cls.later = Step.objects.create(lesson=cls.later_lesson, title='Later', is_published=True)

    def payload(self, due=None):
        return {'release_mode': 'dates', 'modules': [
            {'id': self.first.id, 'opens_at': None, 'due_at': (due or self.now+timedelta(days=2,hours=7)).isoformat()},
            {'id': self.second.id, 'opens_at': (self.now+timedelta(days=3,hours=5)).isoformat(),
             'due_at': (self.now+timedelta(days=9,hours=2)).isoformat()}]}

    def save(self, data=None, user=None, run=None):
        self.client.force_login(user or self.teacher)
        return self.client.put(f'/api/courses/runs/{(run or self.cohort).id}/learning-plan/',
                               json.dumps(data if data is not None else self.payload()),content_type='application/json')

    def plan(self, user=None):
        self.client.force_login(user or self.student)
        return self.client.get(f'/api/courses/runs/{self.cohort.id}/learning-plan/').json()

    def test_dates_are_arbitrary_group_specific_and_do_not_require_week_or_group_start(self):
        response = self.save(); self.assertEqual(response.status_code, 200, response.content)
        self.cohort.refresh_from_db(); self.first.refresh_from_db(); self.other.refresh_from_db()
        self.assertIsNone(self.cohort.starts_at)
        self.assertEqual(self.first.opens_at, self.now+timedelta(days=90))
        self.assertEqual(self.other.release_mode, 'manual')
        self.assertFalse(self.other.module_releases.exists())
        row = self.cohort.module_releases.get(module=self.second)
        self.assertEqual(row.due_at, self.now+timedelta(days=9,hours=2))
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(f'/api/learning/steps/{self.step.id}/?run_id={self.cohort.id}').status_code, 200)
        self.assertEqual(self.client.get(f'/api/learning/steps/{self.later.id}/?run_id={self.cohort.id}').status_code, 403)

    def test_deadline_exact_boundary_keeps_reading_and_completion_available(self):
        due = self.now+timedelta(minutes=10); self.assertEqual(self.save(self.payload(due)).status_code,200)
        with patch('django.utils.timezone.now', return_value=due):
            module = self.plan()['modules'][0]
            self.assertEqual(module['deadline_state'], 'overdue'); self.assertTrue(module['available'])
            self.assertEqual(self.client.get(f'/api/learning/steps/{self.step.id}/?run_id={self.cohort.id}').status_code, 200)
            response = self.client.post(f'/api/learning/steps/{self.step.id}/complete/?run_id={self.cohort.id}', '{}', content_type='application/json')
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(self.plan()['modules'][0]['deadline_state'], 'completed')

    def test_future_opening_protects_files_and_opens_at_exact_timestamp(self):
        self.save(); material=LessonMaterial.objects.create(lesson=self.later_lesson,title='Future',file='missing.pdf')
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(f'/api/learning/materials/{material.pk}/open/?run_id={self.cohort.pk}').status_code,403)
        with patch('django.utils.timezone.now',return_value=self.now+timedelta(days=3,hours=5)):
            self.assertEqual(self.client.get(f'/api/learning/steps/{self.later.pk}/?run_id={self.cohort.pk}').status_code,200)

    def test_module_deadline_can_be_extended_or_removed(self):
        self.save(self.payload(self.now-timedelta(hours=1)))
        self.assertEqual(self.plan()['modules'][0]['deadline_state'],'overdue')
        self.assertEqual(self.save().status_code,200)
        self.assertEqual(self.plan()['modules'][0]['deadline_state'],'open')
        data=self.payload();data['modules'][0]['due_at']=None
        self.assertEqual(self.save(data).status_code,200)
        self.assertIsNone(self.plan()['modules'][0]['due_at'])
        self.assertFalse(any(t['kind']=='module' and t['title']=='First' for t in self.client.get('/api/study/agenda/').json()['student_tasks']))

    def test_waiting_for_teacher_is_not_marked_overdue_and_teacher_sees_counts(self):
        self.save(self.payload(self.now-timedelta(hours=1)))
        StepProgress.objects.create(enrollment=self.e,step=self.step)
        assignment=Assignment.objects.create(course=self.course,title='Essay',is_published=True)
        Step.objects.create(lesson=self.lesson,title='Write',position=2,kind='assignment',assignment=assignment,is_published=True)
        answer=Submission.objects.create(assignment=assignment,enrollment=self.e,student=self.student,attempt_no=1,status='submitted')
        self.assertEqual(self.plan()['modules'][0]['deadline_state'],'waiting')
        module=self.plan(self.teacher)['modules'][0]
        self.assertEqual((module['overdue_count'],module['waiting_count']),(0,1))
        answer.status='returned';answer.save()
        self.assertEqual(self.plan()['modules'][0]['deadline_state'],'overdue')
        module=self.plan(self.teacher)['modules'][0]
        self.assertEqual(module['overdue_count'],1)

    def test_deadlines_show_in_agenda_structure_and_completed_modules_are_not_overdue(self):
        self.save(self.payload(self.now-timedelta(hours=1)))
        self.client.force_login(self.student)
        task=next(t for t in self.client.get('/api/study/agenda/').json()['student_tasks'] if t['kind']=='module' and t['title']=='First')
        self.assertEqual(task['state'],'module_overdue');self.assertIsNone(task['closes_at'])
        structure=self.client.get(f'/api/learning/courses/{self.course.pk}/structure/?run_id={self.cohort.pk}').json()
        self.assertEqual(structure['modules'][0]['deadline_state'],'overdue')
        StepProgress.objects.create(enrollment=self.e,step=self.step)
        module=self.plan()['modules'][0];self.assertEqual(module['deadline_state'],'completed')
        module=self.plan(self.teacher)['modules'][0];self.assertEqual((module['completed_count'],module['overdue_count']),(1,0))

    def test_self_paced_course_also_allows_explicit_module_deadlines(self):
        solo=CourseRun.objects.create(course=self.course,title='Solo',kind='self_paced')
        self.assertEqual(self.save(run=solo).status_code,200)
        self.assertIsNotNone(solo.module_releases.get(module=self.first).due_at)

    def test_invalid_intervals_and_foreign_modules_are_rejected_atomically(self):
        data=self.payload();data['modules'][1]['due_at']=data['modules'][1]['opens_at']
        self.assertEqual(self.save(data).status_code,400);self.assertFalse(self.cohort.module_releases.exists())
        other=Course.objects.create(title='Other');foreign=Module.objects.create(course=other,title='Foreign')
        data=self.payload();data['modules'][0]['id']=foreign.id
        self.assertEqual(self.save(data).status_code,400);self.assertFalse(self.cohort.module_releases.exists())

    def test_only_managers_can_edit_and_other_group_cannot_read(self):
        for user in [self.student,self.other_teacher]:self.assertEqual(self.save(user=user).status_code,403)
        self.client.force_login(self.peer)
        self.assertEqual(self.client.get(f'/api/courses/runs/{self.cohort.id}/learning-plan/').status_code,403)

    def test_module_edits_preserve_checkpoint_attempts_and_schedules(self):
        quiz=Quiz.objects.create(course=self.course,title='Checkpoint',is_published=True)
        Question.objects.create(quiz=quiz,body='?',options=['a','b'],correct_index=0,position=1)
        check=RunCheckpoint.objects.create(run=self.cohort,quiz=quiz,kind='weekly',period=1,
            opens_at=self.now-timedelta(hours=1),closes_at=self.now+timedelta(days=1))
        attempt=QuizAttempt.objects.create(quiz=quiz,enrollment=self.e,student=self.student,attempt_no=1,max_score=1,deadline_at=self.now+timedelta(minutes=10))
        self.assertEqual(self.save().status_code,200)
        attempt.refresh_from_db();self.assertEqual(attempt.status,'active')
        stored=self.cohort.checkpoints.get(quiz=quiz);self.assertEqual(stored.closes_at,check.closes_at)

    def test_group_dates_cannot_make_module_deadline_impossible(self):
        self.assertEqual(self.save().status_code,200)
        self.client.force_login(self.teacher)
        for data in [{'ends_at':(self.now+timedelta(days=1)).isoformat()}, {'starts_at':(self.now+timedelta(days=20)).isoformat()}]:
            response=self.client.patch(f'/api/courses/runs/{self.cohort.id}/',json.dumps(data),content_type='application/json')
            self.assertEqual(response.status_code,400,response.content)
        self.cohort.refresh_from_db();self.assertIsNone(self.cohort.starts_at);self.assertIsNone(self.cohort.ends_at)
