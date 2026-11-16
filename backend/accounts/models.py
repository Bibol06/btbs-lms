
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.functions import Lower
from django.db.models import Q


class User(AbstractUser):
    admin_scope = models.CharField(max_length=10, default='full', choices=[('full', 'Полный доступ'), ('system', 'Системный администратор'), ('learning', 'Администратор обучения')])

    ROLE_CHOICES = [
        ('student', 'Студент'),
        ('teacher', 'Преподаватель'),
        ('admin', 'Администратор'),
    ]

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='student'
    )

    bio = models.TextField(blank=True)
    organization = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    preferred_language = models.CharField(max_length=2, blank=True, default='', choices=[('kk', 'Қазақша'), ('ru', 'Русский'), ('en', 'English')])

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower('username'), name='unique_username_casefold'),
            models.UniqueConstraint(Lower('email'), condition=~Q(email=''), name='unique_nonempty_email_casefold'),
        ]

    def __str__(self):
        return self.username


class SystemAuditEvent(models.Model):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='system_actions')
    target = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='system_changes')
    action = models.CharField(max_length=80)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class RecoveryThrottle(models.Model):
    key = models.CharField(max_length=80, unique=True)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)


class PasswordResetDelivery(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    credential_stamp = models.CharField(max_length=64)
    base_url = models.CharField(max_length=300)
    language = models.CharField(max_length=2, default='ru')
    state = models.CharField(max_length=12, default='pending', db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True)
