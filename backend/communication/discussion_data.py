from accounts.identity import display_name, role_label
from common import ApiError
from .services import teacher_ids
from .presentation import comment_content


def discussion_page(discussion, user, manager, page, focus=None):
    """Page by original question, keeping every reply with its root question."""
    try:
        page = int(page)
    except (ValueError, TypeError):
        raise ApiError('Неверная страница обсуждения')
    if page < 1:
        raise ApiError('Неверная страница обсуждения')
    links = list(discussion.comments.order_by('id').values('id', 'parent_id', 'is_pinned'))
    parents = {c['id']: c['parent_id'] for c in links}
    root_ids = {}
    for c in links:
        path, seen, current = [], set(), c['id']
        while current not in root_ids and current in parents and current not in seen:
            path.append(current)
            seen.add(current)
            parent = parents[current]
            if parent is None or parent not in parents:
                break
            current = parent
        root = root_ids.get(current, current)
        for comment_id in path:
            root_ids[comment_id] = root
    roots = [c for c in links if root_ids[c['id']] == c['id']]
    roots.sort(key=lambda c: (not c['is_pinned'], -c['id']))
    page_size = 20
    selected = roots[(page - 1) * page_size:page * page_size]
    if focus and page == 1:
        try:
            focus_root = root_ids.get(int(focus))
        except (TypeError, ValueError):
            focus_root = None
        if focus_root and all(c['id'] != focus_root for c in selected):
            selected += [c for c in roots if c['id'] == focus_root]
    selected_ids = {c['id'] for c in selected}
    comment_ids = [c['id'] for c in links if root_ids[c['id']] in selected_ids]
    teachers = teacher_ids(discussion.run)
    items = {}
    for c in discussion.comments.filter(id__in=comment_ids).select_related('author').order_by('id'):
        items[c.id] = {
            **comment_content(c, discussion.run.course_id, redacted=c.is_hidden and not manager),
            'author_id': c.author_id, 'author': (display_name(c.author)) if c.author else 'Удалённый пользователь',
            'is_teacher': c.is_staff_reply or c.author_id in teachers, 'staff_at_creation': c.is_staff_reply, 'is_resolved': c.is_resolved, 'author_role_label': role_label(c.author, teaching=c.is_staff_reply or c.author_id in teachers),
            'parent_id': c.parent_id, 'is_hidden': c.is_hidden, 'is_pinned': c.is_pinned,
            'created_at': c.created_at, 'can_edit': c.author_id == user.id,
        }
    threads = [{'root': items[c['id']], 'replies': [items[v['id']] for v in links if v['id'] in items and v['id'] != c['id'] and root_ids[v['id']] == c['id']]}
               for c in selected if c['id'] in items]
    for thread in threads:
        public = [v for v in [thread['root'], *thread['replies']] if not v['is_hidden']]
        teacher_at = max((v['created_at'] for v in public if v['staff_at_creation']), default=None)
        author = thread['root']['author_id']
        student_at = max((v['created_at'] for v in public if v['author_id'] == author and not v['staff_at_creation']), default=thread['root']['created_at'])
        thread['root']['question_state'] = 'resolved' if thread['root']['is_resolved'] else 'answered' if teacher_at and teacher_at >= student_at else 'waiting'
    return {
        'threads': threads,
        # Keep the existing field for clients that still consume flat comments.
        'comments': [comment for thread in threads for comment in [thread['root'], *thread['replies']]],
        'total_threads': len(roots), 'next_page': page + 1 if page * page_size < len(roots) else None,
    }
