import csv
import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from accounts.identity import identity_data
from assessment.models import Quiz, Submission, QuizAttempt
from common import api, authenticated, body, integer, query_integer, ApiError
from courses.access import require_run
from courses.models import CourseRun
from learning.models import Lesson
from .models import ActivityEvent, AttendanceDay, SessionRecord, LessonEvaluation
from .services import context, period, meta, day, dashboard_data
from .tracking import touch_session, record, user_role
from accounts.permissions import is_system_admin


def require_admin(request):
    authenticated(request)
    if not is_system_admin(request.user):
        raise ApiError('История входов и устройств доступна только администратору', 403)


def people_filter(request, qs):
    for term in request.GET.get('search', '').strip()[:150].split():
        qs = qs.filter(Q(first_name__icontains=term) | Q(last_name__icontains=term) | Q(username__icontains=term))
    role = request.GET.get('person_role', 'all')
    admins = Q(is_superuser=True) | Q(role='admin')
    teachers = Q(role='teacher') | Q(courses_taught__isnull=False) | Q(course_memberships__isnull=False) | Q(teaching_runs__isnull=False)
    if role == 'admin':
        qs = qs.filter(admins)
    elif role == 'teacher':
        qs = qs.filter(teachers).exclude(admins)
    elif role == 'student':
        qs = qs.exclude(admins | teachers)
    elif role != 'all':
        raise ApiError('Неизвестный фильтр роли')
    if request.GET.get('person_id'):
        qs = qs.filter(id=query_integer(request, 'person_id', 1, 2**63-1))
    return qs.distinct()


@require_GET
@api
def dashboard(request):
    return JsonResponse(dashboard_data(request))


@require_POST
@api
def presence(request):
    authenticated(request)
    # Server timestamps and authenticated account only; client cannot report others.
    touch_session(request)
    bucket = int(timezone.now().timestamp())//300
    record(request.user, 'platform_active', dedupe=f'presence:{request.user.id}:{bucket}')
    return JsonResponse({'message': 'Активность отмечена'})


def attendance_data(request):
    role, runs, enrollments, _, dates = context(request)
    page = query_integer(request, 'page', 1, 100000, 1)
    coverage = meta(dates)['coverage_start']
    rows = []
    if role == 'teacher':
        total = len(enrollments)
        chosen = enrollments[(page-1)*20:page*20]
        for e in chosen:
            stamps = list(ActivityEvent.objects.filter(enrollment=e, actor_role='student', occurred_at__gte=dates['start'], occurred_at__lt=dates['end'])
                          .exclude(kind='quiz_finished_auto').values_list('occurred_at', flat=True))
            stamps += list(Submission.objects.filter(enrollment=e, submitted_at__gte=dates['start'], submitted_at__lt=dates['end']).values_list('submitted_at', flat=True))
            stamps += list(QuizAttempt.objects.filter(enrollment=e, started_at__gte=dates['start'], started_at__lt=dates['end']).values_list('started_at', flat=True))
            active_days = {day(s) for s in stamps}
            rows.append({**identity_data(e.student), 'enrollment_id': e.id, 'run': e.run.title, 'course': e.course.title,
                'days': [{'date': d, 'active': True if d in active_days else None if coverage is None or d < day(coverage) else False} for d in dates['days']],
                'active_days': len(active_days), 'last_seen_at': max(stamps, default=None), 'logins': None})
    else:
        users = people_filter(request, get_user_model().objects.all()) if role == 'admin' else get_user_model().objects.filter(pk=request.user.id)
        if role == 'admin' and any(request.GET.get(k) for k in ('course_id', 'run_id', 'enrollment_id')):
            from communication.services import teacher_ids
            people = {e.student_id for e in enrollments}
            if not request.GET.get('enrollment_id'):
                for run in runs:
                    people |= teacher_ids(run)
            users = users.filter(id__in=people)
        total = users.count()
        for user in users.order_by('last_name', 'first_name', 'id')[(page-1)*20:page*20]:
            days = {a.date: a for a in AttendanceDay.objects.filter(user=user, date__gte=dates['from'], date__lte=dates['to'])}
            rows.append({**identity_data(user, teaching=user_role(user) == 'teacher'), 'is_active': user.is_active,
                'days': [{'date': d, 'active': True if d in days else None if coverage is None or d < day(coverage) else False,
                          'logins': days[d].login_count if d in days else 0} for d in dates['days']],
                'active_days': len(days), 'logins': sum(a.login_count for a in days.values()),
                'last_seen_at': max((a.last_seen_at for a in days.values()), default=None)})
    return {**meta(dates), 'role': role, 'people': rows, 'days': dates['days'], 'total': total, 'page': page, 'next_page': page+1 if page*20 < total else None,
            'definition': 'Учебные действия в выбранных группах' if role == 'teacher' else 'Зафиксированный вход или действие на платформе; не подтверждение присутствия на очном занятии'}


