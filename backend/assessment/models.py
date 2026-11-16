from django.conf import settings
from django.db import models
from django.db.models import Q, F
from media_paths import course_media_upload_to


class EnrollmentBound(models.Model):
    enrollment = models.ForeignKey('courses.Enrollment', on_delete=models.CASCADE, related_name='%(class)s_records')

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.enrollment_id:
            from courses.models import Enrollment, default_run
            source = getattr(self, 'assignment', None) or getattr(self, 'quiz', None) or self.lesson
            self.enrollment = Enrollment.objects.get(course=source.course, student_id=self.student_id, run=default_run(source.course))
        super().save(*args, **kwargs)


class Assignment(models.Model):
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='assignments')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    allow_late = models.BooleanField(default=False)
    cutoff_at = models.DateTimeField(null=True, blank=True)
    review_hours = models.PositiveIntegerField(default=48)
    max_score = models.PositiveIntegerField(default=100)
    max_attempts = models.PositiveIntegerField(default=3)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        constraints = [
            models.CheckConstraint(condition=Q(max_score__gte=1), name='assignment_positive_score'),
            models.CheckConstraint(condition=Q(max_attempts__gte=1), name='assignment_positive_attempts'),
            models.CheckConstraint(condition=Q(review_hours__gte=1) & Q(review_hours__lte=720), name='assignment_review_hours_range'),
            models.CheckConstraint(condition=Q(due_at__isnull=True) | Q(cutoff_at__isnull=True) | Q(cutoff_at__gte=F('due_at')), name='assignment_cutoff_after_due'),
        ]


class Submission(EnrollmentBound):
    review_version = models.PositiveIntegerField(default=0)
    rubric_result = models.JSONField(default=dict)
    due_at_snapshot = models.DateTimeField(null=True, blank=True)
    is_late = models.BooleanField(default=False)
    review_due_at = models.DateTimeField(null=True, blank=True)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_reviews')
    revision_due_at = models.DateTimeField(null=True, blank=True)
    revision_of = models.OneToOneField('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='revision_submission')
    status = models.CharField(max_length=12, default='submitted', choices=[('submitted', 'На проверке'), ('graded', 'Проверено'), ('returned', 'На доработку')])
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    attempt_no = models.PositiveIntegerField()
    text_answer = models.TextField(blank=True)
    file = models.FileField(upload_to=course_media_upload_to, max_length=500, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    score = models.PositiveIntegerField(null=True, blank=True)
    feedback = models.TextField(blank=True)
    graded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='graded_submissions')
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-submitted_at', '-id']
        constraints = [models.UniqueConstraint(fields=['assignment', 'enrollment', 'attempt_no'], name='unique_submission_attempt_run')]


class Quiz(models.Model):
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='quizzes')
    title = models.CharField(max_length=200)
    max_attempts = models.PositiveIntegerField(default=3)
    time_limit_sec = models.PositiveIntegerField(default=900)
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ['id']
        constraints = [
            models.CheckConstraint(condition=Q(max_attempts__gte=1), name='quiz_positive_attempts'),
            models.CheckConstraint(condition=Q(time_limit_sec__gte=60), name='quiz_minimum_time'),
            models.CheckConstraint(condition=Q(opens_at__isnull=True) | Q(closes_at__isnull=True) | Q(closes_at__gt=F('opens_at')), name='quiz_valid_window'),
        ]


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    body = models.TextField()
    position = models.PositiveIntegerField()
    # Options and correct index are stored together; correct_index is never sent to students.
    options = models.JSONField(default=list)
    correct_index = models.PositiveIntegerField()

    class Meta:
        ordering = ['position', 'id']


class QuizAttempt(EnrollmentBound):
    auto_submitted = models.BooleanField(default=False)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    attempt_no = models.PositiveIntegerField()
    started_at = models.DateTimeField(auto_now_add=True)
    deadline_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, default='active', choices=[('active', 'Идёт'), ('finished', 'Завершён'), ('expired', 'Время истекло')])
    answers = models.JSONField(default=dict)
    score = models.PositiveIntegerField(default=0)
    max_score = models.PositiveIntegerField()

    class Meta:
        ordering = ['-id']
        constraints = [
            models.UniqueConstraint(fields=['quiz', 'enrollment', 'attempt_no'], name='unique_quiz_attempt_run'),
            models.UniqueConstraint(fields=['quiz', 'enrollment'], condition=Q(status='active'), name='one_active_quiz_attempt_run'),
            models.CheckConstraint(condition=Q(score__lte=F('max_score')), name='quiz_score_in_range'),
        ]


class LessonProgress(EnrollmentBound):
    lesson = models.ForeignKey('learning.Lesson', on_delete=models.CASCADE, related_name='progress')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['lesson', 'enrollment'], name='unique_run_lesson_progress')]


class ActivitySchedule(models.Model):
    run = models.ForeignKey('courses.CourseRun', on_delete=models.CASCADE, related_name='schedules')
    assignment = models.ForeignKey(Assignment, null=True, blank=True, on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, null=True, blank=True, on_delete=models.CASCADE)
    due_at = models.DateTimeField(null=True, blank=True)
    allow_late = models.BooleanField(default=False)
    cutoff_at = models.DateTimeField(null=True, blank=True)
    review_hours = models.PositiveIntegerField(default=48)
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)
    max_attempts = models.PositiveIntegerField(default=3)
    time_limit_sec = models.PositiveIntegerField(default=900)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=(Q(assignment__isnull=False) & Q(quiz__isnull=True)) | (Q(assignment__isnull=True) & Q(quiz__isnull=False)), name='schedule_one_activity'),
            models.UniqueConstraint(fields=['run', 'assignment'], name='unique_run_assignment_schedule'),
            models.UniqueConstraint(fields=['run', 'quiz'], name='unique_run_quiz_schedule'),
            models.CheckConstraint(condition=Q(review_hours__gte=1) & Q(review_hours__lte=720), name='schedule_review_hours_range'),
            models.CheckConstraint(condition=Q(due_at__isnull=True) | Q(cutoff_at__isnull=True) | Q(cutoff_at__gte=F('due_at')), name='schedule_cutoff_after_due'),
        ]


class GradeReview(models.Model):
    rubric_result = models.JSONField(default=dict)
    revision_due_at = models.DateTimeField(null=True, blank=True)
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=12)
    score = models.PositiveIntegerField(null=True)
    feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AssignmentExtension(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='extensions')
    enrollment = models.ForeignKey('courses.Enrollment', on_delete=models.CASCADE, related_name='assignment_extensions')
    deadline_at = models.DateTimeField()
    reason = models.CharField(max_length=500, blank=True)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['assignment', 'enrollment'], name='unique_assignment_enrollment_extension')]
