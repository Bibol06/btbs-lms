from django.urls import path
from . import views

urlpatterns = [
    path('courses/<int:course_id>/problems/', views.problems),
    path('problems/<int:problem_id>/', views.problem_detail),
    path('problems/<int:problem_id>/execute/', views.execute),
    path('submissions/<int:submission_id>/', views.submission_status),
    path('runs/<str:token>/', views.practice_status),
]
