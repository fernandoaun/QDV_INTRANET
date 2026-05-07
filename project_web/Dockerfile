# Imagen opcional para VPS, Fly.io, u otro host con Docker.
# También hay Dockerfile en la raíz del repo (mismo contenido) para `docker build .` / Render.
# Build (desde la raíz del repo):
#   docker build -f project_web/Dockerfile -t qdv-web .
#   o: docker build -t qdv-web .
# Run (pasá SECRET_KEY y DATABASE_URL de PostgreSQL):
#   docker run -e FLASK_ENV=production -e SECRET_KEY=... -e DATABASE_URL=postgresql://... -e PORT=8000 -p 8000:8000 qdv-web
#
# DATABASE_URL debe ser compatible con SQLAlchemy + psycopg2 (el código normaliza postgres:// y postgresql://).

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
