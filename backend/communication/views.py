from accounts.identity import display_name, role_label
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from common import api, authenticated, body, text, boolean, integer, ApiError
from courses.models import Course, Enrollment
from courses.access import resolve_run, require_run, can_manage_course, can_manage_run
from learning.models import Lesson
from .models import Announcement, Conversation, Participant, Message, Discussion, Comment, Notification, NotificationPreference, AuditEvent
from .services import notify, teacher_ids, course_target, audit


KINDS = ['announcement', 'message', 'discussion', 'submission', 'grade', 'material', 'deadline']


@require_http_methods(['GET', 'POST'])
@api
def announcements(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    run = resolve_run(request, course)
    require_run(request, run)
    manage = can_manage_run(request.user, run)
    if request.method == 'POST':
        require_run(request, run, manage=True)
        data = body(request)
        all_course = boolean(data, 'all_course', False)
        if all_course and not can_manage_course(request.user, course):
            raise ApiError('Публиковать новости всему курсу может команда курса', 403)
        with transaction.atomic():
            item = Announcement.objects.create(course=course, run=None if all_course else run, author=request.user,
                title=text(data, 'title', 200, True), body=text(data, 'body', 20000, True),
                is_published=boolean(data, 'is_published', True))
            publish_announcement(item)
        return JsonResponse({'id': item.id}, status=201)
    qs = course.announcements.filter(Q(run=run) | Q(run__isnull=True)).select_related('author').order_by('-created_at')
    if not manage:
        qs = qs.filter(is_published=True)
    return JsonResponse({'announcements': [{'id': a.id, 'title': a.title, 'body': a.body,
        'author': display_name(a.author), 'author_role_label': role_label(a.author, teaching=True), 'created_at': a.created_at,
        'is_published': a.is_published, 'all_course': a.run_id is None,
        'can_edit': can_manage_course(request.user, course) or (a.run_id == run.id and manage)} for a in qs[:200]]})


def publish_announcement(item):
    if not item.is_published or item.published_at:
        return
    item.published_at = timezone.now()
    item.save(update_fields=['published_at'])
    qs = item.course.enrollments.filter(status__in=['active', 'completed'], student__is_active=True)
    if item.run_id:
        qs = qs.filter(run=item.run)
    notify(f'announcement:{item.id}', 'announcement', item.course, set(qs.values_list('student_id', flat=True)) - {item.author_id},
        'Новое объявление по курсу', course_target(item.course, item.run, 'announcements'), item.run)


@require_http_methods(['PATCH'])
@api
def announcement_detail(request, announcement_id):
    authenticated(request)
    with transaction.atomic():
        item = get_object_or_404(Announcement.objects.select_for_update(), pk=announcement_id)
        if not (can_manage_course(request.user, item.course) or (item.run_id and can_manage_run(request.user, item.run))):
            raise ApiError('Нет прав на объявление', 403)
        data = body(request)
        item.title = text(data, 'title', 200, True, item.title)
        item.body = text(data, 'body', 20000, True, item.body)
        item.is_published = boolean(data, 'is_published', item.is_published)
        item.save()
        publish_announcement(item)
        audit(request.user, item.course, 'announcement.updated', {'id': item.id})
    return JsonResponse({'message': 'Объявление сохранено'})


def conversation_access(request, conversation):
    run = conversation.enrollment.run
    require_run(request, run)
    if not conversation.participants.filter(user=request.user).exists():
        raise ApiError('Вы не участник этого диалога', 403)


@require_http_methods(['GET', 'POST'])
@api
def conversations(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    run = resolve_run(request, course)
    require_run(request, run)
    if request.method == 'POST':
        data = body(request)
        if can_manage_run(request.user, run):
            enrollment = get_object_or_404(Enrollment, pk=integer(data, 'enrollment_id', 1, 2**63-1), run=run)
        else:
            enrollment = get_object_or_404(Enrollment, run=run, student=request.user)
        with transaction.atomic():
            conversation, created = Conversation.objects.get_or_create(enrollment=enrollment)
            if created:
                ids = teacher_ids(run) | {enrollment.student_id}
                Participant.objects.bulk_create([Participant(conversation=conversation, user_id=i) for i in ids])
            elif can_manage_course(request.user, course) and not conversation.participants.filter(user=request.user).exists():
                Participant.objects.create(conversation=conversation, user=request.user)
                audit(request.user, course, 'conversation.participant_added', {'conversation_id': conversation.id, 'user_id': request.user.id})
        conversation_access(request, conversation)
        return JsonResponse({'id': conversation.id}, status=201)
    qs = Conversation.objects.filter(enrollment__run=run, participants__user=request.user).select_related('enrollment__student').order_by('-id')
    result = []
    for c in qs:
        read = c.participants.get(user=request.user).read_at
        unread = c.messages.exclude(author=request.user)
        if read:
            unread = unread.filter(created_at__gt=read)
        result.append({'id': c.id, 'student': display_name(c.enrollment.student), 'student_role_label': role_label(c.enrollment.student), 'unread': unread.count()})
    students = [{'id': e.id, 'student__username': e.student.username, 'student': display_name(e.student), 'role_label': role_label(e.student)} for e in run.enrollments.select_related('student')] if can_manage_run(request.user, run) else []
    return JsonResponse({'conversations': result, 'students': students})


@require_http_methods(['GET', 'POST', 'PATCH'])
@api
def messages(request, conversation_id):
    conversation = get_object_or_404(Conversation.objects.select_related('enrollment__run__course'), pk=conversation_id)
    conversation_access(request, conversation)
    run = conversation.enrollment.run
    if request.method == 'POST':
        with transaction.atomic():
            message = Message.objects.create(conversation=conversation, author=request.user, body=text(body(request), 'body', 10000, True))
            recipients = set(conversation.participants.exclude(user=request.user).values_list('user_id', flat=True))
            notify(f'message:{message.id}', 'message', run.course, recipients, 'Новое личное сообщение по курсу', course_target(run.course, run, 'messages'), run)
        return JsonResponse({'id': message.id}, status=201)
    if request.method == 'PATCH':
        Participant.objects.filter(conversation=conversation, user=request.user).update(read_at=timezone.now())
        return JsonResponse({'message': 'Прочитано'})
    try:
        before = int(request.GET.get('before', 2**63-1))
    except ValueError:
        raise ApiError('Неверный курсор')
    message_teachers = teacher_ids(run)
    values = list(conversation.messages.filter(pk__lt=before).select_related('author').order_by('-id')[:50])
    return JsonResponse({'messages': [{'id': m.id, 'author': display_name(m.author), 'author_role_label': role_label(m.author, teaching=m.author_id in message_teachers), 'mine': m.author_id == request.user.id, 'body': m.body, 'created_at': m.created_at} for m in reversed(values)],
                         'next_before': values[-1].id if len(values) == 50 else None})


@require_POST
@api
def add_participant(request, conversation_id):
    c = get_object_or_404(Conversation.objects.select_related('enrollment__run__course'), pk=conversation_id)
    authenticated(request)
    run = c.enrollment.run
    if not can_manage_course(request.user, run.course):
        raise ApiError('Добавить преподавателя может команда курса', 403)
    user = get_object_or_404(get_user_model(), username=text(body(request), 'username', 150, True), is_active=True)
    if user.id not in teacher_ids(run):
        raise ApiError('Пользователь не назначен преподавателем этого запуска')
    with transaction.atomic():
        Participant.objects.get_or_create(conversation=c, user=user)
        audit(request.user, run.course, 'conversation.participant_added', {'conversation_id': c.id, 'user_id': user.id})
    return JsonResponse({'message': 'Участник добавлен'})


@require_http_methods(['GET', 'POST', 'PATCH'])
@api
def discussion(request, lesson_id):
    lesson = get_object_or_404(Lesson.objects.select_related('course'), pk=lesson_id)
    run = resolve_run(request, lesson.course)
    require_run(request, run)
    from learning.services import require_lesson_visible
    require_lesson_visible(request.user, lesson, run)
    manager = can_manage_run(request.user, run)
    thread, _ = Discussion.objects.get_or_create(lesson=lesson, run=run)
    if request.method == 'PATCH':
        if not manager:
            raise ApiError('Только преподаватель может закрыть обсуждение', 403)
        thread.is_closed = boolean(body(request), 'is_closed', False)
        thread.save(update_fields=['is_closed'])
    if request.method == 'POST':
        if thread.is_closed:
            raise ApiError('Обсуждение закрыто')
        data = body(request)
        parent = get_object_or_404(Comment, pk=integer(data, 'parent_id', 1, 2**63-1), discussion=thread, is_hidden=False) if data.get('parent_id') else None
        with transaction.atomic():
            comment = Comment.objects.create(discussion=thread, author=request.user, parent=parent, is_staff_reply=manager, body=text(data, 'body', 10000, True))
            recipients = {parent.author_id} if parent and parent.author_id else teacher_ids(run)
            recipients.discard(request.user.id)
            notify(f'comment:{comment.id}', 'discussion', lesson.course, recipients, 'Новый ответ в обсуждении урока', course_target(lesson.course, run, 'lessons', lesson.id), run)
        return JsonResponse({'id': comment.id}, status=201)
    from .discussion_data import discussion_page
    return JsonResponse({'is_closed': thread.is_closed, 'can_moderate': manager,
                         **discussion_page(thread, request.user, manager, request.GET.get('page', '1'), request.GET.get('focus'))})


@require_http_methods(['PATCH'])
@api
def comment_detail(request, comment_id):
    c = get_object_or_404(Comment.objects.select_related('discussion__run__course'), pk=comment_id)
    run = c.discussion.run
    require_run(request, run)
    manager = can_manage_run(request.user, run)
    data = body(request)
    with transaction.atomic():
        if 'is_resolved' in data:
            if c.parent_id or not (manager or c.author_id == request.user.id):
                raise ApiError('Статус меняет автор вопроса или преподаватель', 403)
            c.is_resolved = boolean(data, 'is_resolved')
            audit(request.user, run.course, 'question.status_changed', {'id': c.id, 'resolved': c.is_resolved})
        if 'body' in data:
            if c.author_id != request.user.id or c.is_hidden:
                raise ApiError('Нельзя редактировать этот комментарий', 403)
            c.body = text(data, 'body', 10000, True)
        for key in ['is_hidden', 'is_pinned']:
            if key in data:
                if not manager:
                    raise ApiError('Нет прав модератора', 403)
                setattr(c, key, boolean(data, key))
                audit(request.user, run.course, 'comment.moderated', {'id': c.id, key: getattr(c, key)})
        c.save()
    return JsonResponse({'message': 'Комментарий обновлён'})


def accessible_notifications(user):
    from courses.models import CourseRun
    from courses.access import is_platform_admin
    qs = Notification.objects.filter(recipient=user).select_related('event__course').order_by('-event__created_at', '-id')
    if is_platform_admin(user):
        return qs
    managed_courses = Course.objects.filter(Q(teacher=user) | Q(team__user=user)).values('id')
    managed_runs = CourseRun.objects.filter(Q(course_id__in=managed_courses) | Q(teachers=user)).values('id')
    memberships = Enrollment.objects.filter(student=user, status__in=['active', 'completed'], course__is_published=True)
    global_access = Q(event__run__isnull=True) & (Q(event__course_id__in=managed_courses) | Q(event__course_id__in=memberships.values('course_id')))
    run_access = Q(event__run__isnull=False) & (Q(event__run_id__in=managed_runs) | Q(event__run_id__in=memberships.values('run_id')))
    return qs.filter(global_access | run_access)


@require_http_methods(['GET', 'PATCH'])
@api
def notifications(request):
    authenticated(request)
    if request.method == 'PATCH':
        data = body(request)
        qs = Notification.objects.filter(recipient=request.user)
        if not boolean(data, 'all', False):
            qs = qs.filter(pk=integer(data, 'id', 1, 2**63-1))
        qs.filter(read_at__isnull=True).update(read_at=timezone.now())
        return JsonResponse({'message': 'Отмечено прочитанным'})
    rows = accessible_notifications(request.user)
    try:
        page = max(1, int(request.GET.get('page', 1)))
    except ValueError:
        raise ApiError('Неверная страница')
    return JsonResponse({'unread': rows.filter(read_at__isnull=True).count(), 'total': rows.count(), 'page': page,
        'notifications': [{'id': n.id, 'kind': n.event.kind, 'title': n.event.title, 'course': n.event.course.title,
                          'target': n.event.target, 'created_at': n.event.created_at, 'read_at': n.read_at} for n in rows[(page-1)*30:page*30]]})


@require_http_methods(['GET', 'PUT'])
@api
def preferences(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    require_run(request, resolve_run(request, course))
    pref, _ = NotificationPreference.objects.get_or_create(course=course, user=request.user)
    if request.method == 'PUT':
        values = body(request).get('muted_kinds')
        if not isinstance(values, list) or any(v not in KINDS for v in values):
            raise ApiError('Неизвестный тип уведомления')
        pref.muted_kinds = list(set(values))
        pref.save(update_fields=['muted_kinds'])
    return JsonResponse({'muted_kinds': pref.muted_kinds, 'kinds': KINDS})


@require_GET
@api
def audit_log(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    authenticated(request)
    if not can_manage_course(request.user, course):
        raise ApiError('Доступ к аудиту только у команды курса', 403)
    return JsonResponse({'events': [{'action': e.action, 'context': e.context, 'created_at': e.created_at, 'actor__username': e.actor.username if e.actor else '', 'actor': display_name(e.actor), 'actor_role_label': role_label(e.actor)} for e in AuditEvent.objects.filter(course=course).select_related('actor').order_by('-id')[:100]]})
