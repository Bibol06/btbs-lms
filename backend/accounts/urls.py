
from django.urls import path
from . import views
from . import profile_views
from . import admin_views
from . import system_views
from . import recovery

urlpatterns = [
    path('password-reset/', recovery.request_reset),
    path('password-reset/status/', recovery.reset_delivery_status),
    path('password-reset/validate/', recovery.validate_reset),
    path('password-reset/confirm/', recovery.confirm_reset),
    path('system/status/', system_views.status),
    path('system/backups/', system_views.request_backup),
    path('system/storage-check/', system_views.check_storage),
    path('users/<int:user_id>/responsibility/', admin_views.change_responsibility),
    path('preferences/', profile_views.preferences),
    path('profile/', profile_views.my_profile),
    path('profiles/<int:user_id>/', profile_views.user_profile),
    path('csrf/', views.csrf_view),
    path('login/', views.login_view),
    path('register/', views.register_view),
    path('me/', views.me_view),
    path('logout/', views.logout_view),
    path('users/', views.users_view),
    path('students/create/', views.create_student_view),
    path('users/<int:user_id>/', views.delete_student_view),
]
