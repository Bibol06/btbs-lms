FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements-share.txt backend/requirements-cache.txt ./
RUN pip install --no-cache-dir -r requirements-share.txt -r requirements-cache.txt
COPY backend/ ./
RUN useradd --uid 10001 --create-home lms
USER lms
EXPOSE 8000
# Port 8000 is reachable only from Nginx inside the compose network, so the proxy is trusted.
# trusted-proxy-count=1 takes the client IP that Nginx appended (spoofed left-hand values are ignored).
CMD ["waitress-serve", "--listen=0.0.0.0:8000", "--threads=8", \
     "--trusted-proxy=*", "--trusted-proxy-count=1", \
     "--trusted-proxy-headers=x-forwarded-for x-forwarded-proto", \
     "--clear-untrusted-proxy-headers", "--no-expose-tracebacks", \
     "config.wsgi:application"]
