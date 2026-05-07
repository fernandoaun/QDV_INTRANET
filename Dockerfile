# Misma imagen que project_web/Dockerfile; en la raíz para hosts que ejecutan
# `docker build .` desde el repo (p. ej. Render si el servicio está en modo Docker).
# Contexto de build: raíz del repositorio (carpeta que contiene project_web/).
#
# Web (Gunicorn): CMD por defecto abajo.
# Cron en Render: definí Start Command = python -m flask --app run send-deadline-reminders
# para no levantar Gunicorn.

FROM python:3.12-slim-bookworm

WORKDIR /app/project_web

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production

COPY project_web/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY project_web/ .

EXPOSE 8000
ENV PORT=8000

# Migraciones en runtime: necesitan DATABASE_URL (no en la capa de build).
CMD sh -c "python -m alembic upgrade head && exec gunicorn -w 2 -b 0.0.0.0:${PORT} wsgi:app"
