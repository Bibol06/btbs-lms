from django.urls import path
from . import views

urlpatterns = [
    path('notifications/', views.notifications),
    path('courses/<int:course_id>/announcements/', views.announcements),
    path('announcements/<int:announcement_id>/', views.announcement_detail),
    path('courses/<int:course_id>/conversations/', views.conversations),
    path('conversations/<int:conversation_id>/messages/', views.messages),
    path('conversations/<int:conversation_id>/participants/', views.add_participant),
    path('lessons/<int:lesson_id>/discussion/', views.discussion),
    path('comments/<int:comment_id>/', views.comment_detail),
    path('courses/<int:course_id>/preferences/', views.preferences),
    path('courses/<int:course_id>/audit/', views.audit_log),
]
