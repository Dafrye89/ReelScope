FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 reelscope \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/reelscope reelscope

WORKDIR /app

COPY requirements.txt requirements-server.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements-server.txt

COPY --chown=10001:10001 . /app
RUN mkdir -p /data \
    && chown 10001:10001 /data

USER 10001:10001
EXPOSE 8000

CMD ["gunicorn", "--bind=0.0.0.0:8000", "--workers=1", "--threads=8", "--timeout=0", "--graceful-timeout=120", "--access-logfile=-", "--error-logfile=-", "web_app:app"]
