"""Read-only operational views; every teacher query is scoped to managed runs."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q, Count, Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET

from accounts.identity import identity_data, display_name
from common import api, authenticated, ApiError, query_integer
from courses.access import can_teach, is_platform_admin, require_run
from courses.models import Course, Enrollment
from communication.models import AuditEvent
from learning.services import course_progress
from .deadline_views import managed_runs, student_tasks
from .models import Submission, GradeReview, QuizAttempt
from .quiz_services import finalize_due_attempts


def require_manager(request, admin=False):
    authenticated(request)
    if not (is_platform_admin(request.user) if admin else can_teach(request.user)):
        raise ApiError('Доступ только администратору' if admin else 'Доступ только преподавателю и администратору', 403)


def paginate(request, qs):
    page = query_integer(request, 'page', 1, 100000, 1)
    total = qs.count()
    return list(qs[(page-1)*20:page*20]), {'page': page, 'total': total, 'next_page': page + 1 if page*20 < total else None}


def run_scope(request):
    runs = managed_runs(request.user)
    for key, field in [('course_id', 'course_id'), ('run_id', 'id')]:
        if request.GET.get(key):
            runs = runs.filter(**{field: query_integer(request, key, 1, 2**63-1)})
    return runs


def people_search(qs, search, prefix=''):
    for word in search.split():
        qs = qs.filter(Q(**{prefix+'first_name__icontains': word}) | Q(**{prefix+'last_name__icontains': word}) | Q(**{prefix+'username__icontains': word}))
    return qs


@require_GET
@api
def overview(request):
    require_manager(request)
    now = timezone.now()
    runs = managed_runs(request.user)
    courses = Course.objects.all() if is_platform_admin(request.user) else Course.objects.filter(Q(teacher=request.user) | Q(team__user=request.user) | Q(runs__teachers=request.user)).distinct()
    enrollments = Enrollment.objects.filter(run__in=runs)
    submissions = Submission.objects.filter(enrollment__in=enrollments)
    pending = submissions.filter(status='submitted')
    metrics = {'courses': courses.count(), 'published_courses': courses.filter(is_published=True).count(),
               'groups': runs.filter(kind='cohort').count(),
               'students': enrollments.filter(status__in=['active', 'completed']).values('student_id').distinct().count(),
               'active_enrollments': enrollments.filter(status='active').count(),
               'completed_enrollments': enrollments.filter(status='completed').count(),
               'pending': pending.count(), 'overdue': pending.filter(review_due_at__lte=now).count(),
               'unassigned': pending.filter(reviewer__isnull=True).count(),
               'returned': submissions.filter(status='returned').count(),
               'reviewed_week': GradeReview.objects.filter(submission__enrollment__in=enrollments, created_at__gte=now-timedelta(days=7)).count()}
    if is_platform_admin(request.user):
        users = get_user_model().objects.all()
        metrics['users'] = users.count()
        metrics['inactive_users'] = users.filter(is_active=False).count()
    options = [{'id': r.id, 'course_id': r.course_id, 'title': r.title, 'course': r.course.title} for r in runs.order_by('course__title', 'id')]
    return JsonResponse({'scope': 'platform' if is_platform_admin(request.user) else 'assigned_courses',
                         'metrics': metrics, 'runs': options, 'server_now': now})


@require_GET
@api
def students(request):
    require_manager(request)
    qs = Enrollment.objects.filter(run__in=run_scope(request)).select_related('student', 'course', 'run', 'last_step')
    search = request.GET.get('search', '').strip()[:150]
    if search:
        qs = people_search(qs, search, 'student__')
    status = request.GET.get('status', 'all')
    if status != 'all':
        if status not in ('active', 'completed', 'archived', 'removed'):
            raise ApiError('Неизвестный статус ученика')
        qs = qs.filter(status=status)
    qs = qs.annotate(pending_count=Count('submission_records', filter=Q(submission_records__status='submitted'), distinct=True),
                     returned_count=Count('submission_records', filter=Q(submission_records__status='returned'), distinct=True),
                     graded_count=Count('submission_records', filter=Q(submission_records__status='graded'), distinct=True))
    rows, page = paginate(request, qs.order_by('student__last_name', 'student__first_name', 'id'))
    finalize_due_attempts(QuizAttempt.objects.filter(enrollment_id__in=[e.id for e in rows]))
    return JsonResponse({**page, 'students': [{**identity_data(e.student), 'enrollment_id': e.id, 'course_id': e.course_id,
        'course': e.course.title, 'run_id': e.run_id, 'run': e.run.title, 'status': e.status,
        'last_seen_at': e.last_seen_at, 'enrolled_at': e.enrolled_at, 'last_step': e.last_step.title if e.last_step else None,
        'progress': course_progress(e.course, e), 'pending': e.pending_count, 'returned': e.returned_count, 'graded': e.graded_count,
        'target': f'/#course={e.course_id}&run={e.run_id}&tab=results&student={e.student_id}'} for e in rows]})


@require_GET
@api
def enrollment_tasks(request, enrollment_id):
    require_manager(request)
    e = get_object_or_404(Enrollment.objects.select_related('student', 'run__course'), pk=enrollment_id, run__in=managed_runs(request.user))
    require_run(request, e.run, manage=True)
    finalize_due_attempts(QuizAttempt.objects.filter(enrollment=e))
    return JsonResponse({'student': identity_data(e.student), 'tasks': student_tasks(e.student, [e.id]),
                         'historical': e.status in ('archived', 'removed'), 'server_now': timezone.now()})


@require_GET
@api
def teachers(request):
    require_manager(request, admin=True)
    User = get_user_model()
    qs = User.objects.filter(Q(role='teacher') | Q(courses_taught__isnull=False) | Q(course_memberships__isnull=False) | Q(teaching_runs__isnull=False)).distinct()
    search = request.GET.get('search', '').strip()[:150]
    if search:
        qs = people_search(qs, search)
    rows, page = paginate(request, qs.order_by('last_name', 'first_name', 'id'))
    now = timezone.now()
    results = []
    for user in rows:
        # Scope by actual course/run assignments, even when a platform admin teaches.
        runs = managed_runs(user) if not is_platform_admin(user) else managed_runs(request.user).filter(Q(teachers=user) | Q(course__teacher=user) | Q(course__team__user=user)).distinct()
        assigned = Submission.objects.filter(reviewer=user, status='submitted', enrollment__run__in=runs)
        reviews = GradeReview.objects.filter(reviewer=user, submission__enrollment__run__in=runs)
        results.append({**identity_data(user, teaching=True), 'is_active': user.is_active,
            'courses': Course.objects.filter(Q(teacher=user) | Q(team__user=user) | Q(runs__teachers=user)).distinct().count(), 'groups': runs.filter(kind='cohort').count(),
            'students': Enrollment.objects.filter(run__in=runs, status__in=['active', 'completed']).values('student_id').distinct().count(),
            'pending': assigned.count(), 'overdue': assigned.filter(review_due_at__lte=now).count(),
            'unassigned': Submission.objects.filter(enrollment__run__in=runs, status='submitted', reviewer__isnull=True).count(),
            'reviewed_week': reviews.filter(created_at__gte=now-timedelta(days=7)).count(),
            'last_review_at': reviews.aggregate(value=Max('created_at'))['value']})
    return JsonResponse({**page, 'teachers': results, 'server_now': now})


@require_GET
@api
def courses(request):
    require_manager(request, admin=True)
    qs = Course.objects.select_related('teacher').order_by('-id')
    search = request.GET.get('search', '').strip()[:150]
    if search:
        qs = qs.filter(title__icontains=search)
    rows, page = paginate(request, qs)
    now = timezone.now()
    return JsonResponse({**page, 'courses': [{'id': c.id, 'title': c.title, 'description': c.description, 'is_published': c.is_published,
        'teacher': display_name(c.teacher) if c.teacher else 'Не назначен',
        'groups': c.runs.filter(kind='cohort').count(), 'students': c.enrollments.filter(status__in=['active', 'completed']).values('student_id').distinct().count(),
        'pending': c.assignments.filter(submissions__status='submitted').aggregate(value=Count('submissions'))['value'],
        'overdue': c.assignments.filter(submissions__status='submitted', submissions__review_due_at__lte=now).aggregate(value=Count('submissions'))['value']} for c in rows]})


@require_GET
@api
def activity(request):
    require_manager(request, admin=True)
    events = AuditEvent.objects.select_related('actor', 'course').order_by('-created_at', '-id')
    if request.GET.get('course_id'):
        events = events.filter(course_id=query_integer(request, 'course_id', 1, 2**63-1))
    rows, page = paginate(request, events)
    return JsonResponse({**page, 'events': [{'id': e.id, 'actor': identity_data(e.actor) if e.actor else None,
        'course': e.course.title, 'course_id': e.course_id, 'action': e.action, 'context': e.context, 'created_at': e.created_at} for e in rows]})
