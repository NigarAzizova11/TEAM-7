FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Root olmayan istifadəçi
RUN useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser . .
USER appuser

EXPOSE 8000

# Miqrasiyalar konteyner başlayanda tətbiq olunur; sonra API (tək worker: simulyator dövrü bir dəfə işləsin)
# Render PORT verir; yoxdursa 8000. bootstrap boş bazanı AYNA marşrutları ilə doldurur (artıq doludursa keçir; xəta olsa belə API qalxır)
CMD ["sh", "-c", "alembic upgrade head && (python -m app.cli bootstrap || true) && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
