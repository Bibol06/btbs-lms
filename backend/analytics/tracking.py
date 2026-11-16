import hashlib
import ipaddress
import logging
import re
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import DatabaseError, transaction
from django.utils import timezone

from courses.access import can_manage_run, can_teach
from .models import ActivityEvent, AttendanceDay, ProgressSnapshot, SessionRecord

logger = logging.getLogger(__name__)


def report_zone():
    return ZoneInfo(getattr(settings, 'ANALYTICS_TIMEZONE', 'Asia/Qyzylorda'))


def user_role(user):
    from accounts.permissions import is_admin
    return 'admin' if is_admin(user) else 'teacher' if can_teach(user) else 'student'


def device_info(ua):
    browser = 'Не определён'
    for token, name in [('Edg', 'Edge'), ('OPR', 'Opera'), ('Firefox', 'Firefox'), ('CriOS', 'Chrome iOS'), ('HeadlessChrome', 'Chrome Headless'), ('Chrome', 'Chrome'), ('Version', 'Safari')]:
        match = re.search(r'\b'+token+r'/([\d.]+)', ua)
        if match:
            browser = f'{name} {match.group(1).split(".")[0]}'
            break
    os_name = 'Не определена'
    for token, name in [('iPad', 'iPadOS'), ('iPhone', 'iOS'), ('Android', 'Android'), ('Windows', 'Windows'), ('Macintosh', 'macOS'), ('Linux', 'Linux')]:
        if token in ua:
            os_name = name
            break
    device = 'Планшет' if 'iPad' in ua or ('Android' in ua and 'Mobile' not in ua) else 'Телефон' if 'Mobile' in ua or 'iPhone' in ua else 'Компьютер' if any(t in ua for t in ('Windows', 'Macintosh', 'X11', 'Linux')) else 'Не определено'
    return browser, os_name, device


def session_digest(request):
    key = request.session.session_key
    return hashlib.sha256(key.encode()).hexdigest() if key else None


def attendance(user, now, login=False, active=False):
    day = now.astimezone(report_zone()).date()
    row, _ = AttendanceDay.objects.select_for_update().get_or_create(user=user, date=day, defaults={'first_seen_at': now, 'last_seen_at': now})
    row.first_seen_at = min(row.first_seen_at, now)
    row.last_seen_at = max(row.last_seen_at, now)
    row.login_count += int(login)
    row.platform_active |= active
    row.save(update_fields=['first_seen_at', 'last_seen_at', 'login_count', 'platform_active'])


@transaction.atomic
def touch_session(request, login=False, user=None):
    digest = session_digest(request)
    user = user or getattr(request, 'user', None)
    if not digest or not user or not user.is_authenticated:
        return
    now = timezone.now()
    from django.contrib.sessions.models import Session
    expires = Session.objects.filter(session_key=request.session.session_key).values_list('expire_date', flat=True).first() or request.session.get_expiry_date()
    ua = request.META.get('HTTP_USER_AGENT', '')[:600]
    browser, os_name, device = device_info(ua)
    try:
        address = str(ipaddress.ip_address(request.META.get('REMOTE_ADDR', '')))
    except ValueError:
        address = None
    row, created = SessionRecord.objects.select_for_update().get_or_create(key_digest=digest, defaults={
        'user': user, 'browser': browser, 'os': os_name, 'device': device, 'ip_address': address,
        'user_agent': ua, 'started_at': now, 'last_seen_at': now, 'expires_at': expires,
        'entry_kind': 'login' if login else 'observed'})
    if row.user_id != user.id or row.ended_at:
        return
    row.last_seen_at = now
    row.expires_at = expires
    row.save(update_fields=['last_seen_at', 'expires_at'])
    attendance(user, now, login=login and created, active=True)


def finish_session(request):
    digest = session_digest(request)
    if digest:
        SessionRecord.objects.filter(key_digest=digest, ended_at__isnull=True).update(ended_at=timezone.now(), end_reason='logout')


def record(user, kind, enrollment=None, run=None, step=None, dedupe=None, when=None, active=True):
    """No answers, code, cookies or message text enter the event stream."""
    if not user or not user.is_authenticated:
        return
    try:
        with transaction.atomic():
            now = when or timezone.now()
            run = run or (enrollment.run if enrollment else None)
            role = 'student' if enrollment and not can_manage_run(user, run) else user_role(user)
            defaults = {'user': user, 'kind': kind, 'enrollment': enrollment, 'run': run, 'step': step,
                        'lesson_id': step.lesson_id if step else None, 'occurred_at': now, 'actor_role': role}
            if dedupe:
                _, created = ActivityEvent.objects.get_or_create(dedupe_key=dedupe, defaults=defaults)
            else:
                ActivityEvent.objects.create(**defaults)
                created = True
            if created and active:
                attendance(user, now, active=True)
    except DatabaseError:
        logger.exception('Activity analytics unavailable')


def capture_progress(enrollment, progress, fingerprint=None):
    """Sparse truthful snapshots: first observation is a baseline, never backdated."""
    from learning.services import visible_steps
    try:
        with transaction.atomic():
            # Enrollment row serializes snapshots from concurrent tabs and workers.
            from courses.models import Enrollment
            Enrollment.objects.select_for_update().get(pk=enrollment.pk)
            # A background batch may have been read before a concurrent grade committed.
            # Re-read after acquiring the lock so it cannot overwrite a newer observation.
            from learning.services import course_progress
            progress = course_progress(enrollment.course, enrollment)
            if fingerprint is None:
                spec = list(visible_steps(enrollment.course).filter(required=True).order_by('id').values_list('id', 'kind', 'pass_percent', 'assignment_id', 'quiz_id', 'code_problem_id'))
                if not spec:
                    spec = list(enrollment.course.lessons.filter(is_published=True).values_list('id', flat=True))
                fingerprint = hashlib.sha256(repr(spec).encode()).hexdigest()
            previous = ProgressSnapshot.objects.filter(enrollment=enrollment).order_by('-captured_at', '-id').first()
            if previous and (previous.completed, previous.total, previous.program_fingerprint) == (progress['completed'], progress['total'], fingerprint):
                return
            ProgressSnapshot.objects.create(enrollment=enrollment, completed=progress['completed'], total=progress['total'], program_fingerprint=fingerprint,
                reason='baseline' if previous is None else 'content' if previous.program_fingerprint != fingerprint else 'progress')
    except DatabaseError:
        logger.exception('Progress analytics unavailable')
