# Deploy en Render (paso a paso simple)

Este proyecto ya viene preparado para Render con `render.yaml`.

## 1) Subir el código a GitHub

1. Creá un repo en GitHub (si todavía no existe).
2. Subí esta carpeta completa.

## 2) Crear en Render usando Blueprint

1. Entrá a `https://dashboard.render.com`.
2. Click en **New +**.
3. Elegí **Blueprint**.
4. Conectá GitHub y seleccioná este repo.
5. Render detecta `render.yaml` y crea:
   - un servicio web
   - una base PostgreSQL

## 3) Variable obligatoria (SECRET_KEY)

Antes de finalizar el primer deploy:

1. En Render, abrí el servicio web creado.
2. Entrá a **Environment**.
3. Agregá:
   - Key: `SECRET_KEY`
   - Value: una clave larga aleatoria

Para generar una clave en tu PC:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## 4) Qué ya está configurado en este proyecto

- `FLASK_ENV=production`
- `DATABASE_URL` conectada a la base de Render
- `preDeployCommand`: `python -m alembic upgrade head` (migraciones automáticas)
- `startCommand`: `gunicorn ... wsgi:app`

No hace falta configurar eso manualmente si usás Blueprint.

## 5) Dominio propio + HTTPS

1. En Render, servicio web -> **Settings** -> **Custom Domains**.
2. Agregá tu dominio (`tudominio.com`) y opcional `www.tudominio.com`.
3. Render te muestra qué registros DNS crear.
4. En el proveedor del dominio (Namecheap, etc.) cargá esos DNS exactamente.
5. Esperá propagación.
6. Render activa SSL automático (https) cuando verifica el DNS.

## 6) Si el deploy falla

Revisá en Render -> **Logs**:

- Error de `SECRET_KEY` faltante: agregarla en Environment.
- Error de DB/migración: verificar que PostgreSQL esté creada y enlazada.
- Error de imports: revisar que el deploy use la rama correcta.

