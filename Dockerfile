FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

RUN addgroup --system reposcout && adduser --system --ingroup reposcout reposcout

COPY requirements/runtime.txt requirements/runtime.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements/runtime.txt

COPY main.py ./main.py
COPY src ./src
COPY static ./static

RUN mkdir -p /app/.cache/repository_documents \
    && chown -R reposcout:reposcout /app

USER reposcout

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]

CMD ["python", "main.py"]
