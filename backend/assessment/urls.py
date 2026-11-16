from django.urls import path
from . import views
from . import student_views
from . import deadline_views
from . import management_views

urlpatterns = [
    path('management/overview/', management_views.overview),
    path('management/students/', management_views.students),
    path('management/teachers/', management_views.teachers),
    path('management/courses/', management_views.courses),
    path('management/activity/', management_views.activity),
    path('management/enrollments/<int:enrollment_id>/tasks/', management_views.enrollment_tasks),
    path('courses/<int:course_id>/students/<int:student_id>/', student_views.student_report),
    path('agenda/', deadline_views.agenda),
    path('review-queue/', deadline_views.review_queue),
    path('assignments/<int:assignment_id>/extensions/', deadline_views.extensions),
    path('submissions/<int:submission_id>/reviewer/', deadline_views.assign_reviewer),
    path('courses/<int:course_id>/schedule/', views.schedule),
    path('courses/<int:course_id>/report.csv', views.export_report),
    path('courses/<int:course_id>/', views.course_study),
    path('courses/<int:course_id>/report/', views.course_report),
    path('courses/<int:course_id>/assignments/', views.create_assignment),
    path('assignments/<int:assignment_id>/', views.manage_assignment),
    path('assignments/<int:assignment_id>/submit/', views.submit_assignment),
    path('submissions/<int:submission_id>/grade/', views.grade_submission),
    path('submissions/<int:submission_id>/file/', views.submission_file),
    path('courses/<int:course_id>/quizzes/', views.create_quiz),
    path('quizzes/<int:quiz_id>/', views.manage_quiz),
    path('quizzes/<int:quiz_id>/start/', views.start_quiz),
    path('attempts/<int:attempt_id>/', views.answer_quiz),
    path('lessons/<int:lesson_id>/complete/', views.complete_lesson),
]
