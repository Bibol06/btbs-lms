"""Translations for system captions. Never translate authored course or user content."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent / 'locales' / 'messages.json').read_text(encoding='utf-8'))


def request_language(request):
    explicit = request.GET.get('language', '')
    if explicit in {'kk', 'ru', 'en'}:
        return explicit
    preferred = getattr(request.user, 'preferred_language', '')
    return preferred if preferred in {'kk', 'ru', 'en'} else 'ru'


def translate(source, language='ru'):
    if source is None or language == 'ru':
        return source
    key = ' '.join(str(source).split())
    variants = catalog().get(key)
    if variants:
        return variants[0 if language == 'kk' else 1]
    return source


def system_caption(code, language):
    captions = {
        'recent': 'Активность за 5 минут', 'ended': 'Вышел из аккаунта',
        'expired': 'Срок сессии истёк', 'idle': 'Свежая активность не зафиксирована',
        'step_view': 'Открыл учебный шаг', 'step_completed': 'Отметил материал изученным',
        'step_reopened': 'Снял отметку изучения', 'assignment_submitted': 'Отправил письменную работу',
        'assignment_reviewed': 'Проверил работу', 'assignment_returned': 'Вернул работу на доработку',
        'quiz_started': 'Начал тест', 'quiz_answered': 'Сохранил ответы теста',
        'quiz_finished': 'Завершил тест', 'quiz_finished_auto': 'Тест завершён системой по таймеру',
        'code_submitted': 'Отправил решение Python',
    }
    return translate(captions.get(code, code), language)
