from django.db.models import Count
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.utils import timezone
from common import api, authenticated
from .models import Enrollment, CourseBookmark
from learning.services import refresh_completions
from assessment.models import Submission


@require_GET
@api
def my_learning(request):
    authenticated(request)
    from assessment.quiz_services import finalize_due_attempts
    from assessment.models import QuizAttempt
    from assessment.deadline_views import student_tasks
    finalize_due_attempts(QuizAttempt.objects.filter(student=request.user))
    tasks = student_tasks(request.user)
    result = []
    enrollments = list(Enrollment.objects.filter(student=request.user).select_related('course', 'run', 'last_step').order_by('-last_seen_at', '-id'))
    progress_rows = refresh_completions(enrollments)
    pending = dict(Submission.objects.filter(enrollment__in=enrollments, status='submitted').values('enrollment_id').annotate(n=Count('id')).values_list('enrollment_id', 'n'))
    for enrollment in enrollments:
        progress = progress_rows[enrollment.id]
        deadlines = []
        for task in tasks:
            if task['run_id'] != enrollment.run_id or task['state'] not in ('open', 'late', 'revision', 'active_quiz'):
                continue
            due = task['closes_at'] if task['state'] == 'late' else task['due_at']
            label = 'Исправить до' if task['state'] == 'revision' else 'Приём до' if task['state'] == 'late' else 'Завершить до' if task['kind'] == 'quiz' else 'Сдать до'
            if due and due >= timezone.now():
                deadlines.append({'title': task['title'], 'due_at': due, 'label': label})
        result.append({'id': enrollment.id, 'course_id': enrollment.course_id, 'course': enrollment.course.title,
            'run_id': enrollment.run_id, 'run': enrollment.run.title, 'kind': enrollment.run.kind,
            'status': enrollment.status, 'last_step_id': enrollment.last_step_id, 'progress': progress,
            'pending': pending.get(enrollment.id, 0),
            'deadlines': sorted(deadlines, key=lambda d: d['due_at'])[:3], 'available': enrollment.course.is_published})
    bookmarks = CourseBookmark.objects.filter(user=request.user, course__is_published=True).select_related('course')
    return JsonResponse({'enrollments': result, 'bookmarks': [{'course_id': b.course_id, 'title': b.course.title, 'kind': b.kind} for b in bookmarks]})
