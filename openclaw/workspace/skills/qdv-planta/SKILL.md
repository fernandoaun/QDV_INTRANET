---
name: qdv-planta
description: Consulta y carga QDV por WhatsApp (mismo usuario y permisos que la intranet).
metadata:
  openclaw:
    requires:
      env: ["QDV_API_BASE_URL", "QDV_API_BEARER_TOKEN"]
      bins: ["node"]
---

# QDV planta (WhatsApp = otro cliente de la intranet)

WhatsApp no es un bot genérico: es la misma planta, con el **usuario QDV vinculado al número** que escribe.

Siempre pasá `--from` con el remitente del chat actual (E.164 o el JID de WhatsApp). **Nunca inventes un número.**

```bash
node {baseDir}/scripts/qdv-api.mjs --from +54911XXXXXXXX me
node {baseDir}/scripts/qdv-api.mjs --from +54911XXXXXXXX health
node {baseDir}/scripts/qdv-api.mjs --from +54911XXXXXXXX shift
node {baseDir}/scripts/qdv-api.mjs --from +54911XXXXXXXX dashboard
node {baseDir}/scripts/qdv-api.mjs --from +54911XXXXXXXX alertas
node {baseDir}/scripts/qdv-api.mjs --from +54911XXXXXXXX stock
node {baseDir}/scripts/qdv-api.mjs --from +54911XXXXXXXX reactor
node {baseDir}/scripts/qdv-api.mjs --from +54911XXXXXXXX agua
node {baseDir}/scripts/qdv-api.mjs --from +54911XXXXXXXX salmuera
node {baseDir}/scripts/qdv-api.mjs --from +54911XXXXXXXX entregas
```

Si falla `health`, decí que QDV no responde y no completes con datos viejos.
Si `me` da 403, el número no está en un usuario QDV (o está inactivo / es laboratorista): no hay datos.

## Cargas (preview → confirmación humana → confirm)

Nunca guardes de una. Armá el preview, mostrá el `resumen`, y **esperá** “sí, guardá” (o equivalente claro). Recién ahí `confirm`.

Audio o foto: interpretá, armá preview, y de nuevo esperá confirmación explícita.

```bash
node {baseDir}/scripts/qdv-api.mjs --from +54911XXXXXXXX preview agua '{"numero_columna":1,"temperatura":22,"dureza":1.5}' texto
node {baseDir}/scripts/qdv-api.mjs --from +54911XXXXXXXX confirm TOKEN_DEL_PREVIEW
```

Módulos de carga: `reactor` | `agua` | `salmuera` | `stock_ingreso` | `stock_consumo`.
Si `me.cargas.<modulo>` es false, no insistas: falta permiso o turno de planta (igual que en la web).

## Reglas

- Consultar = los mismos módulos que ve ese usuario en la web. Cargar = los mismos que puede editar, más turno activo si el perfil lo exige.
- No inventes existencias, turnos, lotes ni análisis. Solo el JSON del helper.
- No pidas ni uses `DATABASE_URL`. No SQL.
- No uses `API_BEARER_USER_ID` como si fuera la persona del chat.
- Si la API responde 401, el token de servicio está mal. Si 403, es el usuario/número/turno/permiso.
- No expongas el token ni URLs internas de Postgres.
- Respuestas cortas, español rioplatense.
