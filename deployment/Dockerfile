FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Exact versions with hashes (backend/lock_requirements.py); pip refuses any other file.
COPY backend/requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY backend/ ./
RUN useradd --uid 10001 --create-home lms
USER lms
EXPOSE 8000
# Gunicorn reads backend/gunicorn.conf.py: gthread workers (one per CPU by default), trusted
# Nginx proxy, client IP taken from the right-most X-Forwarded-For entry (config/proxy_wsgi.py).
CMD ["gunicorn"]
