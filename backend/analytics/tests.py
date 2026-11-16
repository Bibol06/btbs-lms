from datetime import timedelta, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.utils import timezone

from assessment.models import Assignment, Submission, Quiz, Question, QuizAttempt, GradeReview
from courses.models import Course, CourseRun, Enrollment
from learning.models import Lesson, Step, StepProgress
from learning.services import course_progress, course_progress_many, refresh_completion
from .models import ActivityEvent, AttendanceDay, SessionRecord, ProgressSnapshot, LessonEvaluation
from .tracking import record, capture_progress, device_info, report_zone


class AnalyticsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user(username='analytics_admin', role='admin')
        cls.teacher = User.objects.create_user(username='analytics_teacher', role='teacher')
        cls.tutor = User.objects.create_user(username='analytics_tutor', role='teacher')
        cls.student = User.objects.create_user(username='analytics_student', first_name='Думан', last_name='Нурланов', password='Original-Strong-Pass-2026')
        cls.peer = User.objects.create_user(username='analytics_peer')
        cls.course = Course.objects.create(title='Learning analytics', teacher=cls.teacher, is_published=True)
        cls.a = CourseRun.objects.create(course=cls.course, title='A', kind='cohort')
        cls.b = CourseRun.objects.create(course=cls.course, title='B', kind='cohort')
        cls.a.teachers.add(cls.tutor)
        cls.enrollment = Enrollment.objects.create(course=cls.course, run=cls.a, student=cls.student)
        cls.other = Enrollment.objects.create(course=cls.course, run=cls.b, student=cls.student)
        cls.peer_enrollment = Enrollment.objects.create(course=cls.course, run=cls.a, student=cls.peer)
        cls.lesson = Lesson.objects.create(course=cls.course, title='Material', is_published=True)
        cls.step = Step.objects.create(lesson=cls.lesson, title='Theory', is_published=True)
        cls.assignment = Assignment.objects.create(course=cls.course, title='Essay', is_published=True)
        cls.pre = Quiz.objects.create(course=cls.course, title='Before', is_published=True)
        cls.post = Quiz.objects.create(course=cls.course, title='After', is_published=True)
        cls.q1 = Question.objects.create(quiz=cls.pre, body='Pre', options=['A','B'], correct_index=0, position=1)
        cls.q2 = Question.objects.create(quiz=cls.post, body='Post', options=['A','B'], correct_index=0, position=1)

    def get(self, suffix='dashboard/', params=None):
        return self.client.get('/api/analytics/'+suffix, params or {})

    def send(self, path, data=None):
        return self.client.post('/api/analytics/'+path, data=json.dumps(data or {}), content_type='application/json')

    def test_roles_and_direct_ids_cannot_cross_scope(self):
        self.assertEqual(self.get().status_code, 401)
        self.client.force_login(self.student)
        self.assertEqual(self.get(params={'role':'teacher'}).status_code, 403)
        self.assertEqual(self.get(params={'role':'admin'}).status_code, 403)
        self.assertEqual(self.get(params={'enrollment_id':self.peer_enrollment.id}).status_code, 404)
        self.assertEqual(self.get('sessions/').status_code, 403)
        self.assertEqual(self.send('evaluations/', {'run_id':self.a.id,'lesson_id':self.lesson.id,'pre_quiz_id':self.pre.id,'post_quiz_id':self.post.id}).status_code, 403)
        self.client.force_login(self.tutor)
        self.assertEqual(self.get(params={'run_id':self.b.id}).status_code, 404)
        self.assertEqual(self.get(params={'enrollment_id':self.other.id}).status_code, 404)
        self.assertEqual(self.get('sessions/').status_code, 403)
        rows = self.get().json()['learners']
        self.assertEqual({r['enrollment_id'] for r in rows}, {self.enrollment.id,self.peer_enrollment.id})

    def test_student_response_does_not_reveal_answers_or_devices(self):
        self.client.force_login(self.student)
        data = self.get().json()
        self.assertEqual({r['id'] for r in data['learners']}, {self.student.id})
        self.assertEqual(data['materials']['lessons'], [])
        self.assertEqual(data['teacher_work'], [])
        text = json.dumps(data)
        for secret in ('correct_index', 'user_agent', 'key_digest', 'ip_address', 'text_answer'):
            self.assertNotIn(secret, text)
        self.assertEqual({p['id'] for p in self.get('attendance/').json()['people']}, {self.student.id})

    def test_bulk_progress_matches_engine_and_snapshots_are_not_backdated(self):
        StepProgress.objects.create(step=self.step, enrollment=self.enrollment)
        batch = course_progress_many([self.enrollment,self.other])
        for e in (self.enrollment,self.other):
            self.assertEqual({k:batch[e.id][k] for k in ('completed','total','percent')}, course_progress(self.course,e))
        before = timezone.now()
        capture_progress(self.enrollment, batch[self.enrollment.id])
        capture_progress(self.enrollment, batch[self.enrollment.id])
        capture_progress(self.enrollment, {'completed':0,'total':1,'percent':0})
        self.assertEqual(ProgressSnapshot.objects.filter(enrollment=self.enrollment).count(),1)
        self.assertGreaterEqual(ProgressSnapshot.objects.get(enrollment=self.enrollment).captured_at, before)
        self.client.force_login(self.student)
        series = self.get(params={'enrollment_id':self.enrollment.id}).json()['series']
        self.assertTrue(all(d['progress'] is None for d in series[:-1]))
        self.assertEqual(series[-1]['progress'],100)

    def test_program_change_and_unmark_create_real_snapshots(self):
        capture_progress(self.enrollment, course_progress(self.course,self.enrollment))
        StepProgress.objects.create(step=self.step,enrollment=self.enrollment)
        refresh_completion(self.enrollment)
        Step.objects.create(lesson=self.lesson,title='New',position=2,is_published=True)
        capture_progress(self.enrollment,course_progress(self.course,self.enrollment))
        snapshots=list(ProgressSnapshot.objects.filter(enrollment=self.enrollment).order_by('captured_at'))
        self.assertEqual([(s.completed,s.total) for s in snapshots],[(0,1),(1,1),(1,2)])
        self.assertEqual(snapshots[-1].reason,'content')

    def test_login_devices_logout_and_no_raw_session_key_exposed(self):
        self.client.post('/api/auth/login/', data=json.dumps({'username':self.student.username,'password':'Original-Strong-Pass-2026'}), content_type='application/json',
            HTTP_USER_AGENT='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0', REMOTE_ADDR='192.0.2.25')
        session = SessionRecord.objects.get(user=self.student)
        self.assertEqual((session.device,session.os,session.browser,session.ip_address),('Компьютер','Windows','Edge 140','192.0.2.25'))
        raw_key = self.client.session.session_key
        self.assertNotEqual(raw_key,session.key_digest)
        self.assertEqual(AttendanceDay.objects.get(user=self.student).login_count,1)
        self.client.post('/api/auth/logout/')
        session.refresh_from_db()
        self.assertIsNotNone(session.ended_at)
        self.client.force_login(self.admin)
        data = self.get('sessions/', {'person_id':self.student.id}).json()
        self.assertEqual(data['sessions'][0]['status'],'ended')
        self.assertNotIn(raw_key,json.dumps(data))
        self.assertNotIn(session.key_digest,json.dumps(data))

    def test_polling_does_not_extend_presence_and_forwarded_ip_is_not_trusted(self):
        self.client.force_login(self.student)
        session=SessionRecord.objects.get(user=self.student)
        old=timezone.now()-timedelta(hours=1)
        SessionRecord.objects.filter(pk=session.id).update(last_seen_at=old)
        for url in ('/api/auth/me/','/api/communication/notifications/','/api/analytics/dashboard/'):
            self.client.get(url)
        session.refresh_from_db()
        self.assertEqual(session.last_seen_at,old)
        self.client.post('/api/analytics/presence/', data='{}', content_type='application/json', REMOTE_ADDR='192.0.2.50', HTTP_X_FORWARDED_FOR='8.8.8.8')
        session.refresh_from_db()
        self.assertGreater(session.last_seen_at,old)
        # The IP of the actual login remains the recorded connection address.
        self.assertNotEqual(session.ip_address,'8.8.8.8')

    def test_presence_cannot_spoof_user_and_event_is_idempotent(self):
        self.client.force_login(self.student)
        self.send('presence/',{'user_id':self.peer.id,'occurred_at':'2000-01-01'})
        self.send('presence/',{'user_id':self.peer.id})
        self.assertEqual(ActivityEvent.objects.filter(kind='platform_active',user=self.student).count(),1)
        self.assertFalse(AttendanceDay.objects.filter(user=self.peer).exists())
        record(self.student,'assignment_submitted',enrollment=self.enrollment,dedupe='same-source')
        record(self.student,'assignment_submitted',enrollment=self.enrollment,dedupe='same-source')
        self.assertEqual(ActivityEvent.objects.filter(dedupe_key='same-source').count(),1)

    def test_auto_finished_test_is_not_student_attendance(self):
        record(self.student,'quiz_finished_auto',enrollment=self.enrollment,dedupe='timer',active=False)
        self.assertFalse(AttendanceDay.objects.filter(user=self.student).exists())
        self.client.force_login(self.tutor)
        data=self.get('attendance/',{'run_id':self.a.id}).json()
        student=next(p for p in data['people'] if p['id']==self.student.id)
        self.assertEqual(student['active_days'],0)

    def test_browser_timer_request_is_not_presence(self):
        self.client.force_login(self.student)
        AttendanceDay.objects.filter(user=self.student).delete()
        now=timezone.now()
        attempt=QuizAttempt.objects.create(quiz=self.pre,student=self.student,enrollment=self.enrollment,attempt_no=1,
            deadline_at=now-timedelta(minutes=1),max_score=1,answers={str(self.q1.id):0})
        response=self.client.post(f'/api/study/attempts/{attempt.id}/',data='{"finish_saved":true}',content_type='application/json')
        self.assertEqual(response.status_code,200)
        self.assertFalse(AttendanceDay.objects.filter(user=self.student).exists())

    def test_step_visit_completion_and_undo_are_instrumented_without_double_count(self):
        self.client.force_login(self.student)
        url=f'/api/learning/steps/{self.step.id}/visit/?run_id={self.a.id}'
        self.assertEqual(self.client.post(url,data='{}',content_type='application/json').status_code,200)
        self.client.post(url,data='{}',content_type='application/json')
        self.assertEqual(ActivityEvent.objects.filter(kind='step_view',user=self.student).count(),1)
        url=f'/api/learning/steps/{self.step.id}/complete/?run_id={self.a.id}'
        self.client.post(url,data='{"completed":true}',content_type='application/json')
        self.client.post(url,data='{"completed":true}',content_type='application/json')
        self.client.post(url,data='{"completed":false}',content_type='application/json')
        self.assertEqual(ActivityEvent.objects.filter(kind='step_completed').count(),1)
        self.assertEqual(ActivityEvent.objects.filter(kind='step_reopened').count(),1)

    def test_distinct_fast_revisits_are_preserved_but_retries_are_idempotent(self):
        from uuid import uuid4
        self.client.force_login(self.student)
        url=f'/api/learning/steps/{self.step.id}/visit/?run_id={self.a.id}'
        visit=str(uuid4())
        for value in (visit,visit,str(uuid4())):
            response=self.client.post(url,data=json.dumps({'visit_id':value}),content_type='application/json')
            self.assertEqual(response.status_code,200)
        self.assertEqual(ActivityEvent.objects.filter(kind='step_view',user=self.student).count(),2)

    def test_real_before_after_sequence_and_no_matching_without_exposure(self):
        now=timezone.now()
        pre=QuizAttempt.objects.create(quiz=self.pre,student=self.student,enrollment=self.enrollment,attempt_no=1,deadline_at=now,status='finished',score=0,max_score=1,finished_at=now-timedelta(minutes=5))
        QuizAttempt.objects.filter(pk=pre.id).update(started_at=now-timedelta(minutes=6))
        post=QuizAttempt.objects.create(quiz=self.post,student=self.student,enrollment=self.enrollment,attempt_no=1,deadline_at=now,status='finished',score=1,max_score=1,finished_at=now-timedelta(minutes=1))
        QuizAttempt.objects.filter(pk=post.id).update(started_at=now-timedelta(minutes=2))
        LessonEvaluation.objects.create(lesson=self.lesson,run=self.a,pre_quiz=self.pre,post_quiz=self.post)
        self.client.force_login(self.tutor)
        row=self.get().json()['materials']['lessons'][0]
        self.assertEqual(row['comparison']['pairs'],0)
        # An older view before the pre-test does not block a later valid revisit.
        ActivityEvent.objects.create(user=self.student,enrollment=self.enrollment,run=self.a,step=self.step,lesson=self.lesson,kind='step_view',actor_role='student',occurred_at=now-timedelta(minutes=7))
        ActivityEvent.objects.create(user=self.student,enrollment=self.enrollment,run=self.a,step=self.step,lesson=self.lesson,kind='step_view',actor_role='student',occurred_at=now-timedelta(minutes=3))
        row=self.get().json()['materials']['lessons'][0]
        self.assertEqual(row['comparison'],{'pairs':1,'before':0.0,'after':100.0,'change':100.0})

    def test_evaluation_rejects_foreign_quiz_and_identical_tests(self):
        foreign=Course.objects.create(title='Foreign')
        quiz=Quiz.objects.create(course=foreign,title='No access',is_published=True)
        self.client.force_login(self.tutor)
        values={'run_id':self.a.id,'lesson_id':self.lesson.id,'pre_quiz_id':self.pre.id,'post_quiz_id':quiz.id}
        self.assertEqual(self.send('evaluations/',values).status_code,404)
        values['post_quiz_id']=self.pre.id
        self.assertEqual(self.send('evaluations/',values).status_code,400)
        values['post_quiz_id']=self.post.id
        self.assertEqual(self.send('evaluations/',values).status_code,200)

    def test_timezone_day_boundaries_and_invalid_periods(self):
        self.client.force_login(self.admin)
        for values in ({'period':'custom','from':'bad','to':'bad'},{'period':'custom','from':'2026-01-02','to':'2026-01-01'},{'period':'wrong'}):
            self.assertEqual(self.get(params=values).status_code,400)
        stamp=datetime(2026,10,24,20,5,tzinfo=ZoneInfo('UTC'))
        record(self.student,'step_completed',enrollment=self.enrollment,when=stamp)
        self.assertTrue(AttendanceDay.objects.filter(user=self.student,date=stamp.astimezone(report_zone()).date()).exists())

    def test_admin_filters_attendance_by_group_and_exports_respect_access(self):
        self.client.force_login(self.admin)
        data=self.get('attendance/',{'run_id':self.a.id,'person_role':'student'}).json()
        self.assertEqual({p['id'] for p in data['people']},{self.student.id,self.peer.id})
        response=self.get('export/',{'kind':'sessions'})
        self.assertEqual(response.status_code,200)
        self.assertNotIn('key_digest',response.content.decode('utf-8-sig'))
        self.client.force_login(self.student)
        self.assertEqual(self.get('export/',{'kind':'sessions'}).status_code,403)
        self.assertEqual(self.get('export/',{'kind':'learners'}).status_code,200)

    def test_review_metrics_count_unique_work_separately_from_edits(self):
        submission=Submission.objects.create(assignment=self.assignment,student=self.student,enrollment=self.enrollment,attempt_no=1)
        for score in (50,80):
            GradeReview.objects.create(submission=submission,reviewer=self.tutor,action='graded',score=score)
        self.client.force_login(self.admin)
        data=self.get().json()
        self.assertEqual(data['summary']['first_reviews'],1)
        self.assertEqual(data['summary']['reviews'],2)
        tutor=next(t for t in data['teacher_work'] if t['id']==self.tutor.id)
        self.assertEqual((tutor['reviews'],tutor['unique_works'],tutor['first_reviews']),(2,1,1))

    def test_pagination_full_name_search_and_mobile_device_classification(self):
        self.assertEqual(device_info('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Version/18.0 Mobile/15E148 Safari/604.1'),('Safari 18','iOS','Телефон'))
        self.client.force_login(self.admin)
        self.assertEqual(self.get('attendance/',{'search':'Нурланов Думан'}).json()['total'],1)
        self.assertEqual(self.get('attendance/',{'page':0}).status_code,400)

    def test_exports_escape_formulas_and_start_from_first_page(self):
        from io import StringIO
        import csv
        User=get_user_model()
        for i in range(22):
            person=User.objects.create_user(username=f'export_{i}',first_name=f'Person {i}')
            Enrollment.objects.create(course=self.course,run=self.a,student=person)
        User.objects.filter(pk=self.peer.id).update(last_name='=FORMULA')
        self.client.force_login(self.admin)
        response=self.get('export/',{'kind':'learners','page':2})
        self.assertEqual(response.status_code,200)
        rows=list(csv.reader(StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(len(rows)-2,25)
        self.assertTrue(any(row and row[0].startswith("'=FORMULA") for row in rows))
        self.assertEqual(len({tuple(row[:3]) for row in rows[2:]}),25)

    def test_previous_period_counts_use_actual_source_dates(self):
        old=Submission.objects.create(assignment=self.assignment,student=self.student,enrollment=self.enrollment,attempt_no=1)
        Submission.objects.filter(pk=old.pk).update(submitted_at=timezone.now()-timedelta(days=8))
        Submission.objects.create(assignment=self.assignment,student=self.student,enrollment=self.enrollment,attempt_no=2)
        self.client.force_login(self.student)
        data=self.get(params={'period':'week','enrollment_id':self.enrollment.id}).json()
        self.assertEqual(data['summary']['submitted'],1)
        self.assertEqual(data['previous']['submitted'],1)

    def test_selected_student_options_keep_other_scoped_learners(self):
        self.client.force_login(self.tutor)
        data=self.get(params={'enrollment_id':self.enrollment.id}).json()
        self.assertEqual([s['enrollment_id'] for s in data['learners']],[self.enrollment.id])
        self.assertEqual({s['id'] for s in data['options']['enrollments']},{self.enrollment.id,self.peer_enrollment.id})

    def test_bulk_progress_assessments_match_course_rules(self):
        from codejudge.models import CodeProblem, CodeSubmission
        problem=CodeProblem.objects.create(course=self.course,title='Python',statement='Sum')
        Step.objects.create(lesson=self.lesson,title='Essay step',kind='assignment',assignment=self.assignment,position=2,is_published=True,pass_percent=70)
        Step.objects.create(lesson=self.lesson,title='Quiz step',kind='quiz',quiz=self.pre,position=3,is_published=True,pass_percent=60)
        Step.objects.create(lesson=self.lesson,title='Code step',kind='code',code_problem=problem,position=4,is_published=True)
        Submission.objects.create(assignment=self.assignment,student=self.student,enrollment=self.enrollment,attempt_no=1,status='graded',score=80)
        QuizAttempt.objects.create(quiz=self.pre,student=self.student,enrollment=self.enrollment,attempt_no=1,status='finished',score=1,max_score=1,deadline_at=timezone.now())
        CodeSubmission.objects.create(problem=problem,enrollment=self.enrollment,status='accepted',code='print(1)',passed=1,total=1)
        actual=course_progress_many([self.enrollment])[self.enrollment.id]
        self.assertEqual({k:actual[k] for k in ('completed','total','percent')},course_progress(self.course,self.enrollment))
        self.assertEqual(actual['completed'],3)

    def test_diagnostic_quiz_without_pass_threshold_is_not_mastery_success(self):
        Step.objects.create(lesson=self.lesson,title='Diagnostic',kind='quiz',quiz=self.pre,position=2,is_published=True,pass_percent=0)
        QuizAttempt.objects.create(quiz=self.pre,student=self.student,enrollment=self.enrollment,attempt_no=1,status='finished',score=0,max_score=1,
            deadline_at=timezone.now(),finished_at=timezone.now())
        self.client.force_login(self.tutor)
        row=self.get().json()['materials']['lessons'][0]
        self.assertEqual(row['attempt_samples'],0)
        self.assertIsNone(row['first_attempt_success'])

    def test_action_history_is_admin_only_filtered_and_has_no_answers(self):
        record(self.student,'step_view',enrollment=self.enrollment,step=self.step,dedupe='history-a')
        record(self.peer,'step_view',enrollment=self.peer_enrollment,step=self.step,dedupe='history-b')
        self.client.force_login(self.tutor)
        self.assertEqual(self.get('activity/').status_code,403)
        self.client.force_login(self.admin)
        data=self.get('activity/',{'person_id':self.student.id}).json()
        self.assertEqual(data['total'],1)
        self.assertEqual(data['events'][0]['person']['id'],self.student.id)
        self.assertNotIn('answers',json.dumps(data))
        self.assertEqual(self.get('export/',{'kind':'activity','person_id':self.student.id}).status_code,200)

    def test_material_attempt_counts_and_first_attempt_question_errors(self):
        Step.objects.create(lesson=self.lesson,title='Test',kind='quiz',quiz=self.pre,position=2,is_published=True,pass_percent=60)
        for number, score, answer in [(1,0,1),(2,1,0)]:
            QuizAttempt.objects.create(quiz=self.pre,student=self.student,enrollment=self.enrollment,attempt_no=number,status='finished',score=score,max_score=1,
                answers={str(self.q1.id):answer},deadline_at=timezone.now(),finished_at=timezone.now())
        self.client.force_login(self.tutor)
        row=self.get().json()['materials']['lessons'][0]
        self.assertEqual((row['attempts'],row['mean_attempts'],row['first_attempt_success']),(2,2.0,0.0))
        self.assertEqual(row['common_errors'][0]['wrong'],1)
        self.assertEqual(row['common_errors'][0]['samples'],1)
