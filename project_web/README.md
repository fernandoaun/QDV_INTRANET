# QDV Salmuera — versión web

Aplicación Flask en la carpeta `project_web/`, separada de la app de escritorio (`qdv_salmuera/`). Incluye SQLite local o PostgreSQL en producción, Alembic, login y comando para crear administrador.

### Windows — ejecutar en tu PC (orden exacto)

1. Abrí **PowerShell** o **CMD**.
2. Entrá a la carpeta del proyecto web:

   ```powershell
   cd "RUTA\AL\REPO\project_web"
   ```

3. Instalá dependencias, copiá env de ejemplo, migraciones y servidor:

   ```powershell
   python -m pip install -r requirements.txt
   copy .env.example .env
   python -m alembic upgrade head
   python run.py
   ```

4. En el navegador: **http://127.0.0.1:5000/**

**Atajo:** hacé doble clic en `iniciar_local.bat` dentro de `project_web` (hace los pasos anteriores y arranca el servidor).

---

## 1. Qué hace falta para correr en local

- Python **3.10+** (recomendado 3.12, ver `runtime.txt`).
- Dependencias de `requirements.txt`.
- Archivo **`.env`** (recomendado; ver sección 6).
- Migraciones aplicadas: `python -m alembic upgrade head`.

---

## 2. Dependencias y archivos

| Elemento | Estado |
|----------|--------|
| `requirements.txt` | Flask, Flask-SQLAlchemy, Alembic, psycopg2-binary, gunicorn, python-dotenv |
| `config.py` | Dev/prod; en prod: `SECRET_KEY` + `DATABASE_URL` (Postgres) obligatorios; con Postgres activa `pool_pre_ping`, `pool_recycle` y `connect_timeout` (ver `DEPLOY_RENDER.md` §10) |
| `run.py` / `wsgi.py` | App para desarrollo y gunicorn |
| `alembic.ini` + `migrations/` | Alembic enlazado a `db.metadata` vía `create_app()` |
| `Procfile` | `gunicorn` para PaaS |
| `../render.yaml` (raíz del repo) | Blueprint Render: Postgres + web (`rootDir: project_web`) |
| `project_web/render.yaml` | Aviso: el Blueprint activo está en la raíz del monorepo |
| `railway.json` | Railway: build, `preDeployCommand` (Alembic), gunicorn |
| `Dockerfile` | Opcional: imagen para VPS / Docker (build desde raíz del repo) |

---

## 3. Comando exacto para levantar la app

Desde la carpeta **`project_web`**:

```powershell
python run.py
```

Alternativa (servidor de Flask):

```powershell
python -m flask --app run run
```

Abrir: **http://127.0.0.1:5000/** (o el puerto del env `PORT`).

---

## 4. Alembic

- **`migrations/env.py`**: inserta `project_web` en `sys.path`, llama `create_app()`, usa `SQLALCHEMY_DATABASE_URI` y `db.metadata` (los modelos se importan en `create_app()`).
- **Revisiones**: `20250329_0001` (vacía), `20250329_0002` (`usuarios`), `283ddb2c1925` (producción, stock, permisos, equipos, etc.). Tras actualizar el código: `python -m alembic upgrade head`.

Comandos (siempre dentro de `project_web`):

```powershell
python -m alembic current
python -m alembic upgrade head
python -m alembic history
```

---

## 5. SQLite local

Si **no** definís `DATABASE_URL`, la app usa un archivo **absoluto**:

`project_web/instance/qdv_web.db`

Así la base no depende del directorio desde el que ejecutes Python.

---

## 6. Crear el archivo `.env`

1. Copiá el ejemplo:

   ```powershell
   cd project_web
   Copy-Item .env.example .env
   ```

2. Editá `.env` con un editor de texto.

3. Mínimo recomendado en **local**:

   ```env
   FLASK_ENV=development
   SECRET_KEY=un-valor-largo-y-aleatorio
   ```

4. **No** subas `.env` a Git (está en `.gitignore`).

5. Dejá **sin definir** `DATABASE_URL` para SQLite automático, salvo que quieras forzar otra URL.

---

## 7. Crear usuario administrador

**Primero** aplicá migraciones. Luego, desde `project_web`:

**Opción A — contraseña por línea de comandos (útil para scripts):**

```powershell
python -m flask --app run create-admin mi_usuario --password "TuPasswordSeguro"
```

**Opción B — contraseña interactiva (no queda en historial):**

```powershell
python -m flask --app run create-admin mi_usuario
```

El nombre de usuario se guarda en **minúsculas**. El rol es **administrador** (`is_admin=true`, `activo=true`).

---

## 8. Checklist de pruebas mínimas

- [ ] `pip install -r requirements.txt` sin errores.
- [ ] Existe `.env` con `SECRET_KEY` (desaparece el warning al arrancar).
- [ ] `python -m alembic upgrade head` termina en `head`.
- [ ] Existe `instance/qdv_web.db` (o la ruta que muestre el log si usás otra URL).
- [ ] `python run.py` y la página `/` carga.
- [ ] `create-admin` crea usuario; login en `/login` redirige a `/dashboard`.
- [ ] `/dashboard` sin sesión redirige a `/login`.
- [ ] Cerrar sesión (navbar) vuelve al inicio.
- [ ] `python -m flask --app run routes` lista `/`, `/login`, `/logout`, `/dashboard`.

