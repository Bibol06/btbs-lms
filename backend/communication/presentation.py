"""The same discussion text contract for previews, queues and lesson threads."""


def comment_content(comment, course_id, *, redacted=False):
    return {
        'id': comment.id,
        '_content_kind': 'discussion_comment',
        'course_id': course_id,
        'body': 'Комментарий скрыт модератором' if redacted else comment.body,
        'is_redacted': redacted,
    }
