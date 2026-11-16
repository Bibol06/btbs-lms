from django.contrib import admin
from .models import Announcement, Conversation, Participant, Message, Discussion, Comment, Notification, Event, NotificationPreference, AuditEvent

admin.site.register([Announcement, Conversation, Participant, Message, Discussion, Comment, Notification, Event, NotificationPreference, AuditEvent])
