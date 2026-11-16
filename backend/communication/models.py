import uuid
from django.conf import settings
from django.db import models


class Announcement(models.Model):
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='announcements')
    run = models.ForeignKey('courses.CourseRun', null=True, blank=True, on_delete=models.CASCADE)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    title = models.CharField(max_length=200)
    body = models.TextField()
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Conversation(models.Model):
    enrollment = models.OneToOneField('courses.Enrollment', on_delete=models.CASCADE, related_name='conversation')
    created_at = models.DateTimeField(auto_now_add=True)


class Participant(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    read_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['conversation', 'user'], name='unique_conversation_participant')]


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class Discussion(models.Model):
    lesson = models.ForeignKey('learning.Lesson', on_delete=models.CASCADE)
    run = models.ForeignKey('courses.CourseRun', on_delete=models.CASCADE)
    is_closed = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['lesson', 'run'], name='unique_run_lesson_discussion')]


class Comment(models.Model):
    is_resolved = models.BooleanField(default=False)
    is_staff_reply = models.BooleanField(default=False)
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies')
    body = models.TextField()
    is_hidden = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Event(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=200, unique=True)
    kind = models.CharField(max_length=40)
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE)
    run = models.ForeignKey('courses.CourseRun', null=True, on_delete=models.CASCADE)
    title = models.CharField(max_length=250)
    target = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)


class Notification(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='notifications')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    read_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['event', 'recipient'], name='unique_notification_delivery')]


class NotificationPreference(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE)
    muted_kinds = models.JSONField(default=list)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'course'], name='unique_notification_preferences')]


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE)
    action = models.CharField(max_length=80)
    context = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
