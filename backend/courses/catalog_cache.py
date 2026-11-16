"""Cache only non-sensitive lesson counts, never access rights or student answers."""
import hashlib
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Q


def key(course_id):
    namespace = hashlib.sha256(str(settings.DATABASES['default']['NAME']).encode()).hexdigest()[:16]
    return f'catalog-counts:v1:{namespace}:{course_id}'


def attach_counts(courses):
    from learning.models import Lesson
    keys = {c.id: key(c.id) for c in courses}
    try:
        cached = cache.get_many(keys.values())
    except Exception:
        cached = {}
    missing = [cid for cid, k in keys.items() if k not in cached]
    values = {cid: (0, 0) for cid in missing}
    for row in Lesson.objects.filter(course_id__in=missing).values('course_id').annotate(total=Count('id'), public=Count('id', filter=Q(is_published=True))):
        values[row['course_id']] = (row['total'], row['public'])
    fresh = {keys[cid]: counts for cid, counts in values.items()}
    if fresh:
        try:
            cache.set_many(fresh, timeout=30)
        except Exception:
            pass
    cached.update(fresh)
    for c in courses:
        c.all_lessons, c.public_lessons = cached[keys[c.id]]
    return courses


def invalidate_lesson_counts(sender, instance, **kwargs):
    target = key(instance.course_id)
    def remove():
        try:
            cache.delete(target)
        except Exception:
            pass
    remove()
    transaction.on_commit(remove)
