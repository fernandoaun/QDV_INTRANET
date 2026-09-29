# Gateway OpenClaw + skill QDV. No incluye la app Flask ni Postgres.
# Contexto de build: carpeta openclaw/

ARG OPENCLAW_IMAGE=ghcr.io/openclaw/openclaw:latest
FROM ${OPENCLAW_IMAGE}

USER root
COPY --chown=node:node scripts/ensure_config.mjs /opt/qdv/ensure_config.mjs
COPY --chown=node:node docker-entrypoint.sh /opt/qdv/docker-entrypoint.sh
COPY --chown=node:node workspace /opt/qdv/workspace-seed
RUN chmod 0755 /opt/qdv/docker-entrypoint.sh \
    && mkdir -p /data \
    && chown node:node /data

ENV OPENCLAW_STATE_DIR=/data/.openclaw \
    OPENCLAW_WORKSPACE_DIR=/data/workspace \
    OPENCLAW_CONFIG_DIR=/data/.openclaw \
    OPENCLAW_GATEWAY_PORT=18789

WORKDIR /app
EXPOSE 18789
# El HEALTHCHECK de la imagen base corre `openclaw` y, con USER root, puede crear
# /data/.openclaw/state como root antes que el gateway (EACCES al arrancar).
# /healthz no toca el estado.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||18789)+'/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
# tini (de la imagen base) como PID 1: reenvía señales y cosecha procesos hijos.
ENTRYPOINT ["tini", "-s", "--", "/opt/qdv/docker-entrypoint.sh"]
