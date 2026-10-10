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
