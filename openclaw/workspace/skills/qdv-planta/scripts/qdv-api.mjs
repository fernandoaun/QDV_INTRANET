#!/usr/bin/env node
/**
 * Cliente HTTP de QDV /api/v1 para OpenClaw.
 * Identidad: Bearer (servicio) + X-QDV-WhatsApp (usuario de planta).
 * Uso: node qdv-api.mjs --from +54911… <comando> [args...]
 * No recibe DATABASE_URL.
 */
const BASE = String(process.env.QDV_API_BASE_URL || "")
  .trim()
  .replace(/\/$/, "");
const TOKEN = String(process.env.QDV_API_BEARER_TOKEN || "").trim();

const GET_COMMANDS = {
  health: { path: "/api/v1/health", auth: false },
  meta: { path: "/api/v1/sync/meta", auth: false },
  me: { path: "/api/v1/me", auth: true },
  shift: { path: "/api/v1/shift/status", auth: true },
  dashboard: { path: "/api/v1/dashboard/snapshot", auth: true },
  entregas: { path: "/api/v1/entregas", auth: true },
  stock: { path: "/api/v1/stock/existencias?categoria=todas", auth: true },
  "stock-mp": { path: "/api/v1/stock/existencias?categoria=materia_prima", auth: true },
  "stock-lab": { path: "/api/v1/stock/existencias?categoria=laboratorio", auth: true },
  "stock-pt": { path: "/api/v1/stock/existencias?categoria=producto_terminado", auth: true },
  alertas: { path: "/api/v1/stock/alertas", auth: true },
  reactor: { path: "/api/v1/produccion/reactor/ultimo", auth: true },
  agua: { path: "/api/v1/produccion/agua/ultimo", auth: true },
  salmuera: { path: "/api/v1/produccion/salmuera/ultimos", auth: true },
};

function usage() {
  console.error(
    "Uso: node qdv-api.mjs --from +54911… <health|me|shift|dashboard|alertas|stock|reactor|agua|salmuera|preview|confirm|…>",
  );
  process.exit(1);
}

function parseArgs(argv) {
  const out = {
    from: String(process.env.QDV_WHATSAPP_FROM || "").trim(),
    cmd: "",
    rest: [],
  };
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--from" || a === "--whatsapp") {
      out.from = String(argv[i + 1] || "").trim();
      i += 1;
    } else if (a.startsWith("--from=")) {
      out.from = a.slice("--from=".length).trim();
    } else if (!out.cmd) {
      out.cmd = a;
    } else {
      out.rest.push(a);
    }
  }
  return out;
}

function authHeaders(needAuth, from) {
  if (!BASE) {
    throw new Error("Falta QDV_API_BASE_URL");
  }
  if (needAuth && !TOKEN) {
    throw new Error("Falta QDV_API_BEARER_TOKEN");
  }
  const headers = { Accept: "application/json" };
  if (needAuth) {
    headers.Authorization = `Bearer ${TOKEN}`;
    const wa = String(from || "").trim();
    if (!wa) {
      throw new Error(
        "Falta el número de WhatsApp del chat. Pasá --from +54911… (el remitente, no lo inventes).",
      );
    }
    headers["X-QDV-WhatsApp"] = wa;
  }
  return headers;
}

async function request(path, { auth, from, method = "GET", body }) {
  const headers = authHeaders(auth, from);
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let pretty = text;
  try {
    pretty = JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    /* keep raw */
  }
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} ${path}\n${pretty}`);
  }
  return pretty;
}

async function main() {
  const { from, cmd, rest } = parseArgs(process.argv);
  if (!cmd || cmd === "-h" || cmd === "--help") usage();

  if (cmd === "consumos-dias") {
    const dias = encodeURIComponent(rest[0] || "7");
    const limit = encodeURIComponent(rest[1] || "50");
    process.stdout.write(
      await request(`/api/v1/stock/consumos/ultimos-dias?dias=${dias}&limit=${limit}`, {
        auth: true,
        from,
      }),
    );
    return;
  }
  if (cmd === "consumos-producto") {
    const categoria = encodeURIComponent(rest[0] || "");
    const producto = encodeURIComponent(rest[1] || "");
    if (!categoria || !producto) {
      throw new Error("Uso: node qdv-api.mjs --from +54911… consumos-producto <categoria> <producto>");
    }
    process.stdout.write(
      await request(
        `/api/v1/stock/consumos/producto?categoria=${categoria}&producto=${producto}`,
        { auth: true, from },
      ),
    );
    return;
  }
  if (cmd === "preview") {
    const moduleName = rest[0] || "";
    const payloadRaw = rest[1] || "{}";
    const source = rest[2] || "texto";
    if (!moduleName) {
      throw new Error("Uso: node qdv-api.mjs --from +54911… preview <modulo> '<json>' [texto|audio|foto]");
    }
    let payload;
    try {
      payload = JSON.parse(payloadRaw);
    } catch (err) {
      throw new Error(`payload JSON inválido: ${err.message}`);
    }
    process.stdout.write(
      await request("/api/v1/intents/preview", {
        auth: true,
        from,
        method: "POST",
        body: { module: moduleName, payload, source },
      }),
    );
    return;
  }
  if (cmd === "confirm") {
    const confirmToken = rest[0] || "";
    if (!confirmToken) {
      throw new Error("Uso: node qdv-api.mjs --from +54911… confirm <confirm_token>");
    }
    process.stdout.write(
      await request("/api/v1/intents/confirm", {
        auth: true,
        from,
        method: "POST",
        body: { confirm_token: confirmToken },
      }),
    );
    return;
  }

  const spec = GET_COMMANDS[cmd];
  if (!spec) usage();
  process.stdout.write(await request(spec.path, { auth: spec.auth, from }));
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
