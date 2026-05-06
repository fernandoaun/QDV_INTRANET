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

## 6) PDFs del erlenmeyer y archivos subidos (importante)

Los PDFs de referencia analítica (ícono erlenmeyer) y los adjuntos de reactivos de laboratorio **no** van a la base de datos: el archivo está en disco y en la BD solo hay el nombre interno (`app_uploaded_documents`, `laboratory_reagents`).

Por defecto la app guardaba bajo `instance/uploads/` dentro del proyecto. **En Render el filesystem del servicio web es efímero**: cada nuevo deploy **borra** esa carpeta. La base PostgreSQL **sí** se conserva, entonces los registros siguen diciendo que hay PDF pero el archivo **ya no existe** → erlenmeyer en rojo / 404.

**Con el Blueprint actual (`render.yaml`)** ya viene un **disco persistente** montado en `/var/qdv/uploads` y la variable `APP_UPLOAD_ROOT` apuntando ahí, para que los PDFs **no se pierdan** al actualizar el sitio.

Si tu servicio se creó **antes** de eso y no tiene disco: en el dashboard, **Disks** → agregar Persistent Disk con el mismo montaje y `APP_UPLOAD_ROOT=/var/qdv/uploads`, o **apply changes** al Blueprint desde el repo actualizado.

**Solución estable (manual / otro host)**

1. En el servicio web de Render: **Disks** → crear un **Persistent Disk** (ej. montaje `/var/qdv/uploads`).
2. En **Environment** agregar:
   - `APP_UPLOAD_ROOT` = la ruta de montaje del disco (ej. `/var/qdv/uploads`).

La aplicación creará ahí las carpetas `hipo_conc/`, `analysis_ref/`, `lab_reagents/`, etc. (misma estructura que antes bajo `instance/uploads`).

**Recuperar archivos viejos**

Si tenés una copia del árbol `uploads` anterior (misma estructura):

- Copiá su contenido dentro de `APP_UPLOAD_ROOT`, **o**
- Dejá la copia en otra ruta y definí `APP_UPLOADS_READ_FALLBACK_PATHS` con rutas separadas por coma; la app buscará PDFs ahí para **servirlos** aunque el archivo principal esté en el fallback (las nuevas subidas siguen yendo a `APP_UPLOAD_ROOT`).

**Primera vez después de configurar el disco**: subir de nuevo los PDFs desde un usuario administrador, o restaurar copia de archivos como arriba.

## 7) Avisos por correo (planificación y mantenimiento)

Los destinatarios se pueden cargar en **Administración → Avisos por correo** (administrador) y/o con la variable **`DEADLINE_ALERT_EMAIL_TO`** en el servidor; la app **une ambas fuentes** sin duplicar. El servidor SMTP sigue siendo por variables de entorno (`SMTP_HOST`, `MAIL_FROM`, etc.; ver `project_web/.env.example`).

### Automático en Render (recomendado)

El archivo **`render.yaml`** de la raíz del repo incluye un **Cron Job** diario llamado **`qdv-salmuera-deadline-reminders`** que ejecuta:

`python -m flask --app run send-deadline-reminders`

- **Horario:** `13:00 UTC` todos los días (aprox. mañana en Argentina; podés cambiar el campo `schedule` en el YAML en formato cron UTC).
- **Coste:** Render cobra ese cron como **otro servicio** (plan `starter`, como el web).
- **Variables:** el Cron usa la misma `DATABASE_URL` (Postgres del Blueprint) que el web, y **hereda** `SECRET_KEY` y las variables `SMTP_*` / `MAIL_FROM` del servicio web (`fromService`). En el Blueprint, esas variables SMTP también están declaradas en el **servicio web** con `sync: false`: cargalas una sola vez en **Environment → qdv-salmuera-web**. Podés configurar opcionales solo en el web: `SMTP_PORT`, `SMTP_USE_TLS`, `DEADLINE_ALERT_EMAIL_TO`, `DEADLINE_REMINDER_DAYS_BEFORE` (el proceso las lee si existen en el entorno del Cron; si no, el código aplica valores por defecto donde aplica).

**Si tu proyecto ya estaba en Render antes de este cron:** entrá al **Blueprint** del repo en el dashboard y usá **Apply** / sincronizar para que se cree el servicio Cron. Revisá que en el web estén cargadas las variables SMTP del Blueprint.

**Comprobar envío:** en el servicio Cron de Render → **Logs** después de la hora programada, o ejecutá el mismo comando una vez a mano desde tu PC con `.env` de producción (solo para prueba).

### Manual (sin Cron en Render)

Si no usás el Cron del Blueprint, podés programar a mano el mismo comando una vez al día (por ejemplo con un Render **Cron Job** que vos crees o una tarea en tu PC):

```bash
python -m flask --app run send-deadline-reminders
```

Referencia local: bloque «Avisos por correo» al final de `project_web/.env.example`.

## 8) Si el deploy falla

Revisá en Render -> **Logs**:

- Error de `SECRET_KEY` faltante: agregarla en Environment.
- Error de DB/migración: verificar que PostgreSQL esté creada y enlazada.
- Error de imports: revisar que el deploy use la rama correcta.

