import json
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from assessment.models import Quiz, Question, QuizAttempt, ActivitySchedule
from learning.models import Module, Lesson, Step, LessonMaterial
from learning.services import course_progress, course_progress_many
from .models import Course, CourseRun, Enrollment, RunCheckpoint


class WeeklyPlanTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.teacher = User.objects.create_user(username='plan_teacher', role='teacher')
        cls.tutor = User.objects.create_user(username='plan_tutor', role='teacher')
        cls.student = User.objects.create_user(username='plan_student')
        cls.peer = User.objects.create_user(username='plan_peer')
        cls.start = timezone.now()-timedelta(days=6)
        cls.course = Course.objects.create(title='Paced', teacher=cls.teacher, is_published=True)
        cls.a = CourseRun.objects.create(course=cls.course, title='A', kind='cohort', starts_at=cls.start)
        cls.b = CourseRun.objects.create(course=cls.course, title='B', kind='cohort', starts_at=cls.start+timedelta(days=14))
        cls.a.teachers.add(cls.tutor)
        cls.e = Enrollment.objects.create(course=cls.course, run=cls.a, student=cls.student)
        Enrollment.objects.create(course=cls.course, run=cls.b, student=cls.peer)
        cls.m1 = Module.objects.create(course=cls.course, title='Week 1', is_published=True, opens_at=cls.start+timedelta(days=90))
        cls.m2 = Module.objects.create(course=cls.course, title='Week 2', position=2, is_published=True)
        cls.l1 = Lesson.objects.create(course=cls.course, module=cls.m1, title='Lesson 1', is_published=True)
        cls.l2 = Lesson.objects.create(course=cls.course, module=cls.m2, title='Lesson 2', position=2, is_published=True)
        cls.s1 = Step.objects.create(lesson=cls.l1, title='First', content='Theory', is_published=True)
        cls.s2 = Step.objects.create(lesson=cls.l2, title='Second', content='Theory', is_published=True)
        cls.quiz = Quiz.objects.create(course=cls.course, title='Weekly', is_published=True)
        Question.objects.create(quiz=cls.quiz, body='2+3?', options=['4','5'], correct_index=1, position=1)
        cls.month = Quiz.objects.create(course=cls.course, title='Four weeks', is_published=True)
        Question.objects.create(quiz=cls.month, body='3+3?', options=['6','9'], correct_index=0, position=1)

    def payload(self):
        return {'release_mode':'weekly', 'starts_at':self.start.isoformat(),
            'modules':[{'id':self.m1.id,'week':1}, {'id':self.m2.id,'week':2}],
            'checkpoints':[{'quiz_id':self.quiz.id,'kind':'weekly','period':1}, {'quiz_id':self.month.id,'kind':'monthly','period':1}]}

    def save(self, data=None, user=None, run=None):
        self.client.force_login(user or self.teacher)
        return self.client.put(f'/api/courses/runs/{(run or self.a).id}/learning-plan/',json.dumps(data or self.payload()),content_type='application/json')

    def test_group_plan_opens_weeks_without_changing_global_module_dates_or_other_group(self):
        response=self.save(); self.assertEqual(response.status_code,200,response.content)
        self.m1.refresh_from_db(); self.b.refresh_from_db()
        self.assertEqual(self.m1.opens_at,self.start+timedelta(days=90)); self.assertEqual(self.b.release_mode,'manual')
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(f'/api/learning/steps/{self.s1.id}/?run_id={self.a.id}').status_code,200)
        self.assertEqual(self.client.get(f'/api/learning/steps/{self.s2.id}/?run_id={self.a.id}').status_code,403)

    def test_module_opens_exactly_at_week_boundary_and_earlier_module_remains_open(self):
        self.save(); self.client.force_login(self.student)
        with patch('django.utils.timezone.now',return_value=self.start+timedelta(days=7)):
            for step in [self.s1,self.s2]:
                self.assertEqual(self.client.get(f'/api/learning/steps/{step.id}/?run_id={self.a.id}').status_code,200)

    def test_future_module_file_route_cannot_bypass_release(self):
        self.save(); material=LessonMaterial.objects.create(lesson=self.l2,title='Locked PDF',file='never-opened.pdf')
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(f'/api/learning/materials/{material.id}/open/?run_id={self.a.id}').status_code,403)

    def test_weekly_and_four_week_windows_and_attempt_deadline(self):
        self.save()
        weekly=ActivitySchedule.objects.get(run=self.a,quiz=self.quiz)
        monthly=ActivitySchedule.objects.get(run=self.a,quiz=self.month)
        self.assertEqual(weekly.opens_at,self.start+timedelta(days=5)); self.assertEqual(weekly.closes_at,self.start+timedelta(days=7))
        self.assertEqual(monthly.opens_at,self.start+timedelta(days=28)); self.assertEqual(monthly.closes_at,self.start+timedelta(days=30))
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(f'/api/study/quizzes/{self.quiz.id}/start/?run_id={self.a.id}', '{}',content_type='application/json').status_code,200)
        self.assertEqual(self.client.post(f'/api/study/quizzes/{self.month.id}/start/?run_id={self.a.id}', '{}',content_type='application/json').status_code,400)

    def test_student_cannot_write_or_read_other_group_plan(self):
        self.assertEqual(self.save(user=self.student).status_code,403)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(f'/api/courses/runs/{self.b.id}/learning-plan/').status_code,403)

    def test_unassigned_group_cannot_start_checkpoint_or_see_it_in_study(self):
        self.save(); self.client.force_login(self.peer)
        with patch('django.utils.timezone.now',return_value=self.start+timedelta(days=20)):
            response=self.client.get(f'/api/study/courses/{self.course.id}/?run_id={self.b.id}')
            self.assertEqual(response.status_code,200)
            self.assertNotIn(self.quiz.id,[q['id'] for q in response.json()['quizzes']])
            self.assertEqual(self.client.post(f'/api/study/quizzes/{self.quiz.id}/start/?run_id={self.b.id}','{}',content_type='application/json').status_code,403)

    def test_used_checkpoint_cannot_be_removed_rebound_or_rescheduled(self):
        self.save()
        QuizAttempt.objects.create(quiz=self.quiz,student=self.student,enrollment=self.e,attempt_no=1,deadline_at=timezone.now()+timedelta(minutes=5),max_score=1)
        data=self.payload(); data['checkpoints']=[]
        self.assertEqual(self.save(data).status_code,400)
        self.assertEqual(RunCheckpoint.objects.filter(run=self.a).count(),2)
        data=self.payload(); data['starts_at']=(self.start+timedelta(days=1)).isoformat()
        self.assertEqual(self.save(data).status_code,400)

    def test_required_checkpoints_contribute_to_progress_and_batch_matches(self):
        self.save()
        initial=course_progress(self.course,self.e); self.assertEqual(initial['total'],4)
        QuizAttempt.objects.create(quiz=self.quiz,student=self.student,enrollment=self.e,attempt_no=1,deadline_at=timezone.now(),status='finished',score=1,max_score=1,finished_at=timezone.now())
        single=course_progress(self.course,self.e); batch=course_progress_many([self.e])[self.e.id]
        self.assertEqual(single['completed'],1); self.assertEqual(single['percent'],25)
        self.assertEqual((single['completed'],single['total']),(batch['completed'],batch['total']))

    def test_duplicate_quiz_or_foreign_module_is_rejected_atomically(self):
        data=self.payload(); data['checkpoints'][1]['quiz_id']=self.quiz.id
        self.assertEqual(self.save(data).status_code,400); self.assertFalse(self.a.module_releases.exists())
        other=Course.objects.create(title='Other'); module=Module.objects.create(course=other,title='Foreign')
        data=self.payload(); data['modules'][0]['id']=module.id
        self.assertEqual(self.save(data).status_code,400)

    def test_group_tutor_can_plan_and_self_paced_cannot_use_weekly_plan(self):
        self.assertEqual(self.save(user=self.tutor).status_code,200)
        solo=CourseRun.objects.create(course=self.course,title='Solo',kind='self_paced')
        self.assertEqual(self.save(run=solo).status_code,400)

    def test_group_end_cannot_cut_off_assessments(self):
        self.save()
        response=self.client.patch(f'/api/courses/runs/{self.a.id}/', json.dumps({'ends_at': (self.start+timedelta(days=10)).isoformat()}), content_type='application/json')
        self.assertEqual(response.status_code,400,response.content)
        self.a.refresh_from_db(); self.assertIsNone(self.a.ends_at)

    def test_schedule_endpoint_cannot_bypass_learning_plan_dates(self):
        self.save()
        response=self.client.put(f'/api/study/courses/{self.course.id}/schedule/?run_id={self.a.id}',json.dumps({'kind':'quiz','id':self.quiz.id,'opens_at':self.start.isoformat(),'closes_at':(self.start+timedelta(days=9)).isoformat()}),content_type='application/json')
        self.assertEqual(response.status_code,400,response.content)
        self.assertEqual(ActivitySchedule.objects.get(run=self.a,quiz=self.quiz).closes_at,self.start+timedelta(days=7))

    def test_shared_step_and_checkpoint_count_once_with_stricter_threshold(self):
        self.save()
        step=Step.objects.create(lesson=self.l1,title='Quiz step',kind='quiz',quiz=self.quiz,required=True,pass_percent=30,is_published=True,position=2)
        QuizAttempt.objects.create(quiz=self.quiz,student=self.student,enrollment=self.e,attempt_no=1,deadline_at=timezone.now(),status='finished',score=1,max_score=2,finished_at=timezone.now())
        single=course_progress(self.course,self.e); batch=course_progress_many([self.e])[self.e.id]
        self.assertEqual(single['total'],4); self.assertEqual(single['completed'],0)
        self.assertNotIn(step.id,batch['step_ids'])
        self.assertEqual((single['completed'],single['total']),(batch['completed'],batch['total']))
