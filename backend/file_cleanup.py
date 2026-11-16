from django.db import transaction


def remove_deleted_file(sender, instance, **kwargs):
    remove_unreferenced_file(sender, instance, **kwargs)


def file_is_referenced(name, using='default'):
    from django.apps import apps
    return any(apps.get_model(label).objects.using(using).filter(file=name).exists()
               for label in ['learning.LessonMaterial', 'courses.CourseImage', 'assessment.Submission'])


def delete_unreferenced(storage, name, using='default'):
    from learning.models import StorageDeletion
    if file_is_referenced(name, using):
        StorageDeletion.objects.using(using).filter(name=name).delete()
        return
    try:
        storage.delete(name)
        StorageDeletion.objects.using(using).filter(name=name).delete()
    except Exception as error:
        row, _ = StorageDeletion.objects.using(using).get_or_create(name=name)
        row.attempts += 1; row.last_error = type(error).__name__
        row.save(update_fields=['attempts', 'last_error'])


def remove_unreferenced_file(sender, instance, using, **kwargs):
    """Course copies may share an immutable image; delete only the last reference."""
    if instance.file:
        storage, name = instance.file.storage, instance.file.name

        def cleanup():
            delete_unreferenced(storage, name, using)

        transaction.on_commit(cleanup, using=using)
