
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('api/media/', include('learning.media_urls')),
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/courses/', include('courses.urls')),
    path('api/learning/', include('learning.urls')),
    path('api/study/', include('assessment.urls')),
    path('api/communication/', include('communication.urls')),
    path('api/code/', include('codejudge.urls')),
    path('api/analytics/', include('analytics.urls')),
    path('api/workspace/', include('workspace.urls')),
]
