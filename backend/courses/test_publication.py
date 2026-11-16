from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from assessment.models import Quiz, Question, Assignment, ActivitySchedule
from communication.models import AuditEvent, Event
from learning.models import Module, Lesson, Step
from .models import Course, CourseRun, Enrollment


class PublicationReadinessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.teacher = User.objects.create_user(username='publication_owner', role='teacher')
        cls.tutor = User.objects.create_user(username='publication_tutor', role='teacher')
        cls.student = User.objects.create_user(username='publication_student')
        cls.other = User.objects.create_user(username='publication_other', role='teacher')
        cls.admin = User.objects.create_user(username='publication_admin', role='admin')
        cls.course = Course.objects.create(teacher=cls.teacher, title='Publication course')
        cls.cohort = CourseRun.objects.create(course=cls.course, title='Publication group', kind='cohort')
        cls.cohort.teachers.add(cls.tutor)
        cls.enrollment = Enrollment.objects.create(course=cls.course, run=cls.cohort, student=cls.student)
        cls.module = Module.objects.create(course=cls.course, title='Module', opens_at=timezone.now()+timedelta(days=1))
        cls.lesson = Lesson.objects.create(course=cls.course, module=cls.module, title='Lesson')
        cls.theory = Step.objects.create(lesson=cls.lesson, title='Read', content='Actual lesson text')
        cls.quiz = Quiz.objects.create(course=cls.course, title='Quiz')
        cls.question = Question.objects.create(quiz=cls.quiz, body='2+2?', options=['3', '4'], correct_index=1, position=1)
        cls.quiz_step = Step.objects.create(lesson=cls.lesson, title='Answer', position=2, kind='quiz', quiz=cls.quiz)
        cls.assignment = Assignment.objects.create(course=cls.course, title='Homework')
        cls.assignment_step = Step.objects.create(lesson=cls.lesson, title='Practice', position=3, kind='assignment', assignment=cls.assignment)

    def url(self, action):
        return f'/api/courses/{self.course.id}/{action}/?run_id={self.cohort.id}'

    def post(self, action, data=None):
        return self.client.post(self.url(action), data or {}, content_type='application/json')

    def test_readiness_reports_drafts_release_date_and_linked_activity_flags(self):
        self.client.force_login(self.teacher)
        response = self.client.get(self.url('readiness'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['summary']['unpublished_modules'], 1)
        self.assertEqual(data['summary']['unpublished_lessons'], 1)
        self.assertEqual(data['summary']['unpublished_steps'], 3)
        self.assertEqual(data['summary']['unpublished_quizzes'], 1)
        self.assertEqual(data['summary']['unpublished_assignments'], 1)
        scheduled = next(issue for issue in data['issues'] if issue['reason'] == 'module_scheduled')
        self.assertEqual(scheduled['id'], self.module.id)
        self.assertEqual(scheduled['scope'], 'module')
        self.assertIsNotNone(scheduled['date'])
        self.assertFalse(data['summary']['ready_now'])

    def test_only_course_editors_and_admin_can_read_or_change_publication(self):
        for actor in [self.student, self.other, self.tutor]:
            self.client.force_login(actor)
            self.assertEqual(self.client.get(self.url('readiness')).status_code, 403)
            self.assertEqual(self.post('publish', {'scope': 'course'}).status_code, 403)
            self.assertEqual(self.post(f'modules/{self.module.id}/open-now').status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url('readiness')).status_code, 401)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url('readiness')).status_code, 200)

    def test_tree_publication_preserves_schedule_and_keeps_students_locked_until_release(self):
        self.client.force_login(self.teacher)
        response = self.post('publish', {'scope': 'course'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['published'], {'course': 1, 'modules': 1, 'lessons': 1, 'steps': 3, 'quizzes': 1, 'assignments': 1})
        self.module.refresh_from_db()
        self.assertGreater(self.module.opens_at, timezone.now())
        self.course.refresh_from_db()
        self.assertTrue(self.course.is_published)
        self.quiz.refresh_from_db()
        self.assignment.refresh_from_db()
        self.assertTrue(self.quiz.is_published and self.assignment.is_published)
        self.question.refresh_from_db()
        self.assertEqual(self.question.correct_index, 1)
        self.assertEqual(self.question.options, ['3', '4'])
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(f'/api/learning/steps/{self.theory.id}/?run_id={self.cohort.id}').status_code, 403)

    def test_open_now_only_changes_selected_module_date_and_records_audit(self):
        self.client.force_login(self.teacher)
        self.post('publish', {'scope': 'course'})
        response = self.post(f'modules/{self.module.id}/open-now')
        self.assertEqual(response.status_code, 200, response.content)
        self.module.refresh_from_db()
        self.assertIsNone(self.module.opens_at)
        self.assertTrue(response.json()['readiness']['summary']['ready_now'])
        self.assertEqual(AuditEvent.objects.filter(action='module.opened_now', course=self.course).count(), 1)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(f'/api/learning/steps/{self.theory.id}/?run_id={self.cohort.id}').status_code, 200)

    def test_open_now_preserves_prerequisite_and_other_modules(self):
        prerequisite = Module.objects.create(course=self.course, title='Required first', position=2)
        self.module.prerequisite = prerequisite
        self.module.save(update_fields=['prerequisite'])
        other_date = timezone.now()+timedelta(days=2)
        other_module = Module.objects.create(course=self.course, title='Later', position=3, opens_at=other_date)
        self.client.force_login(self.teacher)
        response = self.post(f'modules/{self.module.id}/open-now')
        self.assertEqual(response.status_code, 200)
        self.module.refresh_from_db()
        other_module.refresh_from_db()
        self.assertEqual(self.module.prerequisite_id, prerequisite.id)
        self.assertFalse(self.module.is_published)
        self.assertEqual(other_module.opens_at, other_date)

    def test_invalid_materials_block_publication_without_partial_changes(self):
        self.theory.content = ''
        self.theory.save(update_fields=['content'])
        self.client.force_login(self.teacher)
        response = self.post('publish', {'scope': 'course'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['issues'][0]['id'], self.theory.id)
        self.course.refresh_from_db()
        self.module.refresh_from_db()
        self.quiz.refresh_from_db()
        self.assertFalse(self.course.is_published or self.module.is_published or self.quiz.is_published)
        self.assertFalse(Event.objects.exists())

    def test_empty_quiz_is_diagnosed_and_cannot_be_published(self):
        self.quiz.questions.all().delete()
        self.client.force_login(self.teacher)
        data = self.client.get(self.url('readiness')).json()
        self.assertTrue(any(issue['reason'] == 'quiz_empty' for issue in data['issues']))
        self.assertEqual(self.post('publish', {'scope': 'course'}).status_code, 400)

    def test_selected_lesson_publication_opens_parents_without_publishing_siblings(self):
        sibling = Lesson.objects.create(course=self.course, module=self.module, title='Still a draft', position=2)
        sibling_step = Step.objects.create(lesson=sibling, title='Not ready', content='')
        self.client.force_login(self.teacher)
        response = self.post('publish', {'scope': 'lesson', 'target_id': self.lesson.id})
        self.assertEqual(response.status_code, 200, response.content)
        self.module.refresh_from_db()
        self.lesson.refresh_from_db()
        sibling.refresh_from_db()
        sibling_step.refresh_from_db()
        self.assertTrue(self.module.is_published and self.lesson.is_published)
        self.assertFalse(sibling.is_published or sibling_step.is_published)

    def test_publish_without_descendants_does_not_change_children(self):
        self.client.force_login(self.teacher)
        response = self.post('publish', {'scope': 'course', 'include_descendants': False})
        self.assertEqual(response.status_code, 200)
        self.course.refresh_from_db()
        self.module.refresh_from_db()
        self.assertTrue(self.course.is_published)
        self.assertFalse(self.module.is_published)

    def test_other_course_targets_and_invalid_scope_do_not_mutate_course(self):
        other = Course.objects.create(teacher=self.teacher, title='Other')
        foreign_module = Module.objects.create(course=other, title='Foreign')
        self.client.force_login(self.teacher)
        self.assertEqual(self.post('publish', {'scope': 'module', 'target_id': foreign_module.id}).status_code, 404)
        self.assertEqual(self.post(f'modules/{foreign_module.id}/open-now').status_code, 404)
        self.assertEqual(self.post('publish', {'scope': 'step'}).status_code, 400)
        self.assertEqual(self.post('publish', {'scope': 'course', 'include_descendants': 'yes'}).status_code, 400)
        self.course.refresh_from_db()
        self.assertFalse(self.course.is_published)

    def test_published_empty_course_and_run_dates_are_visible_in_diagnostics(self):
        empty = Course.objects.create(teacher=self.teacher, title='Empty published', is_published=True)
        future = CourseRun.objects.create(course=empty, title='Future', kind='cohort', starts_at=timezone.now()+timedelta(days=1))
        self.client.force_login(self.teacher)
        response = self.client.get(f'/api/courses/{empty.id}/readiness/?run_id={future.id}')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(any(issue['reason'] == 'published_empty' for issue in data['issues']))
        self.assertTrue(any(issue['reason'] == 'run_scheduled' for issue in data['issues']))
        self.assertFalse(data['summary']['ready_now'])

    def test_group_quiz_schedule_is_diagnosed_without_rewriting_base_dates(self):
        self.module.opens_at = None
        self.module.save(update_fields=['opens_at'])
        start = timezone.now()+timedelta(days=2)
        ActivitySchedule.objects.create(run=self.cohort, quiz=self.quiz, opens_at=start)
        self.client.force_login(self.teacher)
        data = self.post('publish', {'scope': 'course'}).json()['readiness']
        issue = next(row for row in data['issues'] if row['reason'] == 'quiz_scheduled')
        self.assertEqual(issue['id'], self.quiz.id)
        self.assertIsNotNone(issue['date'])
        self.assertEqual(data['summary']['available_steps'], 2)
        self.quiz.refresh_from_db()
        self.assertIsNone(self.quiz.opens_at)

    def test_closed_assignment_and_quiz_are_explained_for_selected_run(self):
        self.module.opens_at = None
        self.module.save(update_fields=['opens_at'])
        self.quiz.closes_at = timezone.now()-timedelta(hours=1)
        self.quiz.save(update_fields=['closes_at'])
        self.assignment.due_at = timezone.now()-timedelta(hours=2)
        self.assignment.allow_late = False
        self.assignment.save(update_fields=['due_at', 'allow_late'])
        self.client.force_login(self.teacher)
        data = self.post('publish', {'scope': 'course'}).json()['readiness']
        reasons = {item['reason'] for item in data['issues']}
        self.assertIn('quiz_closed', reasons)
        self.assertIn('assignment_closed', reasons)
        self.assertEqual(data['summary']['available_steps'], 1)
