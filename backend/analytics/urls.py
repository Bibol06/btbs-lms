from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard),
    path('attendance/', views.attendance_report),
    path('sessions/', views.sessions_report),
    path('activity/', views.activity_report),
    path('presence/', views.presence),
    path('evaluations/', views.evaluations),
    path('export/', views.export_report),
]
