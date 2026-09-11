#!/usr/bin/env node
/**
 * Primera vez: escribe openclaw.json.
 * Arranques siguientes: actualiza WhatsApp allowFrom y skill QDV
 * sin borrar la sesión QR ni otras claves del operador.
 */
import fs from "node:fs";
import path from "node:path";

const STATE_DIR = process.env.OPENCLAW_STATE_DIR || "/data/.openclaw";
const WORKSPACE_DIR = process.env.OPENCLAW_WORKSPACE_DIR || "/data/workspace";
const SEED_DIR = "/opt/qdv/workspace-seed";
const CONFIG_PATH = path.join(STATE_DIR, "openclaw.json");

function parseAllowFrom(raw) {
  return String(raw || "")
    .split(/[,;\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function gatewayPort() {
  return Number(process.env.PORT || process.env.OPENCLAW_GATEWAY_PORT || 18789);
}

function publicOrigins() {
  const extras = [];
  for (const key of ["OPENCLAW_PUBLIC_URL", "RENDER_EXTERNAL_URL"]) {
    const v = (process.env[key] || "").trim().replace(/\/$/, "");
    if (v) extras.push(v);
  }
  const port = String(gatewayPort());
  return Array.from(
    new Set([
      ...extras,
      `http://127.0.0.1:${port}`,
      `http://localhost:${port}`,
    ]),
  );
}

function enableWhatsappPlugin(cfg) {
  cfg.plugins = cfg.plugins || {};
  cfg.plugins.entries = cfg.plugins.entries || {};
  cfg.plugins.entries.whatsapp = {
    ...(cfg.plugins.entries.whatsapp || {}),
    enabled: true,
  };
}

function copySeedFile(rel) {
  const src = path.join(SEED_DIR, rel);
  const dest = path.join(WORKSPACE_DIR, rel);
  if (!fs.existsSync(src)) return;
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  if (rel.startsWith("skills/") || !fs.existsSync(dest)) {
    fs.copyFileSync(src, dest);
  }
}

function walk(dir, acc, prefix = "") {
  if (!fs.existsSync(dir)) return acc;
  for (const name of fs.readdirSync(dir, { withFileTypes: true })) {
    const rel = prefix ? `${prefix}/${name.name}` : name.name;
    const full = path.join(dir, name.name);
    if (name.isDirectory()) walk(full, acc, rel);
    else acc.push(rel);
  }
  return acc;
}

function syncWorkspaceSeed() {
  fs.mkdirSync(WORKSPACE_DIR, { recursive: true });
  for (const rel of walk(SEED_DIR, [])) {
    copySeedFile(rel);
  }
}

function defaultConfig(allowFrom) {
  const token = (process.env.OPENCLAW_GATEWAY_TOKEN || "").trim();
  const model = (process.env.OPENCLAW_MODEL || "").trim();
  const cfg = {
    gateway: {
      mode: "local",
      bind: "lan",
      port: gatewayPort(),
      trustedProxies: ["10.0.0.0/8"],
      auth: { mode: "token" },
      controlUi: { allowedOrigins: publicOrigins() },
    },
    channels: {
      whatsapp: {
        enabled: true,
        dmPolicy: "allowlist",
        allowFrom,
        groupPolicy: "allowlist",
        groups: { "*": { requireMention: true } },
      },
    },
    agents: {
      defaults: {
        workspace: WORKSPACE_DIR,
        heartbeat: { every: "0m" },
        timeoutSeconds: 180,
      },
    },
    skills: {
      entries: {
        "qdv-planta": {
          enabled: true,
          env: {
            QDV_API_BASE_URL: process.env.QDV_API_BASE_URL || "",
            QDV_API_BEARER_TOKEN: process.env.QDV_API_BEARER_TOKEN || "",
          },
        },
      },
    },
    session: { scope: "per-sender" },
  };
  if (token) cfg.gateway.auth.token = token;
  if (model) cfg.agents.defaults.model = { primary: model };
  enableWhatsappPlugin(cfg);
  return cfg;
}

function mergeConfig(existing, allowFrom) {
  existing.gateway = existing.gateway || {};
  existing.gateway.mode = existing.gateway.mode || "local";
  existing.gateway.bind = "lan";
  existing.gateway.port = gatewayPort();
  existing.gateway.trustedProxies = existing.gateway.trustedProxies || ["10.0.0.0/8"];
  existing.gateway.auth = existing.gateway.auth || { mode: "token" };
  existing.gateway.auth.mode = "token";
  const token = (process.env.OPENCLAW_GATEWAY_TOKEN || "").trim();
  if (token) existing.gateway.auth.token = token;
  existing.gateway.controlUi = existing.gateway.controlUi || {};
  const origins = new Set(existing.gateway.controlUi.allowedOrigins || []);
  for (const o of publicOrigins()) origins.add(o);
  existing.gateway.controlUi.allowedOrigins = Array.from(origins);

  existing.channels = existing.channels || {};
  existing.channels.whatsapp = existing.channels.whatsapp || {};
  existing.channels.whatsapp.enabled = true;
  existing.channels.whatsapp.dmPolicy = existing.channels.whatsapp.dmPolicy || "allowlist";
  existing.channels.whatsapp.groupPolicy = existing.channels.whatsapp.groupPolicy || "allowlist";
  if (allowFrom.length) existing.channels.whatsapp.allowFrom = allowFrom;
  existing.channels.whatsapp.groups = existing.channels.whatsapp.groups || {
    "*": { requireMention: true },
  };

  existing.agents = existing.agents || {};
  existing.agents.defaults = existing.agents.defaults || {};
  existing.agents.defaults.workspace = WORKSPACE_DIR;
  existing.agents.defaults.heartbeat = existing.agents.defaults.heartbeat || { every: "0m" };
  const model = (process.env.OPENCLAW_MODEL || "").trim();
  if (model) existing.agents.defaults.model = { primary: model };

  existing.skills = existing.skills || {};
  existing.skills.entries = existing.skills.entries || {};
  existing.skills.entries["qdv-planta"] = {
    enabled: true,
    env: {
      QDV_API_BASE_URL: process.env.QDV_API_BASE_URL || "",
      QDV_API_BEARER_TOKEN: process.env.QDV_API_BEARER_TOKEN || "",
    },
  };
  if (existing.skills.load && Array.isArray(existing.skills.load.extraDirs)) {
    existing.skills.load.extraDirs = existing.skills.load.extraDirs.filter(
      (d) => d !== "/opt/qdv/workspace-seed/skills",
    );
  }
  enableWhatsappPlugin(existing);
  return existing;
}

function main() {
  if ((process.env.DATABASE_URL || "").trim()) {
    console.error("ADVERTENCIA — aislamiento de base local");
    console.error("OpenClaw no debe tener DATABASE_URL. Quitá esa variable y usá /api/v1.");
    process.exit(2);
  }

  fs.mkdirSync(STATE_DIR, { recursive: true });
  syncWorkspaceSeed();

  const allowFrom = parseAllowFrom(process.env.QDV_WHATSAPP_ALLOW_FROM);
  let cfg;
  if (fs.existsSync(CONFIG_PATH)) {
    const raw = fs.readFileSync(CONFIG_PATH, "utf8");
    try {
      cfg = mergeConfig(JSON.parse(raw), allowFrom);
    } catch (err) {
      console.error(`No pude parsear ${CONFIG_PATH}: ${err.message}`);
      console.error("Dejo el archivo intacto (sesión WhatsApp a salvo).");
      return;
    }
  } else {
    cfg = defaultConfig(allowFrom);
  }

  fs.writeFileSync(CONFIG_PATH, `${JSON.stringify(cfg, null, 2)}\n`, "utf8");
  console.log(`OpenClaw config lista: ${CONFIG_PATH}`);
  if (!allowFrom.length) {
    console.warn("QDV_WHATSAPP_ALLOW_FROM vacío: el bot no responderá DMs hasta cargar números E.164.");
    console.warn("Esos números también tienen que existir en un usuario QDV (identidad; no alcanza la allowlist).");
  }
}

main();
