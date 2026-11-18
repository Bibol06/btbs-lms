from django.db import models
from media_paths import course_media_upload_to

class Lesson(models.Model):
    module = models.ForeignKey('Module', null=True, blank=True, on_delete=models.RESTRICT, related_name='lessons')

    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='lessons'
    )

    title = models.CharField(max_length=200)

    content = models.TextField(blank=True)

    video_url = models.URLField(blank=True)

    position = models.PositiveIntegerField(default=1)

    is_published = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['course', 'position'],
                name='unique_course_lesson_position'
            )
        ]

    def __str__(self):
        return self.title


class LessonMaterial(models.Model):

    # Inline illustrations are rendered only from visible lesson content, never
    # exposed as independently published file steps.
    is_inline = models.BooleanField(default=False)

    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name='materials'
    )

    title = models.CharField(max_length=200)

    file = models.FileField(
        upload_to=course_media_upload_to, max_length=500
    )

    def __str__(self):
        return self.title


class Module(models.Model):
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='modules')
    title = models.CharField(max_length=200)
    position = models.PositiveIntegerField(default=1)
    is_published = models.BooleanField(default=False)
    opens_at = models.DateTimeField(null=True, blank=True)
    prerequisite = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='unlocks')

    class Meta:
        ordering = ['position', 'id']
        constraints = [models.UniqueConstraint(fields=['course', 'position'], name='unique_module_position')]


class Step(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='steps')
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=12, choices=[('text', 'Текст'), ('video', 'Видео'), ('file', 'Файл'), ('assignment', 'Задание'), ('quiz', 'Тест'), ('code', 'Python')], default='text')
    content = models.TextField(blank=True)
    video_url = models.URLField(blank=True)
    # Lecture transcript for video steps: blocks that start with "MM:SS Title" become
    # clickable chapters next to the player.
    transcript = models.TextField(blank=True)
    material = models.ForeignKey(LessonMaterial, null=True, blank=True, on_delete=models.SET_NULL, related_name='steps')
    assignment = models.ForeignKey('assessment.Assignment', null=True, blank=True, on_delete=models.RESTRICT, related_name='steps')
    quiz = models.ForeignKey('assessment.Quiz', null=True, blank=True, on_delete=models.RESTRICT, related_name='steps')
    code_problem = models.ForeignKey('codejudge.CodeProblem', null=True, blank=True, on_delete=models.RESTRICT, related_name='steps')
    position = models.PositiveIntegerField(default=1)
    is_published = models.BooleanField(default=False)
    required = models.BooleanField(default=True)
    pass_percent = models.PositiveIntegerField(default=60)

    class Meta:
        ordering = ['position', 'id']
        constraints = [models.UniqueConstraint(fields=['lesson', 'position'], name='unique_step_position'),
                       models.CheckConstraint(condition=models.Q(pass_percent__lte=100), name='step_pass_percent_range')]


class StepProgress(models.Model):
    enrollment = models.ForeignKey('courses.Enrollment', on_delete=models.CASCADE, related_name='step_progress')
    step = models.ForeignKey(Step, on_delete=models.CASCADE)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['enrollment', 'step'], name='unique_enrollment_step')]


class MediaUpload(models.Model):
    import uuid
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    owner = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    filename = models.CharField(max_length=200)
    title = models.CharField(max_length=200)
    size = models.PositiveBigIntegerField()
    content_type = models.CharField(max_length=100)
    staging_key = models.CharField(max_length=300)
    multipart_id = models.TextField(blank=True)
    part_size = models.PositiveIntegerField(default=0)
    fingerprint = models.CharField(max_length=64, blank=True)
    state = models.CharField(max_length=12, default='pending')
    material = models.ForeignKey(LessonMaterial, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()


class StorageDeletion(models.Model):
    name = models.CharField(max_length=500, unique=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
