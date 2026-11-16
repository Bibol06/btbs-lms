from django.apps import AppConfig


class CoursesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'courses'

    def ready(self):
        from django.db.models.signals import post_delete
        from file_cleanup import remove_unreferenced_file
        post_delete.connect(remove_unreferenced_file, sender=self.get_model('CourseImage'), dispatch_uid='cleanup_course_image')
