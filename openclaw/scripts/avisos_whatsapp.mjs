// Retira de QDV los avisos (copia de los mails del sistema) y los manda por WhatsApp
// con la herramienta `message` del gateway local. Corre en segundo plano junto al gateway.
// Si el aviso trae adjunto (p. ej. el PDF del procedimiento aprobado), lo baja y lo manda
// como documento con el texto de epígrafe.
//
// QDV:     GET  {QDV_API_BASE_URL}/api/v1/whatsapp/avisos
//          GET  {QDV_API_BASE_URL}/api/v1/whatsapp/avisos/<id>/adjunto
//          POST {QDV_API_BASE_URL}/api/v1/whatsapp/avisos/<id>/resultado
// Gateway: POST http://127.0.0.1:{OPENCLAW_GATEWAY_PORT}/tools/invoke

import { mkdir, rm, writeFile } from "node:fs/promises";
import http from "node:http";
import https from "node:https";
import { tmpdir } from "node:os";
import { join } from "node:path";

const BASE = String(process.env.QDV_API_BASE_URL || "").replace(/\/+$/, "");
const TOKEN = String(process.env.QDV_API_BEARER_TOKEN || "").trim();
const GW_TOKEN = String(process.env.OPENCLAW_GATEWAY_TOKEN || "").trim();
const GW_PORT = String(process.env.OPENCLAW_GATEWAY_PORT || process.env.PORT || "18789");
const INTERVALO_MS = Number(process.env.QDV_AVISOS_INTERVALO_MS || 60_000);
// Pausa entre mensajes: ráfagas desde un número nuevo son lo que Meta marca como spam.
const PAUSA_MS = Number(process.env.QDV_AVISOS_PAUSA_MS || 4_000);

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => console.log("[qdv-avisos]", ...a);

async function qdv(path, init = {}) {
  const r = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    signal: AbortSignal.timeout(20_000),
  });
  if (!r.ok) throw new Error(`QDV ${path} → HTTP ${r.status}`);
  return r.json();
}

// GET binario con node:http (no fetch: el undici de Node 24 aborta el proceso con
// «assert(!this.paused)» al bajar un archivo de gunicorn).
function bajarBinario(url, headers, timeoutMs) {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith("https:") ? https : http;
    const req = mod.get(url, { headers, timeout: timeoutMs }, (res) => {
      if (res.statusCode !== 200) {
        res.resume();
        reject(new Error(`HTTP ${res.statusCode}`));
        return;
      }
      const partes = [];
      res.on("data", (c) => partes.push(c));
      res.on("end", () => resolve(Buffer.concat(partes)));
      res.on("error", reject);
    });
    req.on("timeout", () => req.destroy(new Error("timeout")));
    req.on("error", reject);
  });
}

// Baja el adjunto a una carpeta temporal propia del aviso; devuelve la ruta local.
async function bajarAdjunto(aviso) {
  let contenido;
  try {
    contenido = await bajarBinario(`${BASE}${aviso.adjunto.url}`, { Authorization: `Bearer ${TOKEN}` }, 60_000);
  } catch (e) {
    throw new Error(`QDV adjunto #${aviso.id} → ${e?.message || e}`);
  }
  const dir = join(tmpdir(), "qdv-avisos", String(aviso.id));
  await mkdir(dir, { recursive: true });
  const nombre = String(aviso.adjunto.nombre || "documento.pdf").replace(/[\\/]+/g, "_");
  const ruta = join(dir, nombre);
  await writeFile(ruta, contenido);
  return { dir, ruta };
}

async function enviar(aviso) {
  const adj = aviso.adjunto ? await bajarAdjunto(aviso) : null;
  const args = { channel: "whatsapp", target: aviso.telefono, message: aviso.texto };
  if (adj) Object.assign(args, { media: adj.ruta, asDocument: true });
  try {
    await invocar(aviso, args);
  } finally {
    if (adj) await rm(adj.dir, { recursive: true, force: true }).catch(() => {});
  }
}

async function invocar(aviso, args) {
  const r = await fetch(`http://127.0.0.1:${GW_PORT}/tools/invoke`, {
    method: "POST",
    headers: { Authorization: `Bearer ${GW_TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      tool: "message",
      action: "send",
      args,
      idempotencyKey: `qdv-aviso-${aviso.id}`,
    }),
    signal: AbortSignal.timeout(60_000),
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok || body.ok !== true) {
    throw new Error(`gateway HTTP ${r.status}: ${JSON.stringify(body).slice(0, 300)}`);
  }
}

async function ronda() {
  const { avisos = [] } = await qdv("/api/v1/whatsapp/avisos?limit=20");
  for (const aviso of avisos) {
    let resultado = { ok: true };
    try {
      await enviar(aviso);
      log(`enviado #${aviso.id}`);
    } catch (e) {
      resultado = { ok: false, error: String(e?.message || e).slice(0, 480) };
      log(`falló #${aviso.id}: ${resultado.error}`);
    }
    await qdv(`/api/v1/whatsapp/avisos/${aviso.id}/resultado`, {
      method: "POST",
      body: JSON.stringify(resultado),
    });
    await dormir(PAUSA_MS);
  }
}

if (!BASE || !TOKEN || !GW_TOKEN) {
  log("sin QDV_API_BASE_URL / QDV_API_BEARER_TOKEN / OPENCLAW_GATEWAY_TOKEN: avisos desactivados");
} else {
  // Dar tiempo a que el gateway termine de arrancar y conecte WhatsApp.
  await dormir(Number(process.env.QDV_AVISOS_ESPERA_INICIAL_MS || 120_000));
  log("activo");
  for (;;) {
    try {
      await ronda();
    } catch (e) {
      log(`ronda con error: ${String(e?.message || e).slice(0, 300)}`);
    }
    await dormir(INTERVALO_MS);
  }
}
