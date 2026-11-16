FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements-share.txt backend/requirements-cache.txt backend/requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-share.txt -r requirements-cache.txt -r requirements-server.txt
COPY backend/ ./
RUN useradd --uid 10001 --create-home lms
USER lms
EXPOSE 8000
# Gunicorn reads backend/gunicorn.conf.py: gthread workers (one per CPU by default), trusted
# Nginx proxy, client IP taken from the right-most X-Forwarded-For entry (config/proxy_wsgi.py).
CMD ["gunicorn"]