@require_GET
@api
def attendance_report(request):
    return JsonResponse(attendance_data(request))


def sessions_data(request):
    require_admin(request)
    dates = period(request)
    users = people_filter(request, get_user_model().objects.all())
    qs = SessionRecord.objects.filter(user__in=users, started_at__lt=dates['end'], last_seen_at__gte=dates['start']).select_related('user')
    device = request.GET.get('device', '')
    if device:
        if device not in ('Компьютер', 'Телефон', 'Планшет', 'Не определено'):
            raise ApiError('Неизвестный тип устройства')
        qs = qs.filter(device=device)
    now = timezone.now()
    active = Q(ended_at__isnull=True, expires_at__gt=now, last_seen_at__gte=now-timedelta(minutes=5))
    state = request.GET.get('state', 'all')
    if state == 'recent':
        qs = qs.filter(active)
    elif state not in ('all', ''):
        raise ApiError('Неизвестный статус входа')
    total = qs.count()
    page = query_integer(request, 'page', 1, 100000, 1)
    sessions = []
    for s in qs.order_by('-last_seen_at', '-id')[(page-1)*20:page*20]:
        status = 'ended' if s.ended_at else 'expired' if s.expires_at <= now else 'recent' if s.last_seen_at >= now-timedelta(minutes=5) else 'idle'
        sessions.append({'id': s.id, 'person': identity_data(s.user, teaching=user_role(s.user) == 'teacher'),
            'started_at': s.started_at, 'last_seen_at': s.last_seen_at, 'ended_at': s.ended_at, 'status': status,
            'browser': s.browser, 'os': s.os, 'device': s.device, 'ip_address': s.ip_address,
            'user_agent': s.user_agent, 'entry_kind': s.entry_kind})
    return {**meta(dates), 'sessions': sessions, 'total': total, 'page': page, 'next_page': page+1 if page*20 < total else None,
            'definition': 'Устройство определено приблизительно по данным браузера. IP — адрес соединения с сервером; при прокси он может принадлежать прокси.'}


@require_GET
@api
def sessions_report(request):
    return JsonResponse(sessions_data(request))


def activity_data(request):
    require_admin(request)
    dates = period(request)
    users = people_filter(request, get_user_model().objects.all())
    events = ActivityEvent.objects.filter(user__in=users, occurred_at__gte=dates['start'], occurred_at__lt=dates['end']).exclude(kind='platform_active').select_related('user', 'run__course', 'lesson', 'step').order_by('-occurred_at', '-id')
    total = events.count()
    page = query_integer(request, 'page', 1, 100000, 1)
    return {**meta(dates), 'total': total, 'page': page, 'next_page': page+1 if page*20 < total else None,
        'events': [{'id': e.id, 'person': identity_data(e.user), 'kind': e.kind, 'actor_role': e.actor_role,
                    'occurred_at': e.occurred_at, 'course': e.run.course.title if e.run else None,
                    'run': e.run.title if e.run else None, 'lesson': e.lesson.title if e.lesson else None,
                    'step': e.step.title if e.step else None, 'target': f'/#course={e.run.course_id}&run={e.run_id}&tab=results' if e.run else None} for e in events[(page-1)*20:page*20]]}


@require_GET
@api
def activity_report(request):
    return JsonResponse(activity_data(request))


@require_http_methods(['GET', 'POST', 'DELETE'])
@api
def evaluations(request):
    authenticated(request)
    if request.method == 'GET':
        run_id = query_integer(request, 'run_id', 1, 2**63-1)
    else:
        values = body(request)
        run_id = integer(values, 'run_id', 1, 2**63-1)
    run = get_object_or_404(CourseRun.objects.select_related('course'), pk=run_id)
    require_run(request, run, manage=True)
    if request.method != 'GET':
        lesson = get_object_or_404(Lesson, pk=integer(values, 'lesson_id', 1, 2**63-1), course=run.course)
        if request.method == 'DELETE':
            LessonEvaluation.objects.filter(lesson=lesson, run=run).delete()
        else:
            pre = get_object_or_404(Quiz, pk=integer(values, 'pre_quiz_id', 1, 2**63-1), course=run.course, is_published=True)
            post = get_object_or_404(Quiz, pk=integer(values, 'post_quiz_id', 1, 2**63-1), course=run.course, is_published=True)
            if pre.pk == post.pk:
                raise ApiError('Входной и итоговый тесты должны быть разными')
            LessonEvaluation.objects.update_or_create(lesson=lesson, run=run, defaults={'pre_quiz': pre, 'post_quiz': post, 'updated_by': request.user})
    return JsonResponse({'lessons': list(run.course.lessons.filter(is_published=True).values('id', 'title')),
        'quizzes': list(run.course.quizzes.filter(is_published=True).values('id', 'title')),
        'evaluations': list(LessonEvaluation.objects.filter(run=run).values('id', 'lesson_id', 'pre_quiz_id', 'post_quiz_id'))})


