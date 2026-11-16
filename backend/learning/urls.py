
from django.urls import path
from . import views

from . import upload_views
from . import step_views
from . import image_views

urlpatterns = [
    path('teacher/lessons/<int:lesson_id>/images/', image_views.upload_lesson_image),
    path('images/<int:image_id>/', image_views.open_lesson_image),
    path('courses/<int:course_id>/structure/', step_views.structure),
    path('courses/<int:course_id>/reorder/', step_views.reorder),
    path('modules/<int:module_id>/', step_views.module_detail),
    path('lessons/<int:lesson_id>/steps/', step_views.create_step),
    path('steps/<int:step_id>/', step_views.step_detail),
    path('steps/<int:step_id>/visit/', step_views.step_visit),
    path('steps/<int:step_id>/complete/', step_views.complete_step),
    path('teacher/lessons/<int:lesson_id>/', views.manage_lesson),
    path('teacher/materials/<int:material_id>/', views.delete_material),
    path(
        'courses/<int:course_id>/lessons/',
        views.course_lessons
    ),

    path(
        'materials/<int:material_id>/open/',
        views.open_material
    ),
   
    path(
    "teacher/courses/<int:course_id>/lessons/",
    views.teacher_create_lesson
),

path(
    "teacher/lessons/<int:lesson_id>/materials/",
    upload_views.upload_lesson_material
),
]
