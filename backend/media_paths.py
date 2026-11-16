"""Stable, server-owned media namespaces. Titles and module positions may change."""
from pathlib import PurePosixPath
from uuid import uuid4

REMOTE_PREFIX = '_s3/'


def course_prefix(course_id):
    return f'courses/course-{int(course_id)}/'


def media_directory(instance, filename):
    label = instance._meta.label_lower
    if label == 'learning.lessonmaterial':
        lesson = instance.lesson
        category = 'images' if instance.is_inline else (
            'videos' if PurePosixPath(filename).suffix.lower() in {'.mp4', '.webm'} else 'materials')
        return f'{course_prefix(lesson.course_id)}lessons/lesson-{lesson.pk}/{category}/'
    if label == 'courses.courseimage':
        return f'{course_prefix(instance.course_id)}images/'
    if label == 'assessment.submission':
        enrollment = instance.enrollment
        return (f'{course_prefix(instance.assignment.course_id)}groups/run-{enrollment.run_id}/'
                f'assignments/assignment-{instance.assignment_id}/answers/'
                f'enrollment-{enrollment.pk}/attempt-{instance.attempt_no}/')
    raise ValueError('Unsupported media model')


def course_media_upload_to(instance, filename):
    # No original paths, names of people, or client-supplied course IDs in keys.
    normalized = str(filename).replace('\\', '/')
    return f'{media_directory(instance, normalized)}{uuid4().hex}{PurePosixPath(normalized).suffix.lower()}'


def remote_media_key(instance, filename):
    return REMOTE_PREFIX + course_media_upload_to(instance, filename)
