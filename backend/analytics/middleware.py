import logging
import json
from django.db import DatabaseError, transaction
from django.utils import timezone
from .tracking import session_digest, touch_session
from .models import SessionRecord

logger = logging.getLogger(__name__)


class ActiveSessionMiddleware:
    """Only actual successful writes update presence; GET polling does not."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        before = session_digest(request)
        response = self.get_response(request)
        if not request.user.is_authenticated or response.status_code >= 400:
            return response
        path = request.path
        action = request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and (
            path.startswith(('/api/learning/', '/api/study/', '/api/code/', '/api/courses/', '/api/workspace/')) or
            path == '/api/analytics/evaluations/' or
            request.method == 'POST' and path.startswith('/api/communication/'))
        if path.startswith('/api/workspace/') and path.endswith('/preview/'):
            action = False
        if action and path.startswith('/api/study/attempts/') and request.method == 'POST':
            try:
                payload = json.loads(request.body)
                if isinstance(payload, dict) and payload.get('finish_saved') is True:
                    action = False
            except (ValueError, UnicodeDecodeError):
                pass
        after = session_digest(request)
        account_changed = before and after != before and path.startswith('/api/auth/')
        if not action and not account_changed:
            return response
        try:
            with transaction.atomic():
                if account_changed:
                    SessionRecord.objects.filter(key_digest=before, ended_at__isnull=True).update(ended_at=timezone.now(), end_reason='account_changed')
                if action:
                    touch_session(request)
        except DatabaseError:
            logger.exception('Session activity recording unavailable')
        return response
