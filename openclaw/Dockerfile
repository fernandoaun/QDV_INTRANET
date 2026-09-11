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
ENTRYPOINT ["/opt/qdv/docker-entrypoint.sh"]
