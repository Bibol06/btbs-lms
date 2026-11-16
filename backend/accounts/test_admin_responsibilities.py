import json
from django.contrib.auth import get_user_model
from django.test import TestCase
from courses.models import Course, CourseRun
from .models import SystemAuditEvent


class AdminResponsibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User=get_user_model()
        cls.full=User.objects.create_user(username='scope_full',role='admin')
        cls.system=User.objects.create_user(username='scope_system',role='admin',admin_scope='system')
        cls.learning=User.objects.create_user(username='scope_learning',role='admin',admin_scope='learning')
        cls.teacher=User.objects.create_user(username='scope_teacher',role='teacher')
        cls.student=User.objects.create_user(username='scope_student')
        cls.course=Course.objects.create(teacher=cls.teacher,title='Draft')
        cls.cohort=CourseRun.objects.create(course=cls.course,title='A',kind='cohort')

    def get(self,user,path):
        self.client.force_login(user);return self.client.get(path)

    def test_system_and_learning_endpoints_are_separate(self):
        for user,system,learning in [(self.full,200,200),(self.system,200,403),(self.learning,403,200),(self.student,403,403)]:
            self.assertEqual(self.get(user,'/api/auth/system/status/').status_code,system)
            self.assertEqual(self.get(user,f'/api/courses/{self.course.id}/readiness/').status_code,learning)

    def test_only_system_scope_can_see_devices_and_accounts(self):
        for user,expected in [(self.system,200),(self.full,200),(self.learning,403),(self.teacher,403)]:
            self.assertEqual(self.get(user,'/api/analytics/sessions/?period=week').status_code,expected)
            self.assertEqual(self.get(user,'/api/auth/users/').status_code,expected)

    def test_system_storage_groups_media_by_course_without_s3_requests(self):
        from learning.models import Lesson, LessonMaterial
        from courses.models import CourseImage
        lesson = Lesson.objects.create(course=self.course, title='Lesson')
        LessonMaterial.objects.create(lesson=lesson, title='Video', file='_s3/legacy/video.mp4')
        LessonMaterial.objects.create(lesson=lesson, title='Document', file='local.pdf')
        CourseImage.objects.create(course=self.course, title='Image', file='_s3/legacy/picture.png')
        data = self.get(self.system, '/api/auth/system/status/').json()['storage']
        row = next(c for c in data['courses'] if c['id'] == self.course.id)
        self.assertEqual((row['materials'], row['images'], row['s3_files'], row['local_files']), (2, 1, 2, 1))
        self.assertEqual(row['prefix'], f'_s3/courses/course-{self.course.id}/')
        self.assertNotIn('MEDIA_S3_SECRET_KEY', str(data))

    def test_learning_admin_can_manage_all_courses_without_becoming_system_admin(self):
        self.client.force_login(self.learning)
        response=self.client.patch(f'/api/courses/teacher/{self.course.id}/',json.dumps({'title':'Updated'}),content_type='application/json')
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get('/api/analytics/dashboard/?role=admin').status_code,200)
        self.assertEqual(self.client.get('/api/auth/system/status/').status_code,403)

    def test_only_full_admin_can_assign_responsibility_and_cannot_demote_owner(self):
        path=f'/api/auth/users/{self.student.id}/responsibility/'
        for user in [self.system,self.learning,self.teacher,self.student]:
            self.client.force_login(user)
            self.assertEqual(self.client.post(path,json.dumps({'responsibility':'system'}),content_type='application/json').status_code,403)
        self.client.force_login(self.full)
        self.assertEqual(self.client.post(path,json.dumps({'responsibility':'learning'}),content_type='application/json').status_code,200)
        self.student.refresh_from_db();self.assertEqual(self.student.admin_scope,'learning')
        self.assertEqual(SystemAuditEvent.objects.count(),1)
        self.assertEqual(self.client.post(f'/api/auth/users/{self.full.id}/responsibility/',json.dumps({'responsibility':'system'}),content_type='application/json').status_code,400)

    def test_public_registration_cannot_select_admin_scope(self):
        self.client.logout()
        response=self.client.post('/api/auth/register/',json.dumps({'username':'scope_intruder','email':'test@example.com','password':'CorrectHorse_Battery_2026!','role':'admin','admin_scope':'system'}),content_type='application/json')
        self.assertEqual(response.status_code,201)
        user=get_user_model().objects.get(username='scope_intruder');self.assertEqual(user.role,'student')
        self.assertEqual(self.client.get('/api/auth/system/status/').status_code,403)

    def test_me_returns_scope_capabilities_and_clear_role_label(self):
        for user,label in [(self.system,'Системный администратор'),(self.learning,'Администратор обучения')]:
            response=self.get(user,'/api/auth/me/').json()
            self.assertEqual(response['role_label'],label)
            self.assertEqual(response['capabilities']['system_admin'],user==self.system)
            self.assertEqual(response['capabilities']['learning_admin'],user==self.learning)
