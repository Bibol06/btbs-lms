"""Code checks run here, in the 'judge' queue, instead of holding a web thread for up to 20 s."""
from datetime import timedelta

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from .runner import run_python

# A submission still 'running' after this long is reported as a service error. The
# queue drops checks older than QUEUE_EXPIRES, and one check is capped at 20 s.
STALE_AFTER = timedelta(minutes=2)
QUEUE_EXPIRES = 90
PRACTICE_TTL = 600


def practice_key(token):
    return f'codejudge:practice:{token}'


def practice_busy_key(user_id):
    return f'codejudge:practice-busy:{user_id}'


def grade(record, cases, results):
    details, passed = [], 0
    for case, result in zip(cases, results):
        ok = result['status'] == 'ok' and result['stdout'].strip() == case.expected.strip()
        passed += int(ok)
        detail = {'sample': case.is_sample, 'status': 'accepted' if ok else 'wrong_answer' if result['status'] == 'ok' else result['status']}
        if case.is_sample:
            detail.update({'stdout': result['stdout'], 'stderr': result['stderr']})
        details.append(detail)
    return passed, details


# Hard cap well above the 20 s sandbox timeout: a stuck child is killed and replaced.
@shared_task(time_limit=90)
def judge_submission(submission_id):
    from analytics.tracking import record as record_activity
    from learning.services import refresh_completion
    from .models import CodeSubmission
    fresh = timezone.now() - STALE_AFTER
    record = (CodeSubmission.objects.select_related('problem', 'enrollment__student')
              .filter(pk=submission_id, status='running', created_at__gte=fresh).first())
    if record is None:
        return  # already finished, or expired and reported as a service error
    try:
        cases = list(record.problem.test_cases.all())
        results = run_python(record.code, [c.stdin for c in cases])
        passed, details = grade(record, cases, results)
        status = 'accepted' if passed == len(cases) else 'rejected'
    except Exception:
        CodeSubmission.objects.filter(pk=record.pk, status='running').update(status='service_error')
        raise
    # Only a check that is still pending may write a verdict.
    if not CodeSubmission.objects.filter(pk=record.pk, status='running').update(
            status=status, passed=passed, total=len(cases), details=details):
        return
    refresh_completion(record.enrollment)
    record_activity(record.enrollment.student, 'code_submitted', enrollment=record.enrollment, dedupe=f'code:{record.id}')


@shared_task(time_limit=90)
def practice_run(token, user_id, code, stdin):
    """Practice runs never change grades; the result is kept briefly for its owner only."""
    from common import ApiError
    entry = {'user': user_id, 'error': 'Изолированная среда временно недоступна', 'code': 503}
    try:
        entry = {'user': user_id, 'result': run_python(code, [stdin])[0]}
    except ApiError as exc:
        entry['error'], entry['code'] = exc.message, exc.status
    finally:
        cache.set(practice_key(token), entry, PRACTICE_TTL)
        if cache.get(practice_busy_key(user_id)) == token:
            cache.delete(practice_busy_key(user_id))
