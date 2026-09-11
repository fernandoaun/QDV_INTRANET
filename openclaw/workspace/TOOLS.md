# Herramientas

Skill principal: `qdv-planta` → `node {baseDir}/scripts/qdv-api.mjs <comando>`.

No uses shell para curl a Postgres ni para leer `.env` de QDV.
El token va en el entorno del proceso (`QDV_API_BEARER_TOKEN`); no lo imprimas.
