# OpenClaw + WhatsApp nativo (QDV)

Asistente de planta por WhatsApp. **No es WhatsApp Business.** El canal es el gateway que trae OpenClaw (`channels.whatsapp`, QR de Dispositivos vinculados).

WhatsApp es **otro cliente de QDV**: mismos permisos que la intranet. El número que escribe se resuelve a un usuario (`Admin → Usuarios → WhatsApp`). Número desconocido = no hay datos.

Este directorio es un **servicio aparte** de `project_web`. No abre Postgres. No copies `DATABASE_URL`.

```
WhatsApp (texto / audio / foto)
        │
        ▼
  OpenClaw gateway (esta carpeta)
        │  Bearer + X-QDV-WhatsApp → /api/v1
        ▼
  QDV web (local o Render)
```

## Qué necesitás

- Docker Desktop (colegas Windows: dejalo iniciado)
- QDV web corriendo (local o `*.onrender.com`)
- Un **número de WhatsApp aparte** para el bot
- Al menos una clave de modelo: OpenRouter, Anthropic o OpenAI
- Cada operador con su celular en el usuario QDV (E.164, `+54911…`) **y** en `QDV_WHATSAPP_ALLOW_FROM`

Dos filtros distintos:

1. **Allowlist** (`QDV_WHATSAPP_ALLOW_FROM`): OpenClaw ni siquiera responde si el número no está.
2. **Identidad QDV**: el mismo número tiene que estar en el usuario. Si no, la API responde 403.

## Arranque en la PC (compartir con colegas)

1. Levantá QDV (`project_web/iniciar_local.bat`). **No** pongas `DATABASE_URL` en `project_web/.env`.
2. Generá un token de servicio:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

3. En `project_web/.env` (solo local; no lo subas a Git):

```env
API_BEARER_TOKEN=<el token>
```

`API_BEARER_USER_ID` no hace falta para WhatsApp. Reiniciá QDV.

4. En cada usuario de planta (Admin): cargá el WhatsApp en formato `+54911…`.
5. En `openclaw/` copiá `.env.example` → `.env` y completá:

- `OPENCLAW_GATEWAY_TOKEN` (el `.bat` puede generarlo)
- `QDV_API_BASE_URL=http://host.docker.internal:5000`
- `QDV_API_BEARER_TOKEN` = el **mismo** token
- `QDV_WHATSAPP_ALLOW_FROM=+54911…` (los mismos números que en QDV)
- Una clave `OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`

6. Doble clic en `iniciar_openclaw.bat` (o `docker compose up --build`).
7. Dashboard: [http://127.0.0.1:18789/](http://127.0.0.1:18789/) — pegá `OPENCLAW_GATEWAY_TOKEN`.
8. `whatsapp_login.bat` → escaneá el QR **en vivo** con el celular del bot.
9. Escribile al bot desde un número vinculado: “¿hay stock crítico?” o una carga (el bot pide confirmación).

Comprobación sin Docker:

```powershell
python openclaw\scripts\check_setup.py
```

## Render (producción)

El Blueprint de la **raíz** (`render.yaml`) declara `qdv-salmuera-web` y `qdv-openclaw`. Aplicarlo crea el segundo servicio Docker (Starter, disco `/data`). **No** mezcles OpenClaw en el proceso Flask.

1. Environment de **QDV**: `API_BEARER_TOKEN` (el mismo que vas a poner en OpenClaw). Redeploy.
2. Environment de **qdv-openclaw**:

| Variable | Valor |
|---|---|
| `QDV_API_BASE_URL` | `https://TU-QDV.onrender.com` (sin barra final) |
| `QDV_API_BEARER_TOKEN` | el mismo que en QDV |
| `QDV_WHATSAPP_ALLOW_FROM` | `+54911…,+549351…` (usuarios QDV) |
| `OPENCLAW_GATEWAY_TOKEN` | lo genera Render, o uno propio |
| `OPENROUTER_API_KEY` (u otra) | clave del modelo |
| `OPENCLAW_PUBLIC_URL` | `https://TU-OPENCLAW.onrender.com` |
| `TZ` / `OPENCLAW_TZ` | `America/Argentina/Buenos_Aires` |

**No** definas `DATABASE_URL` en OpenClaw.

3. Shell de OpenClaw:

```bash
openclaw channels login --channel whatsapp
```

QR en vivo. La sesión queda en el disco `/data`. Plan **Starter o más** (el Free se duerme y WhatsApp se desvincula).

## Qué puede hacer el bot

Skill `qdv-planta`: consulta y carga con los permisos de **quien escribe**.

- Consulta: turno, panel, stock, alertas, entregas, últimos reactor/agua/salmuera.
- Carga: `preview` → la persona dice “sí, guardá” → `confirm`. Audio y foto igual (nunca guardar sin confirmar).
- Módulos de carga: reactor, agua, salmuera, ingreso/consumo de stock.
- Sin turno de planta (si el perfil lo exige): no carga. Angel solo lee. Laboratorista no opera.

## Problemas frecuentes

| Síntoma | Qué hacer |
|---|---|
| `DATABASE_URL` en OpenClaw | Borrarlo. El check sale con código 2. |
| 401 en la API | Token distinto entre QDV y OpenClaw. |
| 403 “no hay un usuario QDV” | Cargá el número en Admin → Usuarios. |
| El bot no responde WhatsApp | Número no está en `allowFrom`, o el plan Free apagó el servicio. |
| Hay que escanear QR otra vez | Falta disco persistente, o se borró el volume. |
| Dashboard pide token | `OPENCLAW_GATEWAY_TOKEN` del Environment / `.env`. |
| Deploy cancelado / “No open ports” | Health Check Path = `/healthz`. El gateway tiene que escuchar `$PORT` (en Render suele ser 10000). |

## Política de datos

- Local QDV = SQLite (`project_web/instance/`). Remoto = Postgres en Render.
- OpenClaw no sincroniza ni copia esas bases.
- `.env` y `*.db` no se suben a Git.
