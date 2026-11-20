from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from courses.models import Course, CourseRun, Enrollment
from learning.models import Module, Lesson, Step, StepProgress
from assessment.models import Assignment, Submission, Quiz, Question, QuizAttempt, GradeReview
from communication.models import Discussion, Comment
from analytics.models import ActivityEvent, AttendanceDay, ProgressSnapshot, TrackingCoverage
from codejudge.models import CodeSubmission
from .models import LessonPulse, BankQuestion


class WorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.teacher = User.objects.create_user(username='teacher', role='teacher')
        cls.tutor = User.objects.create_user(username='tutor', role='teacher')
        cls.other = User.objects.create_user(username='other', role='teacher')
        cls.student = User.objects.create_user(username='student', role='student', first_name='Думан')
        cls.peer = User.objects.create_user(username='peer', role='student')
        cls.admin = User.objects.create_user(username='admin', role='admin')
        cls.course = Course.objects.create(title='Python', teacher=cls.teacher, is_published=True)
        cls.a = CourseRun.objects.create(course=cls.course, kind='cohort', title='A')
        cls.b = CourseRun.objects.create(course=cls.course, kind='cohort', title='B')
        cls.a.teachers.add(cls.tutor)
        cls.e = Enrollment.objects.create(course=cls.course, run=cls.a, student=cls.student)
        cls.ep = Enrollment.objects.create(course=cls.course, run=cls.a, student=cls.peer)
        cls.eb = Enrollment.objects.create(course=cls.course, run=cls.b, student=cls.peer)
        cls.module = Module.objects.create(course=cls.course, title='Module', is_published=True)
        cls.lesson = Lesson.objects.create(course=cls.course, module=cls.module, title='Lesson', is_published=True)
        cls.step = Step.objects.create(lesson=cls.lesson, title='Read', is_published=True, content='Theory')
        cls.assignment = Assignment.objects.create(course=cls.course, title='Write', max_score=10, is_published=True)
        cls.quiz = Quiz.objects.create(course=cls.course, title='Test', is_published=True)
        cls.q = Question.objects.create(quiz=cls.quiz, body='2+2?', options=['3', '4'], correct_index=1, position=1)
        cls.qstep = Step.objects.create(lesson=cls.lesson, title='Quiz', kind='quiz', quiz=cls.quiz, is_published=True, position=2)
        cls.discussion = Discussion.objects.create(lesson=cls.lesson, run=cls.a)

    def login(self, user):
        self.client.force_login(user)

    def put(self, path, data):
        return self.client.put(path, data=data, content_type='application/json')

    def post(self, path, data):
        return self.client.post(path, data=data, content_type='application/json')

    def test_home_roles_and_scope(self):
        for user, role in [(self.student, 'student'), (self.teacher, 'teacher'), (self.admin, 'admin')]:
            self.login(user)
            r = self.client.get('/api/workspace/home/')
            self.assertEqual(r.status_code, 200); self.assertEqual(r.json()['role'], role)
        self.login(self.tutor)
        self.assertEqual([v['id'] for v in self.client.get('/api/workspace/home/').json()['runs']], [self.a.id])
        self.assertEqual(self.client.get('/api/workspace/home/?personal=1').json()['role'], 'student')

    def test_student_resume_names_its_enrollment(self):
        # My learning matches the Continue card to the enrollment by id.
        Enrollment.objects.filter(pk=self.e.pk).update(last_step=self.step, last_seen_at=timezone.now())
        self.login(self.student)
        resume = self.client.get('/api/workspace/home/').json()['resume']
        self.assertEqual(resume['enrollment_id'], self.e.id)
        self.assertEqual(resume['lesson'], 'Read')
        self.assertIn(f'step={self.step.id}', resume['target'])

    def test_search_scopes_people_and_drafts(self):
        hidden = Course.objects.create(title='Secret', teacher=self.other)
        self.login(self.student)
        self.assertEqual(self.client.get('/api/workspace/search/?q=Secret').json()['results'], [])
        self.assertTrue(all(r['kind'] != 'Ученик' for r in self.client.get('/api/workspace/search/?q=Думан').json()['results']))
        self.login(self.other)
        self.assertTrue(any(r['title'] == hidden.title for r in self.client.get('/api/workspace/search/?q=Secret').json()['results']))
        self.assertFalse(any(r['kind'] == 'Ученик' for r in self.client.get('/api/workspace/search/?q=Думан').json()['results']))

    def test_question_peer_teacher_followup_and_resolution(self):
        path = f'/api/communication/lessons/{self.lesson.id}/discussion/?run_id={self.a.id}'
        self.login(self.student)
        root = self.post(path, {'body': 'Help'}).json()['id']
        self.login(self.peer); self.post(path, {'body': 'Maybe', 'parent_id': root})
        self.login(self.teacher)
        self.assertEqual(self.client.get('/api/workspace/questions/').json()['total'], 1)
        reply = self.post(path, {'body': 'Explain', 'parent_id': root}).json()['id']
        self.assertEqual(self.client.get('/api/workspace/questions/?state=answered').json()['total'], 1)
        self.login(self.student); self.post(path, {'body': 'More?', 'parent_id': reply})
        self.login(self.tutor)
        self.assertEqual(self.client.get('/api/workspace/questions/').json()['total'], 1)
        self.assertEqual(self.put(f'/api/workspace/policies/{self.b.id}/', {'inactive_days': 0, 'missing_count': 2, 'low_score_percent': 0}).status_code, 404)
        self.login(self.peer)
        self.assertEqual(self.client.patch(f'/api/communication/comments/{root}/', {'is_resolved': True}, content_type='application/json').status_code, 403)
        self.login(self.student)
        self.assertEqual(self.client.patch(f'/api/communication/comments/{root}/', {'is_resolved': True}, content_type='application/json').status_code, 200)
        self.login(self.teacher)
        self.assertEqual(self.client.get('/api/workspace/questions/?state=resolved').json()['total'], 1)

    def test_question_focus_includes_old_root_without_breaking_pagination(self):
        root = Comment.objects.create(discussion=self.discussion, author=self.student, body='Old')
        for i in range(25):
            Comment.objects.create(discussion=self.discussion, author=self.peer, body=str(i))
        self.login(self.tutor)
        r = self.client.get(f'/api/communication/lessons/{self.lesson.id}/discussion/?run_id={self.a.id}&focus={root.id}').json()
        self.assertIn(root.id, [t['root']['id'] for t in r['threads']]); self.assertEqual(r['total_threads'], 26)

    def test_student_cannot_use_management_endpoints(self):
        self.login(self.student)
        for path in ['/api/workspace/questions/', '/api/workspace/bank/', f'/api/workspace/policies/{self.a.id}/']:
            self.assertEqual(self.client.get(path).status_code, 403)

    def test_pulse_unique_and_run_isolated(self):
        path = f'/api/workspace/lessons/{self.lesson.id}/pulse/?run_id={self.a.id}'
        self.login(self.student)
        self.assertEqual(self.put(path, {'choice': 'hard', 'note': 'Need help'}).status_code, 200)
        self.assertEqual(self.put(path, {'choice': 'example', 'note': 'Example'}).status_code, 200)
        self.assertEqual(LessonPulse.objects.count(), 1)
        self.assertEqual(self.put(path, {'choice': 'invalid'}).status_code, 400)
        self.assertEqual(self.client.get(f'/api/workspace/lessons/{self.lesson.id}/pulse/?run_id={self.b.id}').status_code, 403)
        self.login(self.teacher)
        r = self.client.get(path).json(); self.assertEqual(r['counts'], {'example': 1})
        self.assertEqual(self.put(path, {'choice': 'clear'}).status_code, 403)

    def test_rubric_sum_freeze_and_grade_conflict(self):
        self.login(self.teacher)
        path = f'/api/workspace/assignments/{self.assignment.id}/rubric/?run_id={self.a.id}'
        self.assertEqual(self.put(path, {'version': 0, 'criteria': [{'label': 'Correct', 'max': 9}]}).status_code, 400)
        self.assertEqual(self.put(path, {'version': 0, 'criteria': [{'label': 'Correct', 'max': 6}, {'label': 'Explain', 'max': 4}]}).status_code, 200)
        self.assertEqual(self.put(path, {'version': 0, 'criteria': []}).status_code, 409)
        s = Submission.objects.create(assignment=self.assignment, enrollment=self.e, student=self.student, attempt_no=1, text_answer='Answer')
        self.assertEqual(self.put(path, {'version': 1, 'criteria': []}).status_code, 409)
        url = f'/api/workspace/reviews/{s.id}/'
        payload = {'expected_version': 0, 'score': 8, 'feedback': 'Good', 'criteria_scores': {'1': 5, '2': 3}}
        self.assertEqual(self.put(url, {**payload, 'criteria_scores': {'1': 7, '2': 1}}).status_code, 400)
        self.assertEqual(self.put(url, payload).status_code, 200)
        self.assertEqual(self.put(url, payload).status_code, 409)
        s.refresh_from_db(); self.assertEqual(s.score, 8); self.assertEqual(s.review_version, 1)
        self.assertEqual(s.rubric_result['criteria'][0]['score'], 5)
        self.assertEqual(s.reviews.get().rubric_result, s.rubric_result)

    def test_review_foreign_run_hidden(self):
        s = Submission.objects.create(assignment=self.assignment, enrollment=self.eb, student=self.peer, attempt_no=1)
        self.login(self.tutor)
        self.assertEqual(self.client.get(f'/api/workspace/reviews/{s.id}/').status_code, 404)
        self.login(self.student)
        self.assertEqual(self.client.get(f'/api/workspace/reviews/{s.id}/').status_code, 403)

    def test_policy_threshold_and_individual_extension(self):
        from assessment.models import AssignmentExtension
        self.assignment.due_at = timezone.now()-timedelta(days=1); self.assignment.save()
        self.login(self.teacher)
        self.put(f'/api/workspace/policies/{self.a.id}/', {'inactive_days': 0, 'missing_count': 1, 'low_score_percent': 0})
        self.assertEqual(len(self.client.get('/api/workspace/home/').json()['attention']), 2)
        AssignmentExtension.objects.create(assignment=self.assignment, enrollment=self.e, deadline_at=timezone.now()+timedelta(days=2))
        rows = self.client.get('/api/workspace/home/').json()['attention']
        self.assertFalse(any(r['id'] == self.e.id for r in rows))

    def test_inactivity_does_not_invent_pretracking_history(self):
        self.login(self.teacher)
        self.put(f'/api/workspace/policies/{self.a.id}/', {'inactive_days': 1, 'missing_count': 0, 'low_score_percent': 0})
        Enrollment.objects.filter(pk=self.e.id).update(enrolled_at=timezone.now()-timedelta(days=30))
        TrackingCoverage.objects.all().delete(); TrackingCoverage.objects.create(started_at=timezone.now())
        self.assertEqual(self.client.get('/api/workspace/home/').json()['attention'], [])

    def test_bank_versions_are_immutable_and_scoped(self):
        self.login(self.teacher)
        data = {'course_id': self.course.id, 'body': '2+2', 'options': ['3', '4'], 'correct_index': 1, 'category': 'Math'}
        r = self.post('/api/workspace/bank/', data); self.assertEqual(r.status_code, 201)
        old = r.json()['id']
        r = self.post('/api/workspace/bank/', {**data, 'previous_id': old, 'body': 'Changed'})
        self.assertEqual(r.json()['version'], 2)
        self.assertEqual(BankQuestion.objects.get(pk=old).body, '2+2')
        self.assertEqual(self.post('/api/workspace/bank/', {**data, 'previous_id': old}).status_code, 409)
        self.q.refresh_from_db(); self.assertEqual(self.q.body, '2+2?')
        self.login(self.tutor)
        self.assertEqual(self.client.get('/api/workspace/bank/').json()['questions'], [])
        self.assertEqual(self.post('/api/workspace/bank/', data).status_code, 404)

    def test_clone_remaps_content_without_people_answers_or_dates(self):
        self.assignment.due_at = timezone.now(); self.assignment.save()
        Step.objects.create(lesson=self.lesson, title='Assignment', position=3, kind='assignment', assignment=self.assignment, is_published=True)
        Submission.objects.create(assignment=self.assignment, enrollment=self.e, student=self.student, attempt_no=1)
        self.login(self.teacher)
        r = self.post(f'/api/workspace/courses/{self.course.id}/clone/', {'title': 'Copy'})
        self.assertEqual(r.status_code, 201)
        c = Course.objects.get(pk=r.json()['course_id']); self.assertFalse(c.is_published)
        self.assertFalse(c.enrollments.exists()); self.assertEqual(c.runs.count(), 1)
        self.assertIsNone(c.assignments.get().due_at); self.assertFalse(c.assignments.get().submissions.exists())
        for s in Step.objects.filter(lesson__course=c):
            if s.assignment: self.assertEqual(s.assignment.course_id, c.id)
            if s.quiz: self.assertEqual(s.quiz.course_id, c.id)
        self.assertEqual(c.quizzes.get().questions.get().body, '2+2?')
        self.login(self.tutor)
        self.assertEqual(self.post(f'/api/workspace/courses/{self.course.id}/clone/', {'title': 'Forbidden'}).status_code, 403)

    def test_preview_isolated_and_quiz_works(self):
        self.login(self.teacher)
        models = [CourseRun, Enrollment, StepProgress, Submission, QuizAttempt, CodeSubmission, GradeReview, ActivityEvent, AttendanceDay, ProgressSnapshot]
        counts = [m.objects.count() for m in models]
        url = f'/api/workspace/courses/{self.course.id}/preview/?run_id={self.a.id}'
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.post(url, {'step_id': self.qstep.id, 'answers': {str(self.q.id): 1}, 'completed': []})
        self.assertEqual(r.status_code, 200); self.assertTrue(r.json()['passed'])
        self.assertEqual([m.objects.count() for m in models], counts)
        self.login(self.student); self.assertEqual(self.client.get(url).status_code, 403)

    def test_preview_assignment_review_is_explicit_and_isolated(self):
        s = Step.objects.create(lesson=self.lesson, position=3, title='Write', kind='assignment', assignment=self.assignment, is_published=True)
        self.login(self.teacher)
        url = f'/api/workspace/courses/{self.course.id}/preview/?run_id={self.a.id}'
        self.assertFalse(self.post(url, {'step_id': s.id}).json()['passed'])
        self.assertTrue(self.post(url, {'step_id': s.id, 'simulate_review': True, 'preview_score': 10}).json()['passed'])
        self.assertFalse(Submission.objects.exists()); self.assertFalse(GradeReview.objects.exists())

    def test_preview_prerequisites_and_hidden_steps(self):
        second = Module.objects.create(course=self.course, title='Second', position=2, prerequisite=self.module, is_published=True)
        lesson = Lesson.objects.create(course=self.course, module=second, title='Next', position=2, is_published=True)
        step = Step.objects.create(lesson=lesson, title='Next', is_published=True)
        self.login(self.teacher)
        url = f'/api/workspace/courses/{self.course.id}/preview/?run_id={self.a.id}'
        self.assertEqual(self.post(url, {'step_id': step.id, 'completed': []}).status_code, 403)
        self.assertTrue(self.post(url, {'step_id': step.id, 'completed': [self.step.id, self.qstep.id]}).json()['passed'])
        step.is_published = False; step.save()
        self.assertEqual(self.post(url, {'step_id': step.id}).status_code, 404)

    def test_tutor_preview_selects_an_assigned_run(self):
        self.login(self.tutor)
        self.assertEqual(self.client.get(f'/api/workspace/courses/{self.course.id}/preview/').json()['run_id'], self.a.id)

    def test_question_insights_first_attempt_distribution_and_scope(self):
        now = timezone.now()
        for number, answer in [(1, 0), (2, 1)]:
            QuizAttempt.objects.create(quiz=self.quiz, enrollment=self.e, student=self.student, attempt_no=number,
                deadline_at=now, finished_at=now, status='finished', answers={str(self.q.id): answer}, score=answer, max_score=1)
        self.login(self.tutor)
        r = self.client.get(f'/api/workspace/question-insights/?run_id={self.a.id}').json()
        self.assertEqual(r['questions'][0]['samples'], 1); self.assertEqual(r['questions'][0]['correct_percent'], 0)
        self.assertEqual(self.client.get(f'/api/workspace/question-insights/?run_id={self.b.id}').status_code, 404)
        self.login(self.student); self.assertEqual(self.client.get('/api/workspace/question-insights/').status_code, 403)

    def test_unassigned_queue_keeps_scope_and_filters(self):
        Submission.objects.create(assignment=self.assignment, enrollment=self.e, student=self.student, attempt_no=1)
        Submission.objects.create(assignment=self.assignment, enrollment=self.ep, student=self.peer, attempt_no=1, reviewer=self.teacher)
        Submission.objects.create(assignment=self.assignment, enrollment=self.eb, student=self.peer, attempt_no=1)
        self.login(self.tutor)
        data = self.client.get('/api/study/review-queue/?unassigned=1').json()
        self.assertEqual(data['total'], 1); self.assertEqual(data['works'][0]['run_id'], self.a.id)

    def test_diagnostic_quiz_does_not_trigger_low_score_signal(self):
        self.qstep.pass_percent = 0; self.qstep.save()
        now = timezone.now()
        QuizAttempt.objects.create(quiz=self.quiz, enrollment=self.e, student=self.student, attempt_no=1,
            deadline_at=now, finished_at=now, status='finished', answers={}, score=0, max_score=1)
        self.login(self.teacher)
        self.put(f'/api/workspace/policies/{self.a.id}/', {'inactive_days': 0, 'missing_count': 0, 'low_score_percent': 60})
        self.assertEqual(self.client.get('/api/workspace/home/').json()['attention'], [])

    def test_preview_respects_run_schedule_without_hiding_readable_content(self):
        from assessment.models import ActivitySchedule
        ActivitySchedule.objects.create(run=self.a, quiz=self.quiz, opens_at=timezone.now()+timedelta(days=1))
        self.login(self.teacher)
        url = f'/api/workspace/courses/{self.course.id}/preview/?run_id={self.a.id}'
        rows = self.client.get(url).json()['steps']
        q = next(r for r in rows if r['id'] == self.qstep.id)
        self.assertTrue(q['action_reason']); self.assertEqual(q['reason'], '')
        self.assertEqual(self.post(url, {'step_id': self.qstep.id, 'answers': {str(self.q.id): 1}}).status_code, 403)

    def test_inactivity_counts_learner_actions_but_not_timer_or_teacher(self):
        self.login(self.teacher)
        self.put(f'/api/workspace/policies/{self.a.id}/', {'inactive_days': 7, 'missing_count': 0, 'low_score_percent': 0})
        old = timezone.now()-timedelta(days=10)
        Enrollment.objects.filter(pk=self.e.id).update(enrolled_at=old, last_seen_at=old)
        TrackingCoverage.objects.all().delete(); TrackingCoverage.objects.create(started_at=old)
        event = ActivityEvent.objects.create(user=self.student, enrollment=self.e, run=self.a, kind='quiz_answered', actor_role='student')
        self.assertFalse(any(r['id'] == self.e.id for r in self.client.get('/api/workspace/home/').json()['attention']))
        event.kind = 'quiz_finished_auto'; event.save()
        ActivityEvent.objects.create(user=self.teacher, enrollment=self.e, run=self.a, kind='assignment_reviewed', actor_role='teacher')
        self.assertTrue(any(r['id'] == self.e.id for r in self.client.get('/api/workspace/home/').json()['attention']))
