"""The same LMS API; HTML is served from frontend/dist by WhiteNoise."""
from django.urls import include, path

urlpatterns = [path('', include('config.urls'))]
