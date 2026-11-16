from django.apps import AppConfig


class AssessmentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'assessment'

    def ready(self):
        from django.db.models.signals import post_delete
        from file_cleanup import remove_deleted_file
        post_delete.connect(remove_deleted_file, sender=self.get_model('Submission'), dispatch_uid='cleanup_submission_file')