@require_GET
@api
def export_report(request):
    kind = request.GET.get('kind', 'learners')
    if kind not in ('learners', 'attendance', 'sessions', 'materials', 'activity'):
        raise ApiError('Неизвестный отчёт')
    provider = sessions_data if kind == 'sessions' else activity_data if kind == 'activity' else attendance_data if kind == 'attendance' else dashboard_data
    request.GET = request.GET.copy()
    request.GET['page'] = '1'
    request.GET['lesson_page'] = '1'
    data = provider(request)
    total = data['materials']['total'] if kind == 'materials' else data['total']
    if total > 2000:
        raise ApiError('Выгрузка до 2000 записей: сузьте фильтры')
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    from localization import translate, request_language, system_caption
    from content_localization import content_text
    language = request_language(request)
    caption = lambda value: translate(value, language)
    def safe(value):
        value = '' if value is None else str(value)
        return "'"+value if value.startswith(('=', '+', '-', '@', '\t', '\r')) else value
    writer.writerow([caption('Период'), str(data['from']), str(data['to']), data['timezone'], caption('Сформировано'), str(data['as_of'])])
    headers = {'learners': ['Имя', 'Курс', 'Группа', 'Прогресс, %', 'На проверке'],
               'attendance': ['Имя', 'Роль', 'Дней с активностью', 'Входов']+[str(d) for d in data['days']] if kind == 'attendance' else [],
               'sessions': ['Имя', 'Роль', 'Начало', 'Последняя активность', 'Устройство', 'Браузер', 'ОС', 'IP', 'Статус'],
               'activity': ['Имя', 'Событие', 'Дата', 'Курс', 'Группа', 'Урок', 'Шаг'],
               'materials': ['Урок', 'Курс', 'Открыли', 'Выполнили', 'Успех первой попытки, %', 'Наблюдений', 'Пар до/после', 'До, %', 'После, %']}
    writer.writerow([caption(value) for value in headers[kind]])
    original = request.GET
    try:
        for page in range(1, (total+14)//15+1 if kind == 'materials' else (total+19)//20+1):
            request.GET = original.copy()
            request.GET['lesson_page' if kind == 'materials' else 'page'] = str(page)
            part = data if page == 1 else provider(request)
            records = part['materials']['lessons'] if kind == 'materials' else part['people'] if kind == 'attendance' else part['sessions'] if kind == 'sessions' else part['events'] if kind == 'activity' else part['learners']
            from courses.models import Course
            course_names = {row.get('course') for row in records if isinstance(row.get('course'), str)}
            by_title = {}
            for item in Course.objects.filter(title__in=course_names):
                by_title.setdefault(item.title, []).append(item)
            for row in records:
                matches = by_title.get(row.get('course'), [])
                row_course = matches[0] if len(matches) == 1 else None
                if kind == 'learners':
                    values = [row['display_name'], content_text(row['course'], language, row_course), caption(row['run']) if row['run'] == 'Самостоятельное обучение' else content_text(row['run'], language, row_course), row['progress']['percent'], row['pending']]
                elif kind == 'attendance':
                    values = [row['display_name'], caption(row['role_label']), row['active_days'], row['logins']]+[caption('Есть активность' if d['active'] else 'Нет данных' if d['active'] is None else 'Не зафиксирована') for d in row['days']]
                elif kind == 'sessions':
                    values = [row['person']['display_name'], caption(row['person']['role_label']), row['started_at'], row['last_seen_at'], caption(row['device']), caption(row['browser']), caption(row['os']), row['ip_address'], system_caption(row['status'], language)]
                elif kind == 'activity':
                    values = [row['person']['display_name'], system_caption(row['kind'], language), row['occurred_at'], *[content_text(row[key], language, row_course) for key in ['course', 'run', 'lesson', 'step']]]
                else:
                    values = [content_text(row['title'], language, row_course), content_text(row['course'], language, row_course), row['opened'], row['completed'], row['first_attempt_success'], row['attempt_samples'], row['comparison']['pairs'], row['comparison']['before'], row['comparison']['after']]
                writer.writerow([safe(v) for v in values])
    finally:
        request.GET = original
    result = HttpResponse('\ufeff'+buffer.getvalue(), content_type='text/csv; charset=utf-8')
    result['Content-Disposition'] = f'attachment; filename="analytics-{kind}.csv"'
    return result
