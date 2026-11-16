"""Prepared, field-scoped translations. Course language and authored evidence take priority."""
import json
import re
from functools import lru_cache
from pathlib import Path

TEXT_FIELDS = frozenset({'title', 'description', 'content', 'body', 'statement', 'category', 'course', 'course__title', 'assignment', 'run', 'lesson', 'module', 'step', 'label', 'options'})
ORIGINAL_FIELDS = frozenset({'text_answer', 'feedback', 'comment', 'note', 'bio', 'organization', 'city', 'code', 'starter_code', 'stdin', 'expected', 'file_name', 'file_url', 'url', 'target', 'display_name', 'username', 'student', 'teacher', 'author', 'reviewer'})
TERMS = ('BTBS', 'Python', 'Java', 'JavaScript', 'TypeScript', 'Django', 'React', 'WebAssembly', 'PostgreSQL', 'API', 'HTTP', 'HTTPS', 'HTML', 'CSS', 'SQL', 'CSV', 'PDF', 'DOCX', 'PPTX', 'JPG', 'PNG', 'UTF-8', 'C++', 'sum', 'input', 'print', 'True', 'False', 'None')


def text_key(value):
    return ' '.join(value.split())


@lru_cache(maxsize=1)
def content_catalog():
    return json.loads((Path(__file__).parent / 'locales' / 'content.json').read_text(encoding='utf-8'))


def safe_variants(source):
    variants = content_catalog().get(text_key(source))
    if not variants:
        return None
    protected = [term for term in TERMS if re.search(r'(?<![\w])' + re.escape(term) + r'(?![\w])', source)]
    protected += re.findall(r'`[^`]+`|https?://\S+|\b[A-Z][A-Z0-9_]{1,}\b|\b\w+\([^()\n]*\)', source)
    approved = {language: value for language, value in variants.items() if all(token in value for token in protected)}
    return approved or None


def course_from_request(request):
    if request is None:
        return None
    match = re.search(r'/courses/(\d+)(?:/|$)', request.path)
    if match:
        return int(match[1])
    if request.GET.get('course_id', '').isdigit():
        return int(request.GET['course_id'])
    routes = [
        (r'/courses/runs/(\d+)', 'courses', 'CourseRun', 'course_id'),
        (r'/workspace/reviews/(\d+)', 'assessment', 'Submission', 'assignment__course_id'),
        (r'/assignments/(\d+)', 'assessment', 'Assignment', 'course_id'),
        (r'/quizzes/(\d+)', 'assessment', 'Quiz', 'course_id'),
        (r'/attempts/(\d+)', 'assessment', 'QuizAttempt', 'quiz__course_id'),
        (r'/lessons/(\d+)', 'learning', 'Lesson', 'course_id'),
        (r'/learning/steps/(\d+)', 'learning', 'Step', 'lesson__course_id'),
        (r'/problems/(\d+)', 'codejudge', 'CodeProblem', 'course_id'),
    ]
    from django.apps import apps
    for pattern, app, model, field in routes:
        match = re.search(pattern, request.path)
        if match:
            return apps.get_model(app, model).objects.filter(pk=match[1]).values_list(field, flat=True).first()
    return None


def attach_content_translations(data, request=None, course_id=None):
    """Variants belong to their exact object/field; source values and indices stay intact."""
    from courses.models import Course
    root_course = course_id or course_from_request(request)
    ids, titles = ({root_course} if root_course else set()), set()
    def identify(value, inherited=None, collection=''):
        if 'content_language' in value and isinstance(value.get('id'), int):
            return value['id']
        if isinstance(value.get('course_id'), int):
            return value['course_id']
        if collection in {'courses', 'teaching_courses'} and isinstance(value.get('id'), int):
            return value['id']
        target = value.get('target', '')
        if isinstance(target, str):
            match = re.search(r'(?:[?#&])course(?:_id)?=(\d+)', target)
            if match:
                return int(match[1])
        return inherited
    def collect(value, inherited=None, collection=''):
        if isinstance(value, dict):
            current = identify(value, inherited, collection)
            if current:
                ids.add(current)
            if isinstance(value.get('course'), str):
                titles.add(value['course'])
            for key, child in value.items():
                collect(child, current, key)
        elif isinstance(value, list):
            for child in value:
                collect(child, inherited, collection)
    collect(data, root_course)
    from django.db.models import Q
    rows = list(Course.objects.filter(Q(id__in=ids) | Q(title__in=titles)).values('id', 'title', 'content_language', 'content_translation'))
    policies = {row['id']: {'language': row['content_language'], 'mode': row['content_translation']} for row in rows}
    by_title = {}
    for row in rows:
        by_title.setdefault(row['title'], []).append(row['id'])
    def visit(value, inherited=None, collection='', personal=False):
        if isinstance(value, list):
            for child in value:
                visit(child, inherited, collection, personal)
            return
        if not isinstance(value, dict):
            return
        current = identify(value, inherited, collection)
        if not current and isinstance(value.get('course'), str) and len(by_title.get(value['course'], [])) == 1:
            current = by_title[value['course']][0]
        policy = policies.get(current, {'language': 'other', 'mode': 'original'})
        private = personal or collection in {'messages', 'comments', 'replies', 'feedback', 'notes', 'reviews', 'submissions'}
        if collection == 'questions' and ('student' in value or (request is not None and '/communication/' in request.path)):
            private = True
        # Authored messages use the same rule regardless of their collection name.
        # Only server-tagged discussion and lesson-feedback DTOs use prepared variants;
        # this never opts private messages or submitted evidence into translation.
        protected_context = personal or collection in {'messages', 'feedback', 'reviews', 'submissions'}
        lesson_feedback = value.get('_content_kind') == 'lesson_feedback' and not protected_context
        if (value.get('_content_kind') == 'discussion_comment' or lesson_feedback) and not protected_context:
            private = bool(value.get('is_redacted'))
        value.pop('_text', None)
        localized = {}
        for key, child in list(value.items()):
            if key.startswith('_'):
                continue
            standard_run = (key == 'run' or (key == 'title' and value.get('kind') == 'self_paced')) and child == 'Самостоятельное обучение'
            if standard_run:
                localized[key] = safe_variants(child)
            display_field = (key in TEXT_FIELDS and key not in ORIGINAL_FIELDS) or (lesson_feedback and key == 'note')
            if display_field and not private and policy['mode'] == 'localized':
                if isinstance(child, str):
                    variants = safe_variants(child)
                    if variants:
                        localized[key] = variants
                elif key == 'options' and isinstance(child, list):
                    variants = [safe_variants(item) if isinstance(item, str) else None for item in child]
                    if any(variants):
                        localized[key] = variants
            visit(child, current, key, private)
        if localized:
            value['_text'] = localized
    visit(data, root_course)
    if root_course in policies and isinstance(data, dict):
        data['_course_policy'] = policies[root_course]
    return data


def content_text(source, language='ru', course=None):
    if not isinstance(source, str) or course is None or course.content_translation != 'localized':
        return source
    return (safe_variants(source) or {}).get(language, source)


class ContentTranslationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith('/api/') or response.status_code >= 400 or response.streaming or 'application/json' not in response.get('Content-Type', ''):
            return response
        try:
            payload = json.loads(response.content)
        except (ValueError, UnicodeDecodeError):
            return response
        if not isinstance(payload, dict):
            return response
        attach_content_translations(payload, request)
        response.content = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        response['Cache-Control'] = 'private, no-store'
        if 'Content-Length' in response:
            response['Content-Length'] = len(response.content)
        return response
