#!/bin/sh
# Baileys rc14 toma la versión de WhatsApp Web de su repo en GitHub, que quedó
# vieja; WhatsApp la rechaza al vincular ("No se pueden vincular dispositivos
# nuevos en este momento"). Se redirige a fetchLatestWaWebVersion, que la lee
# de web.whatsapp.com. Idempotente; cubre el plugin instalado en /data.
for f in /app/node_modules/.pnpm/baileys@*/node_modules/baileys/lib/Utils/generics.js \
         "${OPENCLAW_STATE_DIR:-/data/.openclaw}"/npm/projects/*/node_modules/@openclaw/whatsapp/node_modules/baileys/lib/Utils/generics.js; do
  [ -f "$f" ] || continue
  grep -q 'qdv-wa-version' "$f" && continue
  sed -i 's|^export const fetchLatestBaileysVersion = async (options = {}) => {$|&\n    return fetchLatestWaWebVersion(options); // qdv-wa-version|' "$f" \
    && echo "patch_baileys: $f"
done

# WhatsApp a veces deja de entregar mensajes sin cortar la conexión ("app-silent").
# OpenClaw tarda 4 × 30 min en notarlo y al reconectar descarta lo que llegó hace más
# de 20 min (y solo lo recupera si hubo charla reciente): esos mensajes se perdían.
# Ajuste: detecta el silencio en 4 × 10 min y al reconectar siempre responde lo que
# llegó en los últimos 45 min. Idempotente; si cambia el código del plugin, avisa.
for f in "${OPENCLAW_STATE_DIR:-/data/.openclaw}"/npm/projects/*/node_modules/@openclaw/whatsapp/dist/.setup/monitor-*.mjs \
         /app/node_modules/.pnpm/*/node_modules/@openclaw/whatsapp/dist/.setup/monitor-*.mjs; do
  [ -f "$f" ] || continue
  grep -q 'WHATSAPP_RECONNECT_CATCH_UP_MAX_MS' "$f" || continue
  grep -q 'qdv-wa-catchup' "$f" && continue
  if grep -q 'tuning.messageTimeoutMs ?? 18e5;' "$f" \
     && grep -q 'const WHATSAPP_RECONNECT_CATCH_UP_MAX_MS = 12e5;' "$f" \
     && grep -q 'Math.min(Math.max(messageTimeoutMs, 6e4), WHATSAPP_RECONNECT_CATCH_UP_MAX_MS)' "$f" \
     && grep -q 'appendReplyWindow: connectionLocal.openedAfterRecentInbound ? {' "$f"; then
    sed -i \
      -e 's|tuning.messageTimeoutMs ?? 18e5;|tuning.messageTimeoutMs ?? 6e5; // qdv-wa-catchup|' \
      -e 's|const WHATSAPP_RECONNECT_CATCH_UP_MAX_MS = 12e5;|const WHATSAPP_RECONNECT_CATCH_UP_MAX_MS = 27e5;|' \
      -e 's|Math.min(Math.max(messageTimeoutMs, 6e4), WHATSAPP_RECONNECT_CATCH_UP_MAX_MS)|Math.min(Math.max(messageTimeoutMs * 4 + 3e5, 6e4), WHATSAPP_RECONNECT_CATCH_UP_MAX_MS)|' \
      -e 's|appendReplyWindow: connectionLocal.openedAfterRecentInbound ? {|appendReplyWindow: true ? {|' \
      "$f" && echo "patch_wa_catchup: $f"
  else
    echo "patch_wa_catchup: NO aplicado (cambió el plugin): $f" >&2
  fi
done