---

## 9. Listo para GitHub

- **Sí**, si el repo incluye `project_web/` con `.gitignore` (`.env`, `instance/`, venv).
- **No subir**: `.env`, `instance/*.db`, contraseñas, `SECRET_KEY` real.
- El Blueprint de Render debe estar en la **raíz del repo** (`render.yaml` junto a `project_web/`). Si el remoto es **solo** `project_web`, copiá ese YAML aquí y quitá `rootDir`.
- Revisá que el repo padre (monorepo) no fuerce subir `instance/` desde otra ruta.

---

## 10. Deploy (Render / Railway / Docker / VPS)

### Qué queda listo en el repo

- **`render.yaml`** en la **raíz del monorepo** (hermano de `project_web/`): servicio web + PostgreSQL enlazado (`DATABASE_URL`), Alembic en `preDeployCommand`.
- **`project_web/config.py`**: en `FLASK_ENV=production` exige **`SECRET_KEY`** y **`DATABASE_URL`** (no SQLite en servidor).
- **`railway.json`**, **`Procfile`**, **`wsgi.py`**: arranque con gunicorn.
- **`Dockerfile`** en `project_web/`: build desde la raíz del repo (ver abajo).

### Checklist antes de exponer la URL pública

1. Repositorio en GitHub/GitLab (o conexión que use tu PaaS).
2. Base **PostgreSQL** creada (plugin en Railway, recurso Postgres en Render, o contenedor/managed en VPS).
3. Variables en el servicio web:
   - `FLASK_ENV=production`
   - `SECRET_KEY` (obligatorio; podés generar: `python -c "import secrets; print(secrets.token_hex(32))"`)
   - `DATABASE_URL` con la cadena que te da el proveedor (interna si el PaaS lo ofrece)
   - `SESSION_COOKIE_SECURE=true` detrás de HTTPS
4. Primer deploy: migraciones (`alembic upgrade head`) ya van en Render/Railway vía `preDeployCommand`.
5. **Una vez** levantado el sitio: crear admin con `create-admin` (shell del servicio o comando one-off).
6. Cambiar la contraseña por defecto del entorno de pruebas si alguna vez se usó la misma DB.

### Variables obligatorias en producción

- `FLASK_ENV=production`
- `SECRET_KEY`
- `DATABASE_URL` → PostgreSQL (Render/Railway suelen dar `postgres://...`; el código normaliza a `postgresql+psycopg2://`)
- `SESSION_COOKIE_SECURE=true` en HTTPS

### Render

- En el dashboard: **New → Blueprint** y elegí el repo; Render lee **`render.yaml` en la raíz**.
- En **Environment** del servicio web, definí **`SECRET_KEY`** (en el blueprint está `sync: false` para no versionarla).
- El bloque `databases` declara Postgres; si el plan no aplica a tu cuenta, creá la base a mano en Render y asigná `DATABASE_URL` igualmente (podés simplificar el YAML quitando `databases` y `fromDatabase`).

### Railway

- **New Project → Deploy from GitHub** → servicio con **Root Directory** = `project_web`.
- Añadí **PostgreSQL**; en el servicio web, variable `DATABASE_URL` referenciando la base (Railway suele inyectarla sola al conectar).
- Definí `FLASK_ENV`, `SECRET_KEY`, `SESSION_COOKIE_SECURE` como en Render.

### Comando de arranque (Render / Railway / Procfile)

```bash
gunicorn -w 2 -b 0.0.0.0:$PORT wsgi:app
```

### Docker (VPS u host propio)

Desde la **raíz del repositorio** (donde están `project_web/` y `render.yaml`):

```bash
docker build -f project_web/Dockerfile -t qdv-web .
docker run --rm -p 8000:8000 \
  -e FLASK_ENV=production \
  -e SECRET_KEY="cambiar-por-secreto-largo" \
  -e DATABASE_URL="postgresql://usuario:clave@host:5432/nombre_bd" \
  -e SESSION_COOKIE_SECURE=true \
  qdv-web
```

Detrás de un proxy TLS (nginx, Caddy, Traefik), mantené `SESSION_COOKIE_SECURE=true` y serví la app por HTTPS.

### Primer usuario en producción

Tras el primer deploy, ejecutá **una vez** (shell del servicio, “Run command”, o `docker exec`):

```bash
python -m flask --app run create-admin admin --password "..."
```

---

## Notas de seguridad

- Los envíos **POST** de formularios están protegidos con **CSRF** (Flask-WTF): cada `<form method="post">` incluye el token vía `{% include "_csrf.html" %}`. Si agregás un formulario nuevo, incluí ese fragmento dentro del formulario.
- Las contraseñas usan `werkzeug.security` (esquema distinto al hash personalizado de la app de escritorio): usuarios migrados desde el desktop requerirán **reestablecer contraseña** o un script de migración de hashes.

## Relación con la app de escritorio

En el mismo repositorio, la carpeta `qdv_salmuera/` (hermana de `project_web/`) es la app **Tkinter** con **otro SQLite**. No comparte base con esta web. Para política de uso y riesgo de divergencia, ver el `README.md` en la raíz del monorepo.
