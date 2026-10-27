FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-writer fonts-dejavu-core fonts-liberation && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py postgres_sql.py postgres_rehearsal.py teacher_schedule_digest.py memo_documents.py /app/
RUN python -c "import memo_documents; print('Memo document module OK')"
COPY templates/ /app/templates/
COPY static/ /app/static/
COPY scripts/ /app/scripts/
RUN test -s /app/static/edupilot-logo-header.png && \
    test -s /app/static/edupilot-180.png && \
    test -s /app/static/edupilot-192.png && \
    test -s /app/static/edupilot-512.png && \
    test -s /app/static/edupilot-maskable-512.png

RUN groupadd --gid 10001 edupilot && useradd --uid 10001 --gid 10001 --shell /usr/sbin/nologin edupilot
USER 10001:10001

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=35s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["gunicorn","app:app","--bind","0.0.0.0:8000","--workers","1","--threads","4","--timeout","120","--access-logfile","-","--error-logfile","-"]
