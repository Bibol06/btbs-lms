from django.urls import path
from . import media_views

urlpatterns = [path('config/', media_views.upload_config),
    path('uploads/<uuid:upload_id>/parts/', media_views.parts),
    path('lessons/<int:lesson_id>/uploads/', media_views.initiate),
    path('uploads/<uuid:upload_id>/complete/', media_views.complete),
    path('uploads/<uuid:upload_id>/abort/', media_views.abort)]
