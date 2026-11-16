from celery import shared_task

from background import exclusive


def capture_all_progress():
    """Record current progress for every enrollment; never fabricates historical values."""
    from analytics.models import TrackingCoverage
    from analytics.tracking import capture_progress
    from courses.models import Enrollment
    TrackingCoverage.objects.get_or_create(pk=1)
    count, last = 0, 0
    queryset = Enrollment.objects.select_related('course', 'run').order_by('id')
    while True:
        rows = list(queryset.filter(id__gt=last)[:100])
        if not rows:
            return count
        for enrollment in rows:
            capture_progress(enrollment, None)
            count += 1
        last = rows[-1].id


@shared_task
@exclusive(ttl=1800)
def capture_progress_snapshots():
    return capture_all_progress()
