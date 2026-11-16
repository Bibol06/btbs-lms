import json
import subprocess
import sys
import os
from pathlib import Path
from django.conf import settings
from common import ApiError


def runtime_path():
    return Path(settings.BASE_DIR).parent / '.local/runtime/python-3.12.0.wasm'


def run_python(code, cases):
    if not runtime_path().is_file():
        raise ApiError('Среда Python не установлена. Выполните manage.py setup_code_runner.', 503)
    payload = json.dumps({'runtime': str(runtime_path()), 'code': code, 'cases': cases}, ensure_ascii=False).encode('utf-8')
    try:
        result = subprocess.run([sys.executable, '-m', 'codejudge.worker'], input=payload, capture_output=True,
            timeout=20, cwd=settings.BASE_DIR, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except subprocess.TimeoutExpired:
        return [{'status': 'time_limit', 'stdout': '', 'stderr': 'Превышено время выполнения'} for _ in cases]
    try:
        output = json.loads(result.stdout)
    except (ValueError, UnicodeDecodeError):
        raise ApiError('Изолированная среда временно недоступна', 503)
    if 'error' in output:
        raise ApiError(output['error'], 503)
    return output['results']
