from django.urls import path
from . import views
from . import run_views
from . import learning_views
from . import publication_views
from . import image_views
from . import pacing_views

urlpatterns = [
    path('runs/<int:run_id>/learning-plan/', pacing_views.learning_plan),
    path('images/<int:image_id>/', image_views.open_course_image),
    path('teacher/<int:course_id>/images/', image_views.upload_course_image),
    path('<int:course_id>/readiness/', publication_views.readiness),
    path('<int:course_id>/publish/', publication_views.publish),
    path('<int:course_id>/modules/<int:module_id>/open-now/', publication_views.open_module_now),
    path('my-learning/', learning_views.my_learning),
    path('join/', run_views.join_group),
    path('runs/<int:run_id>/', run_views.run_detail),
    path('runs/<int:run_id>/students/', run_views.run_students),
    path('enrollments/<int:enrollment_id>/', run_views.enrollment_status),
    path('<int:course_id>/runs/', run_views.runs),
    path('<int:course_id>/team/', run_views.team),
    path('<int:course_id>/bookmark/', run_views.bookmark),
    path("", views.courses_list),
    path("<int:course_id>/enroll/", views.enroll_course),
    path("teacher/", views.teacher_courses),
    path("teacher/<int:course_id>/", views.edit_teacher_course),
]
