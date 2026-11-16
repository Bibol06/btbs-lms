"""One JSON object per log line, so Docker/journald/any log collector can parse it."""
import json
import logging
from datetime import datetime, timezone

# Attributes every LogRecord has; anything else came from `extra=` and is included.
_STANDARD = set(vars(logging.LogRecord('', 0, '', 0, '', (), None))) | {'message', 'asctime'}
# Never write these even if a caller passes them in `extra=`.
_REDACT = {'password', 'token', 'secret', 'authorization', 'cookie', 'request'}


class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            'time': datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec='milliseconds'),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        for key, value in vars(record).items():
            if key in _STANDARD or key.startswith('_'):
                continue
            entry[key] = '[redacted]' if key.lower() in _REDACT else value
        if record.exc_info:
            entry['exception'] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)
