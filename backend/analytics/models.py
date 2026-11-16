from django.conf import settings
from django.db import models
from django.utils import timezone


class TrackingCoverage(models.Model):
    started_at = models.DateTimeField(default=timezone.now)


class ActivityEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    enrollment = models.ForeignKey('courses.Enrollment', null=True, on_delete=models.CASCADE)
    run = models.ForeignKey('courses.CourseRun', null=True, on_delete=models.CASCADE)
    step = models.ForeignKey('learning.Step', null=True, on_delete=models.SET_NULL)
    lesson = models.ForeignKey('learning.Lesson', null=True, on_delete=models.SET_NULL)
    kind = models.CharField(max_length=32)
    actor_role = models.CharField(max_length=12)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    dedupe_key = models.CharField(max_length=180, null=True, unique=True)

    class Meta:
        indexes = [models.Index(fields=['run', 'occurred_at']), models.Index(fields=['user', 'occurred_at'])]


class ProgressSnapshot(models.Model):
    enrollment = models.ForeignKey('courses.Enrollment', on_delete=models.CASCADE)
    captured_at = models.DateTimeField(default=timezone.now, db_index=True)
    completed = models.PositiveIntegerField()
    total = models.PositiveIntegerField()
    program_fingerprint = models.CharField(max_length=64)
    reason = models.CharField(max_length=16, default='progress')

    class Meta:
        indexes = [models.Index(fields=['enrollment', '-captured_at'])]
        constraints = [models.CheckConstraint(condition=models.Q(completed__lte=models.F('total')), name='analytics_progress_in_range')]


class SessionRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key_digest = models.CharField(max_length=64, unique=True)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True)
    end_reason = models.CharField(max_length=20, blank=True)
    browser = models.CharField(max_length=60)
    os = models.CharField(max_length=60)
    device = models.CharField(max_length=24)
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.CharField(max_length=600, blank=True)
    entry_kind = models.CharField(max_length=16, default='login')


class AttendanceDay(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    date = models.DateField(db_index=True)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    login_count = models.PositiveIntegerField(default=0)
    platform_active = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'date'], name='analytics_unique_attendance_day')]


class LessonEvaluation(models.Model):
    lesson = models.ForeignKey('learning.Lesson', on_delete=models.CASCADE)
    run = models.ForeignKey('courses.CourseRun', on_delete=models.CASCADE)
    pre_quiz = models.ForeignKey('assessment.Quiz', null=True, on_delete=models.SET_NULL, related_name='+')
    post_quiz = models.ForeignKey('assessment.Quiz', null=True, on_delete=models.SET_NULL, related_name='+')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['lesson', 'run'], name='analytics_unique_lesson_evaluation')]
