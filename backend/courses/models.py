
from django.db import models
from django.conf import settings
from media_paths import course_media_upload_to


class Course(models.Model):
    title = models.CharField(max_length=200)
    content_language = models.CharField(max_length=5, default='ru', choices=[('ru', 'Русский'), ('kk', 'Қазақша'), ('en', 'English'), ('other', 'Другой язык')])
    content_translation = models.CharField(max_length=12, default='original', choices=[('original', 'Сохранять язык курса'), ('localized', 'Подготовленные переводы')])

    description = models.TextField(blank=True)

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'is_active': True},
        related_name='courses_taught'
    )

    is_published = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class CourseImage(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='description_images')
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to=course_media_upload_to, max_length=500)


class Enrollment(models.Model):
    run = models.ForeignKey('CourseRun', on_delete=models.CASCADE, related_name='enrollments')
    status = models.CharField(max_length=12, default='active', choices=[('active', 'Активно'), ('completed', 'Завершено'), ('archived', 'Архив'), ('removed', 'Доступ отозван')])
    last_step = models.ForeignKey('learning.Step', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    last_seen_at = models.DateTimeField(null=True, blank=True)
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'is_active': True},
        related_name='enrollments'
    )

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='enrollments'
    )

    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'run'],
                name='unique_student_run'
            )
        ]

    def __str__(self):
        return f'{self.student.username} - {self.course.title}'

    def save(self, *args, **kwargs):
        if not self.run_id:
            self.run = default_run(self.course)
        if self.run.course_id != self.course_id:
            from django.core.exceptions import ValidationError
            raise ValidationError('Группа относится к другому курсу')
        super().save(*args, **kwargs)


class CourseRun(models.Model):
    release_mode = models.CharField(max_length=10, default='manual', choices=[('manual', 'Обычный доступ'), ('weekly', 'Учебные недели'), ('dates', 'Даты модулей')])
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='runs')
    title = models.CharField(max_length=200, default='Самостоятельное обучение')
    kind = models.CharField(max_length=12, choices=[('self_paced', 'Самостоятельно'), ('cohort', 'Группа')], default='self_paced')
    teachers = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='teaching_runs', blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_open = models.BooleanField(default=True)
    join_code = models.CharField(max_length=64, unique=True, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['course'], condition=models.Q(kind='self_paced'), name='one_selfpaced_run'),
            models.CheckConstraint(condition=models.Q(starts_at__isnull=True) | models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=models.F('starts_at')), name='run_valid_dates'),
        ]


class CourseMember(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='team')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='course_memberships')
    role = models.CharField(max_length=12, choices=[('owner', 'Владелец'), ('editor', 'Редактор')], default='editor')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['course', 'user'], name='unique_course_member')]


class RunModuleRelease(models.Model):
    run = models.ForeignKey(CourseRun, on_delete=models.CASCADE, related_name='module_releases')
    module = models.ForeignKey('learning.Module', on_delete=models.CASCADE, related_name='run_releases')
    week = models.PositiveIntegerField(default=1)
    opens_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['run', 'module'], name='unique_run_module_release'),
                       models.CheckConstraint(condition=models.Q(week__gte=1, week__lte=520), name='module_release_week_range'),
                       models.CheckConstraint(condition=models.Q(due_at__isnull=True) | models.Q(opens_at__isnull=True) | models.Q(due_at__gt=models.F('opens_at')), name='module_deadline_after_opening')]


class RunCheckpoint(models.Model):
    run = models.ForeignKey(CourseRun, on_delete=models.CASCADE, related_name='checkpoints')
    quiz = models.ForeignKey('assessment.Quiz', on_delete=models.CASCADE, related_name='checkpoints')
    kind = models.CharField(max_length=8, choices=[('weekly', 'Недельный тест'), ('monthly', 'Контроль за 4 недели')])
    period = models.PositiveIntegerField(default=1)
    required = models.BooleanField(default=True)
    pass_percent = models.PositiveIntegerField(default=60)
    # Null dates follow the group start; explicit dates are deliberate exceptions.
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['run', 'kind', 'period'], name='unique_run_checkpoint_period'),
                       models.UniqueConstraint(fields=['run', 'quiz'], name='unique_run_checkpoint_quiz'),
                       models.CheckConstraint(condition=models.Q(period__gte=1, period__lte=520), name='checkpoint_period_range'),
                       models.CheckConstraint(condition=models.Q(pass_percent__lte=100), name='checkpoint_pass_range')]


class CourseBookmark(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    kind = models.CharField(max_length=12, choices=[('favorite', 'Избранное'), ('wishlist', 'Хочу пройти')])

    class Meta:
        constraints = [models.UniqueConstraint(fields=['course', 'user', 'kind'], name='unique_course_bookmark')]


def default_run(course):
    return CourseRun.objects.get_or_create(course=course, kind='self_paced')[0]
