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

Módulos de carga: `reactor` | `agua` | `salmuera` | `stock_ingreso` | `stock_consumo` | `carga_camion` | `descarga_camion`.
Carga de camión (`carga_camion`, choferes y operaciones; no pide turno):
- Primero mirá `entregas`: si hay una entrega `programada` de hoy para ese chofer (`chofer_previsto`), ofrecésela y cargá con `{"entrega_id":N,"litros":X}` (litros reales cargados).
- Si no hay programada (o dice que es otra), carga directa: `{"litros":X}`; el chofer sale de su usuario (o pasá `"chofer":"Rafa"`).
- Si te dice solo los litros de hipoclorito, antes del preview preguntale: «¿Llevás agua también? ¿Cuántos litros?». Si lleva, mandá `"agua_litros":Y`; si no, no lo mandes. Si ya te dijo hipoclorito y agua juntos, no preguntes. El agua no toca stock ni producción: solo queda anotada en la carga.
- Si avisa el agua después de que la carga ya quedó registrada, agregala a esa carga con `{"entrega_id":N,"agua_litros":Y}` (sin `litros`).
- Los campos son exactamente `litros` (hipoclorito), `agua_litros`, `entrega_id`, `chofer`. No inventes otros.
Descarga del camión (`descarga_camion`, choferes; una por cada punto donde descargan):
- `{"destino":"<texto como lo dijo el chofer>","litros":X}`. `litros` = lo que descargó en ese punto tal como lo dice (si mezcló agua con el hipoclorito, el total descargado). No le preguntes cuánto era agua y cuánto hipoclorito. Usa la última carga del chofer que todavía tiene litros; si dice otra, agregá `"entrega_id":N`.
- Si el sistema responde que hay varios destinos («¿Cuál?»), preguntale al chofer cuál de esas opciones y reenviá con ese texto. Si el destino no existe, decile que logística lo tiene que dar de alta.
- Después de confirmar, decile cuántos litros le quedan en el camión (viene en la respuesta).
En `stock_consumo`, los filtros de papel llevan `"equipo"`: "Tanque Salmuera Clarificada" o "Tolva UltraPura" (preguntá cuál si no lo dice).
Si `me.cargas.<modulo>` es false, no insistas: falta permiso o turno de planta (igual que en la web).

## Reglas

- Consultar = los mismos módulos que ve ese usuario en la web. Cargar = los mismos que puede editar, más turno activo si el perfil lo exige.
- No inventes existencias, turnos, lotes ni análisis. Solo el JSON del helper.
- No pidas ni uses `DATABASE_URL`. No SQL.
- No uses `API_BEARER_USER_ID` como si fuera la persona del chat.
- Si la API responde 401, el token de servicio está mal. Si 403, es el usuario/número/turno/permiso.
- No expongas el token ni URLs internas de Postgres.
- Respuestas cortas, español rioplatense.
