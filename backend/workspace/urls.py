from django.urls import path
from . import views, author_views

urlpatterns = [
    path('home/', views.home),
    path('search/', views.search),
    path('questions/', views.questions),
    path('question-insights/', views.question_insights),
    path('policies/<int:run_id>/', views.policy),
    path('lessons/<int:lesson_id>/pulse/', views.pulse),
    path('assignments/<int:assignment_id>/rubric/', views.rubric),
    path('reviews/<int:submission_id>/', views.review),
    path('bank/', author_views.bank),
    path('courses/<int:course_id>/clone/', author_views.clone_course),
    path('courses/<int:course_id>/preview/', author_views.preview),
]
