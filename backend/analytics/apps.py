from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    name = 'analytics'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        from . import signals  # noqa: F401
