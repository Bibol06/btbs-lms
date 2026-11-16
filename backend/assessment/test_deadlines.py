import json
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from courses.models import Course, CourseRun, Enrollment
from learning.models import Module, Lesson, Step
from communication.models import Notification
from communication.management.commands.notification_worker import remind_deadlines
from .models import Assignment, Submission, ActivitySchedule, AssignmentExtension, Quiz, Question, QuizAttempt
from .quiz_services import finalize_due_attempts


class DeadlineWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username='deadline_owner', role='teacher')
        cls.teacher = User.objects.create_user(username='deadline_teacher', role='teacher')
        cls.other_teacher = User.objects.create_user(username='deadline_other_teacher', role='teacher')
        cls.student = User.objects.create_user(username='deadline_student')
        cls.peer = User.objects.create_user(username='deadline_peer')
        cls.course = Course.objects.create(title='Deadlines', teacher=cls.owner, is_published=True)
        cls.cohort = CourseRun.objects.create(course=cls.course, title='A', kind='cohort')
        cls.other = CourseRun.objects.create(course=cls.course, title='B', kind='cohort')
        cls.cohort.teachers.add(cls.teacher)
        cls.other.teachers.add(cls.other_teacher)
        cls.enrollment = Enrollment.objects.create(course=cls.course, run=cls.cohort, student=cls.student)
        cls.peer_enrollment = Enrollment.objects.create(course=cls.course, run=cls.cohort, student=cls.peer)
        cls.assignment = Assignment.objects.create(course=cls.course, title='Written work', is_published=True, max_attempts=1)
        cls.module = Module.objects.create(course=cls.course, title='Module', is_published=True)
        cls.lesson = Lesson.objects.create(course=cls.course, module=cls.module, title='Lesson', is_published=True)
        cls.quiz = Quiz.objects.create(course=cls.course, title='Quiz', is_published=True, max_attempts=2, time_limit_sec=60)
        cls.question = Question.objects.create(quiz=cls.quiz, body='2+2?', options=['3','4'], correct_index=1, position=1)
        Step.objects.create(lesson=cls.lesson, title='Quiz step', kind='quiz', quiz=cls.quiz, is_published=True)

    def setUp(self):
        self.client.force_login(self.student)

    def url(self, path, run=None):
        return path + f'?run_id={(run or self.cohort).id}'

    def send(self, path, data=None, method='post', run=None):
        return getattr(self.client, method)(self.url(path, run), data=json.dumps(data or {}), content_type='application/json')

    def submit(self, assignment=None):
        return self.client.post(self.url(f'/api/study/assignments/{(assignment or self.assignment).id}/submit/'), {'text_answer':'Saved answer'})

    def extension(self, enrollment=None, deadline=None):
        return self.send(f'/api/study/assignments/{self.assignment.id}/extensions/', {'enrollment_id':(enrollment or self.enrollment).id, 'deadline_at':(deadline or timezone.now()+timedelta(days=2)).isoformat(), 'reason':'Agreed extension'})

    def attempt(self):
        return self.send(f'/api/study/quizzes/{self.quiz.id}/start/').json()['attempt']

    def expire_with_saved_answer(self):
        attempt = self.attempt()
        self.send(f'/api/study/attempts/{attempt["id"]}/', {'answers':{str(self.question.id):1}}, 'patch')
        QuizAttempt.objects.filter(pk=attempt['id']).update(deadline_at=timezone.now()-timedelta(seconds=1))
        return attempt

    def test_soft_deadline_accepts_late_without_changing_grade_or_history(self):
        self.assignment.due_at = timezone.now()-timedelta(hours=1)
        self.assignment.cutoff_at = timezone.now()+timedelta(days=1)
        self.assignment.allow_late = True
        self.assignment.save()
        response = self.submit()
        self.assertEqual(response.status_code,201)
        record = Submission.objects.get()
        self.assertTrue(record.is_late)
        self.assertEqual(record.due_at_snapshot,self.assignment.due_at)
        self.client.force_login(self.teacher)
        self.assertEqual(self.send(f'/api/study/submissions/{record.id}/grade/', {'score':100,'feedback':'Good'},'put').status_code,200)
        self.assignment.due_at = timezone.now()+timedelta(hours=2)
        self.assignment.save()
        record.refresh_from_db()
        self.assertTrue(record.is_late)
        self.assertEqual(record.score,100)
        self.assertLess(record.due_at_snapshot,timezone.now())

    def test_strict_deadline_and_final_cutoff_reject_submission(self):
        self.assignment.due_at = timezone.now()-timedelta(hours=1)
        self.assignment.save()
        self.assertEqual(self.submit().status_code,400)
        self.assignment.allow_late = True
        self.assignment.cutoff_at = timezone.now()-timedelta(minutes=1)
        self.assignment.save()
        self.assertEqual(self.submit().status_code,400)
        self.assertEqual(Submission.objects.count(),0)

    def test_group_policy_does_not_change_other_group(self):
        Enrollment.objects.create(course=self.course,run=self.other,student=self.student)
        self.assignment.due_at=timezone.now()-timedelta(days=1)
        self.assignment.save()
        ActivitySchedule.objects.create(run=self.cohort,assignment=self.assignment,due_at=timezone.now()-timedelta(hours=1),allow_late=True,review_hours=24)
        self.assertEqual(self.submit().status_code,201)
        response=self.client.post(self.url(f'/api/study/assignments/{self.assignment.id}/submit/',self.other), {'text_answer':'Other'})
        self.assertEqual(response.status_code,400)
        self.assertEqual(Submission.objects.get().reviewer,self.teacher)
        self.assertAlmostEqual((Submission.objects.get().review_due_at-timezone.now()).total_seconds(),24*3600,delta=15)

    def test_individual_extension_only_for_selected_student(self):
        self.assignment.due_at=timezone.now()-timedelta(hours=1);self.assignment.save()
        self.assertEqual(self.extension().status_code,403)
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.extension().status_code,403)
        self.client.force_login(self.teacher)
        self.assertEqual(self.extension().status_code,200)
        self.client.force_login(self.student)
        self.assertEqual(self.submit().status_code,201)
        self.assertFalse(Submission.objects.get().is_late)
        self.client.force_login(self.peer)
        self.assertEqual(self.submit().status_code,400)

    def test_personal_extension_allows_only_that_assignment_after_group_end(self):
        self.cohort.ends_at=timezone.now()-timedelta(hours=1);self.cohort.save()
        self.assertEqual(self.submit().status_code,400)
        self.client.force_login(self.teacher);self.assertEqual(self.extension().status_code,200)
        self.client.force_login(self.student)
        self.assertEqual(self.submit().status_code,201)
        other_work=Assignment.objects.create(course=self.course,title='Another',is_published=True)
        self.assertEqual(self.submit(other_work).status_code,400)
        self.assertEqual(self.send(f'/api/study/quizzes/{self.quiz.id}/start/').status_code,403)

    def test_return_after_deadline_grants_new_deadline_and_one_revision(self):
        record=Submission.objects.create(assignment=self.assignment,enrollment=self.enrollment,student=self.student,attempt_no=1,text_answer='First')
        self.assignment.due_at=timezone.now()-timedelta(days=1);self.assignment.save()
        due=timezone.now()+timedelta(days=3)
        self.client.force_login(self.teacher)
        response=self.send(f'/api/study/submissions/{record.id}/grade/', {'return_for_revision':True,'feedback':'Explain the solution','revision_due_at':due.isoformat()},'put')
        self.assertEqual(response.status_code,200)
        record.refresh_from_db()
        self.assertEqual(record.revision_due_at,due)
        self.assertEqual(record.reviews.get().revision_due_at,due)
        self.assertEqual(AssignmentExtension.objects.get().deadline_at,due)
        self.client.force_login(self.student)
        self.assertEqual(self.submit().status_code,201)
        revision=Submission.objects.exclude(pk=record.id).get()
        self.assertEqual(revision.revision_of,record)
        self.assertFalse(revision.is_late)
        self.assertEqual(self.submit().status_code,400)

    def test_returning_old_submission_or_past_revision_date_is_rejected(self):
        record=Submission.objects.create(assignment=self.assignment,enrollment=self.enrollment,student=self.student,attempt_no=1)
        self.client.force_login(self.teacher)
        response=self.send(f'/api/study/submissions/{record.id}/grade/', {'return_for_revision':True,'revision_due_at':(timezone.now()-timedelta(hours=1)).isoformat()},'put')
        self.assertEqual(response.status_code,400)
        record.refresh_from_db();self.assertEqual(record.status,'submitted')
        self.assertFalse(AssignmentExtension.objects.exists())
        Submission.objects.create(assignment=self.assignment,enrollment=self.enrollment,student=self.student,attempt_no=2)
        self.assertEqual(self.send(f'/api/study/submissions/{record.id}/grade/', {'return_for_revision':True},'put').status_code,400)

    def test_archived_enrollment_cannot_get_extension(self):
        self.enrollment.status='removed';self.enrollment.save()
        self.client.force_login(self.teacher)
        self.assertEqual(self.extension().status_code,400)

    def test_review_assignment_rejects_outside_teacher_and_respects_group(self):
        sid=self.submit().json()['submission']['id']
        self.client.force_login(self.teacher)
        url=f'/api/study/submissions/{sid}/reviewer/'
        self.assertEqual(self.send(url,{'reviewer_id':self.other_teacher.id},'patch').status_code,403)
        self.assertEqual(self.send(url,{'reviewer_id':self.owner.id},'patch').status_code,200)
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.send(url,{'reviewer_id':self.other_teacher.id},'patch').status_code,403)
        self.client.force_login(self.student)
        self.assertEqual(self.send(url,{'reviewer_id':self.student.id},'patch').status_code,403)

    def test_overdue_review_stays_gradable_and_queue_filters_are_scoped(self):
        sid=self.submit().json()['submission']['id']
        Submission.objects.filter(pk=sid).update(review_due_at=timezone.now()-timedelta(hours=1))
        self.client.force_login(self.teacher)
        queue=self.client.get('/api/study/review-queue/?state=overdue&mine=1').json()
        self.assertEqual(queue['total'],1)
        self.assertEqual(queue['works'][0]['review_state'],'overdue')
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.get('/api/study/review-queue/').json()['total'],0)
        self.client.force_login(self.teacher)
        self.assertEqual(self.send(f'/api/study/submissions/{sid}/grade/', {'score':80},'put').status_code,200)
        self.assertEqual(self.client.get('/api/study/review-queue/').json()['total'],0)

    def test_student_agenda_shows_waiting_reviewer_without_other_students_work(self):
        self.submit()
        data=self.client.get('/api/study/agenda/').json()
        task=next(t for t in data['student_tasks'] if t['kind']=='assignment')
        self.assertEqual(task['state'],'waiting')
        self.assertEqual(task['reviewer'],self.teacher.username)
        self.assertIsNotNone(task['review_due_at'])
        self.assertEqual(data['review_counts']['pending'],0)
        self.client.force_login(self.peer)
        task=next(t for t in self.client.get('/api/study/agenda/').json()['student_tasks'] if t['kind']=='assignment')
        self.assertEqual(task['state'],'open')
        self.assertIsNone(task['reviewer'])

    def test_deadline_validation_rejects_backwards_dates_and_invalid_review_hours(self):
        self.client.force_login(self.owner)
        url=f'/api/study/assignments/{self.assignment.id}/'
        self.assertEqual(self.send(url,{'due_at':timezone.now().isoformat(),'cutoff_at':(timezone.now()-timedelta(days=1)).isoformat()},'patch').status_code,400)
        for value in [0,721,True,'48']:
            self.assertEqual(self.send(url,{'review_hours':value},'patch').status_code,400)

    def test_review_reminders_go_to_responsible_teacher_once(self):
        sid=self.submit().json()['submission']['id']
        Submission.objects.filter(pk=sid).update(review_due_at=timezone.now()-timedelta(minutes=1))
        remind_deadlines();remind_deadlines()
        notifications=Notification.objects.filter(event__key__startswith=f'review-deadline:{sid}:')
        self.assertEqual(list(notifications.values_list('recipient_id',flat=True)),[self.teacher.id])
        self.client.force_login(self.teacher)
        self.send(f'/api/study/submissions/{sid}/grade/', {'score':90},'put')
        remind_deadlines()
        self.assertEqual(notifications.count(),1)

    def test_timed_out_quiz_scores_saved_answers_and_ignores_late_changes(self):
        attempt=self.expire_with_saved_answer()
        response=self.send(f'/api/study/attempts/{attempt["id"]}/', {'answers':{str(self.question.id):0}})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['attempt']['score'],1)
        self.assertTrue(response.json()['attempt']['auto_submitted'])
        saved=QuizAttempt.objects.get();self.assertEqual(saved.answers,{str(self.question.id):1})
        self.assertEqual(self.client.get(self.url(f'/api/study/courses/{self.course.id}/')).json()['progress']['percent'],100)

    def test_worker_finalizes_without_browser_and_does_not_repeat_notifications(self):
        attempt=self.expire_with_saved_answer()
        finalize_due_attempts();finalize_due_attempts()
        saved=QuizAttempt.objects.get(pk=attempt['id'])
        self.assertEqual(saved.status,'finished');self.assertEqual(saved.score,1)
        self.assertEqual(Notification.objects.filter(event__key=f'quiz-auto-finished:{saved.id}').count(),1)

    def test_finish_saved_before_deadline_keeps_attempt_active_and_answers(self):
        attempt=self.attempt()
        self.send(f'/api/study/attempts/{attempt["id"]}/', {'answers':{str(self.question.id):1}},'patch')
        response=self.send(f'/api/study/attempts/{attempt["id"]}/', {'finish_saved':True})
        self.assertEqual(response.json()['attempt']['status'],'active')
        self.assertEqual(QuizAttempt.objects.get().answers,{str(self.question.id):1})

    def test_resume_after_timer_does_not_start_an_unrequested_new_attempt(self):
        self.expire_with_saved_answer()
        response=self.send(f'/api/study/quizzes/{self.quiz.id}/start/')
        self.assertEqual(response.json()['attempt']['status'],'finished')
        self.assertEqual(response.json()['attempt']['score'],1)
        self.assertEqual(QuizAttempt.objects.count(),1)

    def test_quiz_timer_cannot_run_past_end_of_group(self):
        self.cohort.ends_at=timezone.now()+timedelta(seconds=30);self.cohort.save()
        attempt=self.attempt()
        saved=QuizAttempt.objects.get(pk=attempt['id'])
        self.assertEqual(saved.deadline_at,self.cohort.ends_at)

    def test_expired_group_does_not_discard_previously_saved_quiz_answers(self):
        attempt=self.expire_with_saved_answer()
        self.cohort.ends_at=timezone.now()-timedelta(seconds=1);self.cohort.save()
        response=self.send(f'/api/study/attempts/{attempt["id"]}/', {'finish_saved':True})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['attempt']['score'],1)
