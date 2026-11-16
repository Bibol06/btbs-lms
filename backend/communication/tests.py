import json
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from courses.models import Course, CourseRun, Enrollment, default_run
from learning.models import Module, Lesson, Step, StepProgress
from assessment.models import Assignment, Quiz, Question, Submission, QuizAttempt, ActivitySchedule
from .models import Notification, Event, Comment
from .services import notify


class PlatformTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username='owner', role='teacher')
        cls.teacher_a = User.objects.create_user(username='teacher_a', role='teacher')
        cls.teacher_b = User.objects.create_user(username='teacher_b', role='teacher')
        cls.a = User.objects.create_user(username='a')
        cls.b = User.objects.create_user(username='b')
        cls.course = Course.objects.create(title='Platform', teacher=cls.owner, is_published=True)
        cls.default = default_run(cls.course)
        cls.ra = CourseRun.objects.create(course=cls.course, title='Group A', kind='cohort', join_code='invite-a')
        cls.rb = CourseRun.objects.create(course=cls.course, title='Group B', kind='cohort', join_code='invite-b')
        cls.ra.teachers.add(cls.teacher_a)
        cls.rb.teachers.add(cls.teacher_b)
        cls.ea = Enrollment.objects.create(course=cls.course, run=cls.ra, student=cls.a)
        cls.eb = Enrollment.objects.create(course=cls.course, run=cls.rb, student=cls.b)
        cls.module = Module.objects.create(course=cls.course, title='Module', is_published=True)
        cls.lesson = Lesson.objects.create(course=cls.course, module=cls.module, title='Lesson', is_published=True)
        cls.step = Step.objects.create(lesson=cls.lesson, title='Theory', content='Secret theory', is_published=True)
        cls.assignment = Assignment.objects.create(course=cls.course, title='Homework', is_published=True)
        cls.quiz = Quiz.objects.create(course=cls.course, title='Quiz', is_published=True)
        cls.question = Question.objects.create(quiz=cls.quiz, body='Question', options=['A', 'B'], correct_index=0, position=1)

    def setUp(self):
        self.client.force_login(self.a)

    def url(self, path, run=None):
        return path + f'?run_id={(run or self.ra).id}'

    def send(self, path, data=None, method='post', run=None):
        return getattr(self.client, method)(self.url(path, run), json.dumps(data or {}), content_type='application/json')

    def test_student_cannot_access_another_group(self):
        for path in [f'/api/learning/courses/{self.course.id}/structure/', f'/api/study/courses/{self.course.id}/', f'/api/communication/courses/{self.course.id}/announcements/']:
            self.assertEqual(self.client.get(self.url(path, self.rb)).status_code, 403)

    def test_same_user_different_runs_have_independent_progress(self):
        Enrollment.objects.create(course=self.course, run=self.rb, student=self.a)
        self.assertEqual(self.send(f'/api/learning/steps/{self.step.id}/complete/').status_code, 200)
        self.assertTrue(StepProgress.objects.filter(enrollment=self.ea).exists())
        data = self.client.get(self.url(f'/api/learning/courses/{self.course.id}/structure/', self.rb)).json()
        self.assertEqual(data['progress']['completed'], 0)

    def test_assigned_teacher_can_grade_own_group_only(self):
        sa = Submission.objects.create(assignment=self.assignment, enrollment=self.ea, student=self.a, attempt_no=1)
        sb = Submission.objects.create(assignment=self.assignment, enrollment=self.eb, student=self.b, attempt_no=1)
        self.client.force_login(self.teacher_a)
        self.assertEqual(self.send(f'/api/study/submissions/{sa.id}/grade/', {'score': 80}, 'put').status_code, 200)
        self.assertEqual(self.send(f'/api/study/submissions/{sb.id}/grade/', {'score': 80}, 'put').status_code, 403)
        self.assertEqual(self.send(f'/api/learning/teacher/lessons/{self.lesson.id}/', {'title': 'Hacked'}, 'patch').status_code, 403)
        report = self.client.get(self.url(f'/api/study/courses/{self.course.id}/report/')).json()
        self.assertEqual([r['student'] for r in report['students']], ['a'])

    def test_deadline_overrides_are_group_specific(self):
        ActivitySchedule.objects.create(run=self.ra, assignment=self.assignment, due_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.client.post(self.url(f'/api/study/assignments/{self.assignment.id}/submit/'), {'text_answer': 'A'}).status_code, 400)
        self.client.force_login(self.b)
        self.assertEqual(self.client.post(self.url(f'/api/study/assignments/{self.assignment.id}/submit/', self.rb), {'text_answer': 'B'}).status_code, 201)

    def test_quiz_attempts_are_independent_across_groups(self):
        Enrollment.objects.create(course=self.course, run=self.rb, student=self.a)
        x = self.send(f'/api/study/quizzes/{self.quiz.id}/start/').json()['attempt']['id']
        y = self.send(f'/api/study/quizzes/{self.quiz.id}/start/', run=self.rb).json()['attempt']['id']
        self.assertNotEqual(x, y)
        self.assertEqual(QuizAttempt.objects.count(), 2)

    def test_group_invitation_and_closed_enrollment(self):
        self.client.force_login(self.b)
        response = self.send('/api/courses/join/', {'code': 'invite-a'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['run_id'], self.ra.id)
        self.ra.is_open = False
        self.ra.save()
        self.assertEqual(self.send('/api/courses/join/', {'code': 'invite-a'}).status_code, 404)

    def test_course_editor_can_be_student_elsewhere(self):
        self.client.force_login(self.owner)
        response = self.send(f'/api/courses/{self.course.id}/team/', {'username': 'a'})
        self.assertEqual(response.status_code, 200)
        self.client.force_login(self.a)
        self.assertTrue(self.client.get('/api/auth/me/').json()['can_teach'])
        other = Course.objects.create(title='Other', is_published=True)
        self.assertEqual(self.send(f'/api/courses/{other.id}/enroll/').status_code, 200)

    def test_future_module_does_not_leak_legacy_content(self):
        self.module.opens_at = timezone.now()+timedelta(days=1)
        self.module.save()
        self.assertEqual(self.client.get(self.url(f'/api/learning/steps/{self.step.id}/')).status_code, 403)
        legacy = self.client.get(self.url(f'/api/learning/courses/{self.course.id}/lessons/')).json()
        self.assertTrue(legacy['lessons'][0]['locked'])
        self.assertEqual(legacy['lessons'][0]['content'], '')

    def test_prerequisite_and_cycles(self):
        second = Module.objects.create(course=self.course, title='Second', position=2, is_published=True, prerequisite=self.module)
        lesson = Lesson.objects.create(course=self.course, module=second, title='Second', position=2, is_published=True)
        step = Step.objects.create(lesson=lesson, title='Second', is_published=True)
        self.assertEqual(self.client.get(self.url(f'/api/learning/steps/{step.id}/')).status_code, 403)
        self.send(f'/api/learning/steps/{self.step.id}/complete/')
        self.assertEqual(self.client.get(self.url(f'/api/learning/steps/{step.id}/')).status_code, 200)
        self.client.force_login(self.owner)
        self.assertEqual(self.send(f'/api/learning/modules/{self.module.id}/', {'prerequisite_id': second.id}, 'patch').status_code, 400)

    def test_test_step_cannot_be_completed_manually(self):
        step = Step.objects.create(lesson=self.lesson, title='Quiz', kind='quiz', quiz=self.quiz, position=2, is_published=True)
        self.assertEqual(self.send(f'/api/learning/steps/{step.id}/complete/').status_code, 400)
        start = self.send(f'/api/study/quizzes/{self.quiz.id}/start/').json()
        self.send(f'/api/study/attempts/{start["attempt"]["id"]}/', {'answers': {str(self.question.id): 0}})
        detail = self.client.get(self.url(f'/api/learning/steps/{step.id}/')).json()
        self.assertTrue(detail['step']['completed'])

    def test_step_cross_course_reference_rejected(self):
        other = Course.objects.create(title='Other')
        a = Assignment.objects.create(course=other, title='Other')
        self.client.force_login(self.owner)
        response = self.send(f'/api/learning/lessons/{self.lesson.id}/steps/', {'title': 'Bad', 'kind': 'assignment', 'assignment_id': a.id})
        self.assertEqual(response.status_code, 400)

    def test_reorder_is_atomic_and_validates_complete_list(self):
        second = Step.objects.create(lesson=self.lesson, title='Second', position=2, is_published=True)
        self.client.force_login(self.owner)
        url = f'/api/learning/courses/{self.course.id}/reorder/'
        self.assertEqual(self.send(url, {'kind': 'steps', 'parent_id': self.lesson.id, 'ids': [self.step.id]}).status_code, 400)
        self.assertEqual(self.send(url, {'kind': 'steps', 'parent_id': self.lesson.id, 'ids': [second.id, self.step.id]}).status_code, 200)
        self.step.refresh_from_db()
        self.assertEqual(self.step.position, 2)

    def test_last_step_and_archiving(self):
        self.send(f'/api/learning/steps/{self.step.id}/visit/')
        self.ea.refresh_from_db()
        self.assertEqual(self.ea.last_step_id, self.step.id)
        self.assertEqual(self.send(f'/api/courses/enrollments/{self.ea.id}/', {'status': 'archived'}, 'patch').status_code, 200)
        self.assertEqual(self.client.get(self.url(f'/api/learning/steps/{self.step.id}/')).status_code, 403)
        self.assertEqual(self.send(f'/api/courses/enrollments/{self.ea.id}/', {'status': 'active'}, 'patch').status_code, 200)

    def test_group_announcement_recipients_and_history(self):
        self.client.force_login(self.teacher_a)
        response = self.send(f'/api/communication/courses/{self.course.id}/announcements/', {'title': 'Group A news', 'body': 'Details'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(list(Notification.objects.values_list('recipient_id', flat=True)), [self.a.id])
        self.client.force_login(self.b)
        values = self.client.get(self.url(f'/api/communication/courses/{self.course.id}/announcements/', self.rb)).json()
        self.assertEqual(values['announcements'], [])
        self.assertEqual(self.client.get('/api/communication/notifications/').json()['unread'], 0)

    def test_teacher_cannot_broadcast_to_other_groups(self):
        self.client.force_login(self.teacher_a)
        self.assertEqual(self.send(f'/api/communication/courses/{self.course.id}/announcements/', {'title': 'All', 'body': 'All', 'all_course': True}).status_code, 403)

    def test_global_announcement_deduplicates_multi_enrolled_student(self):
        Enrollment.objects.create(course=self.course, run=self.rb, student=self.a)
        self.client.force_login(self.owner)
        self.send(f'/api/communication/courses/{self.course.id}/announcements/', {'title': 'All', 'body': 'News', 'all_course': True})
        self.assertEqual(Notification.objects.filter(recipient=self.a).count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.b).count(), 1)

    def test_publishing_existing_draft_delivers_once(self):
        self.client.force_login(self.owner)
        response = self.send(f'/api/communication/courses/{self.course.id}/announcements/', {'title': 'Draft', 'body': 'News', 'is_published': False})
        self.assertEqual(Notification.objects.count(), 0)
        for _ in range(2):
            self.send(f'/api/communication/announcements/{response.json()["id"]}/', {'is_published': True}, 'patch')
        self.assertEqual(Notification.objects.filter(recipient=self.a).count(), 1)

    def test_notification_event_idempotency(self):
        for _ in range(2):
            notify('same', 'announcement', self.course, {self.a.id}, 'News', '/', self.ra)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Notification.objects.count(), 1)

    def test_preferences_and_read_ownership(self):
        self.send(f'/api/communication/courses/{self.course.id}/preferences/', {'muted_kinds': ['announcement']}, 'put')
        notify('muted', 'announcement', self.course, {self.a.id, self.b.id}, 'News', '/', None)
        self.assertFalse(Notification.objects.filter(recipient=self.a).exists())
        row = Notification.objects.get(recipient=self.b)
        self.send('/api/communication/notifications/', {'id': row.id}, 'patch')
        row.refresh_from_db()
        self.assertIsNone(row.read_at)

    def test_lost_enrollment_hides_notifications(self):
        notify('news', 'announcement', self.course, {self.a.id}, 'Private event', '/', self.ra)
        self.ea.status = 'archived'
        self.ea.save()
        self.assertEqual(self.client.get('/api/communication/notifications/').json()['notifications'], [])

    def test_private_dialog_and_unread_tracking(self):
        response = self.send(f'/api/communication/courses/{self.course.id}/conversations/')
        cid = response.json()['id']
        url = f'/api/communication/conversations/{cid}/messages/'
        self.assertEqual(self.send(url, {'body': 'Question'}).status_code, 201)
        self.client.force_login(self.teacher_a)
        self.assertEqual(self.client.get(url).json()['messages'][0]['body'], 'Question')
        self.assertEqual(self.send(url, {}, 'patch').status_code, 200)
        self.send(url, {'body': 'Answer'})
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.teacher_b)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_new_teacher_is_not_implicitly_added_to_old_dialog(self):
        cid = self.send(f'/api/communication/courses/{self.course.id}/conversations/').json()['id']
        self.ra.teachers.add(self.teacher_b)
        self.client.force_login(self.teacher_b)
        url = f'/api/communication/conversations/{cid}/messages/'
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.send(f'/api/communication/conversations/{cid}/participants/', {'username': 'teacher_b'}).status_code, 200)
        self.client.force_login(self.teacher_b)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_discussion_group_scope_and_parent_validation(self):
        url = f'/api/communication/lessons/{self.lesson.id}/discussion/'
        cid = self.send(url, {'body': 'Group A question'}).json()['id']
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(self.url(url, self.rb)).json()['comments'], [])
        self.assertEqual(self.send(url, {'body': 'Cross-group reply', 'parent_id': cid}, run=self.rb).status_code, 404)

    def test_comment_moderation_and_closing(self):
        url = f'/api/communication/lessons/{self.lesson.id}/discussion/'
        cid = self.send(url, {'body': 'Question'}).json()['id']
        self.assertEqual(self.send(f'/api/communication/comments/{cid}/', {'is_pinned': True}, 'patch').status_code, 403)
        self.client.force_login(self.teacher_a)
        self.assertEqual(self.send(f'/api/communication/comments/{cid}/', {'is_hidden': True}, 'patch').status_code, 200)
        self.send(url, {'is_closed': True}, 'patch')
        self.client.force_login(self.a)
        response = self.client.get(self.url(url)).json()
        self.assertNotEqual(response['comments'][0]['body'], 'Question')
        self.assertEqual(self.send(url, {'body': 'Late reply'}).status_code, 400)

    def test_returned_work_grants_revision_and_keeps_review_history(self):
        self.assignment.max_attempts = 1
        self.assignment.save()
        response = self.client.post(self.url(f'/api/study/assignments/{self.assignment.id}/submit/'), {'text_answer': 'First'})
        sid = response.json()['submission']['id']
        self.client.force_login(self.teacher_a)
        self.send(f'/api/study/submissions/{sid}/grade/', {'return_for_revision': True, 'feedback': 'Revise'}, 'put')
        self.client.force_login(self.a)
        self.assertEqual(self.client.post(self.url(f'/api/study/assignments/{self.assignment.id}/submit/'), {'text_answer': 'Revised'}).status_code, 201)
        self.assertEqual(Submission.objects.get(pk=sid).reviews.count(), 1)

    def test_deadline_reminders_are_idempotent(self):
        from .management.commands.notification_worker import remind_deadlines
        self.assignment.due_at = timezone.now()+timedelta(hours=1)
        self.assignment.save()
        remind_deadlines(); remind_deadlines()
        self.assertEqual(Notification.objects.filter(recipient=self.a, event__kind='deadline').count(), 1)

    def test_guest_and_csrf_protection(self):
        self.client.logout()
        self.assertEqual(self.client.get('/api/communication/notifications/').status_code, 401)
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.a)
        self.assertEqual(client.post(self.url(f'/api/communication/courses/{self.course.id}/conversations/'), data='{}', content_type='application/json').status_code, 403)

    def test_announcements_available_before_classes_start_but_steps_locked(self):
        self.ra.starts_at = timezone.now()+timedelta(days=1)
        self.ra.save()
        self.assertEqual(self.client.get(self.url(f'/api/communication/courses/{self.course.id}/announcements/')).status_code, 200)
        self.assertEqual(self.client.get(self.url(f'/api/learning/steps/{self.step.id}/')).status_code, 403)

    def test_published_step_notification_is_once_and_draft_does_not_send(self):
        self.client.force_login(self.owner)
        response = self.send(f'/api/learning/lessons/{self.lesson.id}/steps/', {'title': 'New', 'kind': 'text'})
        self.assertEqual(Notification.objects.count(), 0)
        for _ in range(2):
            self.send(f'/api/learning/steps/{response.json()["id"]}/', {'is_published': True}, 'patch')
        self.assertEqual(Notification.objects.filter(recipient=self.a).count(), 1)

    def test_teacher_queue_excludes_other_group(self):
        Submission.objects.create(assignment=self.assignment, enrollment=self.ea, student=self.a, attempt_no=1)
        Submission.objects.create(assignment=self.assignment, enrollment=self.eb, student=self.b, attempt_no=1)
        self.client.force_login(self.teacher_a)
        data = self.client.get('/api/study/review-queue/').json()
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['works'][0]['student'], 'a')

    def test_revoked_student_cannot_restore_access_via_archive_or_invite(self):
        self.client.force_login(self.teacher_a)
        self.assertEqual(self.send(f'/api/courses/enrollments/{self.ea.id}/', {'status': 'removed'}, 'patch').status_code, 200)
        self.client.force_login(self.a)
        self.assertEqual(self.send(f'/api/courses/enrollments/{self.ea.id}/', {'status': 'active'}, 'patch').status_code, 403)
        self.assertEqual(self.send('/api/courses/join/', {'code': 'invite-a'}).status_code, 403)
        self.client.get('/api/courses/my-learning/')
        self.ea.refresh_from_db()
        self.assertEqual(self.ea.status, 'removed')
        self.assertEqual(self.client.get(self.url(f'/api/learning/steps/{self.step.id}/')).status_code, 403)
        self.client.force_login(self.teacher_a)
        self.assertEqual(self.send(f'/api/courses/enrollments/{self.ea.id}/', {'status': 'active'}, 'patch').status_code, 200)


    def test_discussion_groups_interleaved_and_nested_replies_under_original_question(self):
        url = f'/api/communication/lessons/{self.lesson.id}/discussion/'
        first = self.send(url, {'body': 'First question'}).json()['id']
        second = self.send(url, {'body': 'Separate question'}).json()['id']
        self.client.force_login(self.teacher_a)
        reply = self.send(url, {'body': 'Teacher answer', 'parent_id': first}).json()['id']
        self.client.force_login(self.a)
        follow_up = self.send(url, {'body': 'Follow-up', 'parent_id': reply}).json()['id']
        self.client.force_login(self.teacher_a)
        final = self.send(url, {'body': 'Clarification', 'parent_id': follow_up}).json()['id']
        other_reply = self.send(url, {'body': 'Answer to second question', 'parent_id': second}).json()['id']
        data = self.client.get(self.url(url)).json()
        threads = {t['root']['id']: t for t in data['threads']}
        self.assertEqual(data['total_threads'], 2)
        self.assertEqual([r['id'] for r in threads[first]['replies']], [reply, follow_up, final])
        self.assertEqual([r['id'] for r in threads[second]['replies']], [other_reply])
        self.assertEqual(threads[first]['replies'][1]['parent_id'], reply)
        self.assertTrue(threads[first]['replies'][0]['is_teacher'])
        self.assertFalse(threads[first]['root']['is_teacher'])
        self.assertTrue(Notification.objects.filter(recipient=self.a, event__key=f'comment:{reply}').exists())

    def test_discussion_hidden_parent_keeps_visible_replies_in_same_thread(self):
        url = f'/api/communication/lessons/{self.lesson.id}/discussion/'
        root = self.send(url, {'body': 'Hidden original question'}).json()['id']
        self.client.force_login(self.teacher_a)
        reply = self.send(url, {'body': 'Visible teacher reply', 'parent_id': root}).json()['id']
        self.send(f'/api/communication/comments/{root}/', {'is_hidden': True}, 'patch')
        self.client.force_login(self.a)
        thread = self.client.get(self.url(url)).json()['threads'][0]
        self.assertTrue(thread['root']['is_hidden'])
        self.assertNotIn('Hidden original question', thread['root']['body'])
        self.assertEqual(thread['replies'][0]['id'], reply)
        self.assertEqual(thread['replies'][0]['body'], 'Visible teacher reply')

    def test_discussion_paginates_questions_without_cutting_long_reply_threads(self):
        from .models import Discussion
        thread = Discussion.objects.create(lesson=self.lesson, run=self.ra)
        roots = Comment.objects.bulk_create([Comment(discussion=thread, author=self.a, body=f'Question {i}') for i in range(21)])
        Comment.objects.bulk_create([Comment(discussion=thread, author=self.teacher_a, parent=roots[-1], body=f'Reply {i}') for i in range(505)])
        url = self.url(f'/api/communication/lessons/{self.lesson.id}/discussion/')
        first = self.client.get(url).json()
        self.assertEqual(first['total_threads'], 21)
        self.assertEqual(len(first['threads']), 20)
        self.assertEqual(first['next_page'], 2)
        self.assertEqual(first['threads'][0]['root']['id'], roots[-1].id)
        self.assertEqual(len(first['threads'][0]['replies']), 505)
        second = self.client.get(url + '&page=2').json()
        self.assertEqual([t['root']['id'] for t in second['threads']], [roots[0].id])
        self.assertIsNone(second['next_page'])
        ids_first = {c['id'] for c in first['comments']}
        self.assertFalse(ids_first & {c['id'] for c in second['comments']})
        self.assertEqual(self.client.get(url + '&page=-1').status_code, 400)
        self.assertEqual(self.client.get(url + '&page=invalid').status_code, 400)

    def test_pinning_reply_does_not_detach_it_from_original_question(self):
        url = f'/api/communication/lessons/{self.lesson.id}/discussion/'
        root = self.send(url, {'body': 'First question'}).json()['id']
        other = self.send(url, {'body': 'Other question'}).json()['id']
        self.client.force_login(self.teacher_a)
        reply = self.send(url, {'body': 'Pinned answer', 'parent_id': root}).json()['id']
        self.send(f'/api/communication/comments/{reply}/', {'is_pinned': True}, 'patch')
        threads = self.client.get(self.url(url)).json()['threads']
        self.assertEqual([t['root']['id'] for t in threads], [other, root])
        self.assertEqual(threads[1]['replies'][0]['id'], reply)
        self.assertTrue(threads[1]['replies'][0]['is_pinned'])
        self.send(f'/api/communication/comments/{root}/', {'is_pinned': True}, 'patch')
        self.assertEqual(self.client.get(self.url(url)).json()['threads'][0]['root']['id'], root)
