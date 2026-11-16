from django.apps import AppConfig


class LearningConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'learning'

    def ready(self):
        from django.db.models.signals import post_delete, post_save
        from courses.catalog_cache import invalidate_lesson_counts
        post_save.connect(invalidate_lesson_counts, sender=self.get_model('Lesson'), dispatch_uid='lesson_counts_save')
        post_delete.connect(invalidate_lesson_counts, sender=self.get_model('Lesson'), dispatch_uid='lesson_counts_delete')
        from file_cleanup import remove_deleted_file
        post_delete.connect(remove_deleted_file, sender=self.get_model('LessonMaterial'), dispatch_uid='cleanup_lesson_material')
