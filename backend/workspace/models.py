import uuid
from django.conf import settings
from django.db import models


class AttentionPolicy(models.Model):
    run = models.OneToOneField('courses.CourseRun', on_delete=models.CASCADE)
    inactive_days = models.PositiveIntegerField(default=0)
    missing_count = models.PositiveIntegerField(default=2)
    low_score_percent = models.PositiveIntegerField(default=0)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)


class LessonPulse(models.Model):
    lesson = models.ForeignKey('learning.Lesson', on_delete=models.CASCADE)
    enrollment = models.ForeignKey('courses.Enrollment', on_delete=models.CASCADE)
    choice = models.CharField(max_length=12, choices=[('clear', 'Понятно'), ('hard', 'Сложно'), ('example', 'Нужен пример')])
    note = models.CharField(max_length=1000, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['lesson', 'enrollment'], name='workspace_unique_pulse')]


class AssignmentRubric(models.Model):
    assignment = models.OneToOneField('assessment.Assignment', on_delete=models.CASCADE, related_name='rubric')
    version = models.PositiveIntegerField(default=1)
    criteria = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)


class BankQuestion(models.Model):
    family = models.UUIDField(default=uuid.uuid4)
    version = models.PositiveIntegerField(default=1)
    is_current = models.BooleanField(default=True)
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE)
    body = models.TextField()
    category = models.CharField(max_length=100, blank=True)
    options = models.JSONField(default=list)
    correct_index = models.PositiveIntegerField()
    is_ready = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['family', 'version'], name='workspace_bank_version'),
                      models.UniqueConstraint(fields=['family'], condition=models.Q(is_current=True), name='workspace_bank_current')]
