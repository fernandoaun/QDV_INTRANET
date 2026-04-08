import sqlite3
import json
import hashlib
import colorsys
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Tuple

from qdv_salmuera.config import settings as cfg


def _parse_voltajes_cell_list(raw: Any) -> List[Any]:
    """Parsea voltajes_json de SQLite; nunca lanza por JSON inválido."""
    if raw is None:
        return []
    if isinstance(raw, str) and not raw.strip():
        return []
    try:
        v = json.loads(raw) if isinstance(raw, str) else raw
        return v if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def normalize_tipo_producto(tipo: Any) -> str:
    """
    Valores canónicos en DB y UI: "Filtro" o "Normal" (solo esta capitalización).
    Acepta entradas legacy: filtro, FILTRO, normal, etc.
    """
    if tipo is None:
        return "Normal"
    s = str(tipo).strip()
    if not s:
        return "Normal"
    t = s.lower()
    if t == "filtro":
        return "Filtro"
    return "Normal"


def _hue_from_hex(hex_c: str) -> float:
    h = (hex_c or "").strip().lstrip("#")
    if len(h) != 6:
        return 0.0
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    hh, _ll, _ss = colorsys.rgb_to_hls(r, g, b)
    return float(hh)


def _hue_distance(a: float, b: float) -> float:
    d = abs(a - b)
    return min(d, 1.0 - d)


def _color_hex_from_hue(h: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h % 1.0, 0.42, 0.64)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def _allocate_product_color_hex(nombre_clave: str, existing_hexes: List[str]) -> str:
    """Hue base por hash; si choca con colores existentes, avanza en pasos áureos."""
    existing_hues: List[float] = []
    for hx in existing_hexes:
        try:
            existing_hues.append(_hue_from_hex(hx))
        except ValueError:
            continue
    digest = hashlib.sha256(nombre_clave.encode("utf-8")).digest()
    n = int.from_bytes(digest[:4], "big")
    base_hue = (n % 10_000) / 10_000.0
    phi = 0.618033988749895
    for k in range(36):
        h = (base_hue + k * phi) % 1.0
        if not existing_hues or all(_hue_distance(h, eh) > 0.055 for eh in existing_hues):
            return _color_hex_from_hue(h)
    return _color_hex_from_hue(base_hue)

# =========================
# DB — SQLite local (solo app de escritorio; ver README del repositorio)
# =========================
class DB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()
        self._seed_operators_if_empty()
        self._seed_default_admin_if_needed()
        self._seed_columnas_intercambio_if_needed()

    def _connect(self):
        con = sqlite3.connect(self.db_path)
        try:
            con.execute("PRAGMA foreign_keys = ON;")
        except Exception:
            pass
        return con
    

    def _init_schema(self):
        with self._connect() as con:
            cur = con.cursor()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS operadores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL UNIQUE,
                    created_at_iso TEXT NOT NULL
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_operadores_nombre ON operadores(nombre);")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS salmuera_registros (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha_iso TEXT NOT NULL,
                    hora_hm TEXT NOT NULL,
                    electrolizador INTEGER NOT NULL,
                    cantidad_celdas INTEGER NOT NULL,
                    turno TEXT NOT NULL,
                    voltajes_json TEXT NOT NULL,
                    voltaje_total REAL NOT NULL,
                    amperaje REAL NOT NULL,
                    caudal_agua_l_h REAL NOT NULL,
                    caudal_salmuera_l_h REAL NOT NULL,
                    hipo_conc REAL NOT NULL,
                    hipo_exceso_soda REAL NOT NULL,
                    sal_temp REAL NOT NULL,
                    sal_conc REAL NOT NULL,
                    sal_ph REAL NOT NULL,
                    soda_conc REAL NOT NULL,
                    declor_ph REAL NOT NULL,
                    operador TEXT NOT NULL,
                    lote TEXT,
                    observaciones TEXT,
                    atraso_motivo TEXT,
                    created_at_iso TEXT NOT NULL
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_salmuera_fecha ON salmuera_registros(fecha_iso);")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS bolson_registros (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha_iso TEXT NOT NULL,
                    hora_hm TEXT NOT NULL,
                    created_at_iso TEXT NOT NULL
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_bolson_fecha ON bolson_registros(fecha_iso);")

            # =========================
            # Reactor (nuevo módulo)
            # =========================
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reactor_registros (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha_iso TEXT NOT NULL,
                    hora_hm TEXT NOT NULL,
                    operador TEXT NOT NULL,
                    lote TEXT NOT NULL,
                    ph REAL NOT NULL,
                    temperatura REAL NOT NULL,
                    densidad REAL NOT NULL,
                    concentracion_tabla REAL NOT NULL,
                    exceso_naoh REAL NOT NULL,
                    exceso_na2co3 REAL NOT NULL,
                    observaciones TEXT,
                    created_at_iso TEXT NOT NULL
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reactor_fecha ON reactor_registros(fecha_iso);")

            # =========================
            # Control de agua (nuevo módulo)
            # =========================
            # Permitir múltiples análisis por turno:
            # - Creamos la tabla SIN UNIQUE(fecha_iso, turno)
            # - Migramos automáticamente si existe una versión vieja con UNIQUE.
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agua_registros (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha_iso TEXT NOT NULL,
                    hora_hm TEXT NOT NULL,
                    turno TEXT NOT NULL,
                    operador TEXT NOT NULL,
                    lote TEXT NOT NULL,
                    numero_columna INTEGER NOT NULL,
                    temperatura REAL NOT NULL,
                    dureza REAL NOT NULL,
                    observaciones TEXT,
                    created_at_iso TEXT NOT NULL
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_agua_fecha_turno ON agua_registros(fecha_iso, turno);")

            # =========================
            # Estado columnas de intercambio iónico
            # =========================
            cur.execute("""
                CREATE TABLE IF NOT EXISTS columnas_intercambio_ionico (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    columna_numero INTEGER NOT NULL CHECK (columna_numero IN (1,2,3)),
                    estado TEXT NOT NULL,
                    fecha_regeneracion TEXT,
                    hora_regeneracion TEXT,
                    dureza_salida_ppm REAL,
                    dureza_post_regeneracion_ppm REAL,
                    observaciones TEXT,
                    created_at_iso TEXT NOT NULL,
                    updated_at_iso TEXT NOT NULL
                );
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_col_intercambio_col_created ON columnas_intercambio_ionico(columna_numero, created_at_iso);"
            )

            # Migración: si la tabla existente tiene UNIQUE(fecha_iso, turno), recrearla sin esa restricción.
            try:
                cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='agua_registros';")
                row = cur.fetchone()
                sql = (row[0] or "") if row else ""
                if "UNIQUE" in sql.upper() and "FECHA_ISO" in sql.upper() and "TURNO" in sql.upper():
                    cur.execute("ALTER TABLE agua_registros RENAME TO agua_registros_old;")
                    cur.execute("""
                        CREATE TABLE agua_registros (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            fecha_iso TEXT NOT NULL,
                            hora_hm TEXT NOT NULL,
                            turno TEXT NOT NULL,
                            operador TEXT NOT NULL,
                            lote TEXT NOT NULL,
                            numero_columna INTEGER NOT NULL,
                            temperatura REAL NOT NULL,
                            dureza REAL NOT NULL,
                            observaciones TEXT,
                            created_at_iso TEXT NOT NULL
                        );
                    """)
                    cur.execute("""
                        INSERT INTO agua_registros (
                            id, fecha_iso, hora_hm, turno, operador, lote,
                            numero_columna, temperatura, dureza, observaciones, created_at_iso
                        )
                        SELECT
                            id, fecha_iso, hora_hm, turno, operador, lote,
                            numero_columna, temperatura, dureza, observaciones, created_at_iso
                        FROM agua_registros_old;
                    """)
                    cur.execute("DROP TABLE agua_registros_old;")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_agua_fecha_turno ON agua_registros(fecha_iso, turno);")
            except Exception:
                # Si algo falla en la migración, no frenamos el arranque; la app seguirá con el esquema actual.
                pass

            # Migración simple: agregar columna atraso_motivo si no existe
            try:
                cur.execute("PRAGMA table_info(salmuera_registros);")
                cols = [row[1] for row in cur.fetchall()]
                if "atraso_motivo" not in cols:
                    cur.execute("ALTER TABLE salmuera_registros ADD COLUMN atraso_motivo TEXT;")
                if "lote" not in cols:
                    cur.execute("ALTER TABLE salmuera_registros ADD COLUMN lote TEXT;")
            except Exception:
                pass

            # =========================
            # Autenticación / usuarios
            # =========================
            cur.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_hash TEXT NOT NULL,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    activo INTEGER NOT NULL DEFAULT 1,
                    created_at_iso TEXT NOT NULL
                );
            """)
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_username ON usuarios(username);")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS permisos_usuario (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    permiso TEXT NOT NULL,
                    habilitado INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(user_id, permiso),
                    FOREIGN KEY (user_id) REFERENCES usuarios(id) ON DELETE CASCADE
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_permisos_user ON permisos_usuario(user_id);")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS productos_catalogo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    categoria TEXT NOT NULL CHECK (categoria IN ('materia_prima', 'laboratorio')),
                    nombre_producto TEXT NOT NULL,
                    tipo_producto TEXT NOT NULL DEFAULT 'Normal',
                    activo INTEGER NOT NULL DEFAULT 1,
                    created_at_iso TEXT NOT NULL,
                    UNIQUE(categoria, nombre_producto)
                );
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_productos_catalogo_categoria ON productos_catalogo(categoria, activo, nombre_producto);"
            )

            cur.execute("""
                CREATE TABLE IF NOT EXISTS ingresos_stock (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    categoria TEXT NOT NULL CHECK (categoria IN ('materia_prima', 'laboratorio')),
                    producto TEXT NOT NULL,
                    marca TEXT NOT NULL,
                    vencimiento TEXT NOT NULL,
                    lote TEXT NOT NULL,
                    cantidad REAL NOT NULL CHECK (cantidad > 0),
                    fecha TEXT NOT NULL,
                    hora TEXT NOT NULL,
                    operador TEXT NOT NULL,
                    created_at_iso TEXT NOT NULL
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ingresos_stock_cat_prod ON ingresos_stock(categoria, producto, marca);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ingresos_stock_fecha ON ingresos_stock(fecha, hora);")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS consumos_stock (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    categoria TEXT NOT NULL CHECK (categoria IN ('materia_prima', 'laboratorio')),
                    producto TEXT NOT NULL,
                    marca TEXT NOT NULL,
                    cantidad REAL NOT NULL CHECK (cantidad > 0),
                    fecha TEXT NOT NULL,
                    hora TEXT NOT NULL,
                    operador TEXT NOT NULL,
                    observaciones TEXT,
                    equipo_id INTEGER,
                    created_at_iso TEXT NOT NULL
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_consumos_stock_cat_prod ON consumos_stock(categoria, producto, marca);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_consumos_stock_fecha ON consumos_stock(fecha, hora);")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS equipos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre_equipo TEXT NOT NULL,
                    descripcion TEXT NOT NULL DEFAULT '',
                    activo INTEGER NOT NULL DEFAULT 1,
                    created_at_iso TEXT NOT NULL
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_equipos_activo ON equipos(activo, nombre_equipo);")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS producto_colores (
                    nombre_clave TEXT NOT NULL PRIMARY KEY,
                    nombre_display TEXT NOT NULL,
                    color_hex TEXT NOT NULL,
                    created_at_iso TEXT NOT NULL
                );
            """)

            # Migraciones: columnas nuevas en bases existentes
            try:
                cur.execute("PRAGMA table_info(productos_catalogo);")
                pc_cols = [row[1] for row in cur.fetchall()]
                if pc_cols and "tipo_producto" not in pc_cols:
                    cur.execute(
                        "ALTER TABLE productos_catalogo ADD COLUMN tipo_producto TEXT NOT NULL DEFAULT 'Normal';"
                    )
            except Exception:
                pass
            try:
                cur.execute("SELECT id, tipo_producto FROM productos_catalogo;")
                for rid, t in cur.fetchall():
                    nt = normalize_tipo_producto(t)
                    cur.execute(
                        "UPDATE productos_catalogo SET tipo_producto = ? WHERE id = ?;",
                        (nt, int(rid)),
                    )
            except Exception:
                pass
            try:
                cur.execute("PRAGMA table_info(consumos_stock);")
                cs_cols = [row[1] for row in cur.fetchall()]
                if cs_cols and "equipo_id" not in cs_cols:
                    cur.execute("ALTER TABLE consumos_stock ADD COLUMN equipo_id INTEGER;")
            except Exception:
                pass

            con.commit()

    def _seed_columnas_intercambio_if_needed(self) -> None:
        now = datetime.now()
        now_iso = now.isoformat(timespec="seconds")
        fecha_h = now.strftime("%d/%m/%Y")
        hora_h = now.strftime("%H:%M")
        defaults = {
            1: ("En operación", None, None),
            2: ("Regenerada", fecha_h, hora_h),
            3: ("Regenerada", fecha_h, hora_h),
        }
        with self._connect() as con:
            cur = con.cursor()
            for columna, cfg in defaults.items():
                cur.execute(
                    "SELECT COUNT(*) FROM columnas_intercambio_ionico WHERE columna_numero = ?;",
                    (columna,),
                )
                if int(cur.fetchone()[0]) > 0:
                    continue
                estado, fecha_reg, hora_reg = cfg
                cur.execute(
                    """
                    INSERT INTO columnas_intercambio_ionico (
                        columna_numero, estado, fecha_regeneracion, hora_regeneracion,
                        dureza_salida_ppm, dureza_post_regeneracion_ppm, observaciones,
                        created_at_iso, updated_at_iso
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (columna, estado, fecha_reg, hora_reg, None, None, "", now_iso, now_iso),
                )
            con.commit()
    
    def fetch_last_salmuera(self):
        """Devuelve el último registro de salmuera (ORDER BY id DESC LIMIT 1) como dict."""
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT
                    id, fecha_iso, hora_hm,
                    electrolizador, cantidad_celdas, turno,
                    voltajes_json, voltaje_total,
                    amperaje, caudal_agua_l_h, caudal_salmuera_l_h,
                    hipo_conc, hipo_exceso_soda,
                    sal_temp, sal_conc, sal_ph,
                    soda_conc, declor_ph,
                    operador, observaciones, atraso_motivo,
                    created_at_iso
                FROM salmuera_registros
                ORDER BY id DESC
                LIMIT 1;
            """)
            r = cur.fetchone()

        if not r:
            return None

        return {
            "id": r[0],
            "fecha_iso": r[1],
            "hora_hm": r[2],
            "electrolizador": r[3],
            "cantidad_celdas": r[4],
            "turno": r[5],
            "voltajes_celdas": _parse_voltajes_cell_list(r[6]),
            "voltaje_total": r[7],
            "amperaje": r[8],
            "caudal_agua_l_h": r[9],
            "caudal_salmuera_l_h": r[10],
            "hipo_conc": r[11],
            "hipo_exceso_soda": r[12],
            "sal_temp": r[13],
            "sal_conc": r[14],
            "sal_ph": r[15],
            "soda_conc": r[16],
            "declor_ph": r[17],
            "operador": r[18],
            "observaciones": r[19],
            "atraso_motivo": r[20],
            "created_at_iso": r[21],
        }


    def fetch_last_salmuera_by_electrolizador(self, electrolizador: int, limit: int = 10):
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT id, electrolizador, cantidad_celdas
                FROM salmuera_registros
                WHERE electrolizador = ?
                ORDER BY id DESC
                LIMIT ?;
            """, (electrolizador, limit))
            rows = cur.fetchall()

        return [
            {
                "id": r[0],
                "electrolizador": r[1],
                "cantidad_celdas": r[2],
            }
            for r in rows
        ]

    def _seed_operators_if_empty(self):
        existing = self.fetch_operadores()
        if existing:
            return
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as con:
            cur = con.cursor()
            for name in cfg.DEFAULT_OPERATORS:
                cur.execute(
                    "INSERT OR IGNORE INTO operadores (nombre, created_at_iso) VALUES (?, ?);",
                    (name, now),
                )
            con.commit()

    def fetch_operadores(self) -> List[str]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("SELECT nombre FROM operadores ORDER BY nombre COLLATE NOCASE ASC;")
            rows = cur.fetchall()
        return [r[0] for r in rows]

    def add_operador(self, nombre: str) -> None:
        nombre = nombre.strip()
        if not nombre:
            raise ValueError("Nombre de operador vacío.")
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("INSERT INTO operadores (nombre, created_at_iso) VALUES (?, ?);", (nombre, now))
            con.commit()

    def insert_bolson_now(self) -> Dict[str, Any]:
        now = datetime.now()
        fecha_iso = now.strftime("%Y-%m-%d")
        hora_hm = now.strftime("%H:%M")
        created = now.isoformat(timespec="seconds")

        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                INSERT INTO bolson_registros (fecha_iso, hora_hm, created_at_iso)
                VALUES (?, ?, ?);
            """, (fecha_iso, hora_hm, created))
            rid = cur.lastrowid
            con.commit()

        return {"id": rid, "fecha_iso": fecha_iso, "hora_hm": hora_hm, "created_at_iso": created}

    def fetch_last_bolson(self) -> Optional[Dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT id, fecha_iso, hora_hm, created_at_iso
                FROM bolson_registros
                ORDER BY id DESC
                LIMIT 1;
            """)
            r = cur.fetchone()
        if not r:
            return None
        return {"id": r[0], "fecha_iso": r[1], "hora_hm": r[2], "created_at_iso": r[3]}

    def fetch_bolson_all(self) -> List[Dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT id, fecha_iso, hora_hm, created_at_iso
                FROM bolson_registros
                ORDER BY id DESC;
            """)
            rows = cur.fetchall()
        return [{"id": r[0], "fecha_iso": r[1], "hora_hm": r[2], "created_at_iso": r[3]} for r in rows]


    def insert_salmuera(self, data):

        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                INSERT INTO salmuera_registros (
                    fecha_iso, hora_hm, electrolizador, cantidad_celdas, turno,
                    voltajes_json, voltaje_total,
                    amperaje, caudal_agua_l_h, caudal_salmuera_l_h,
                    hipo_conc, hipo_exceso_soda,
                    sal_temp, sal_conc, sal_ph,
                    soda_conc, declor_ph,
                    operador, lote, observaciones, atraso_motivo,
                    created_at_iso
                ) VALUES (
                    ?,?,?,?,?,   ?,?,
                    ?,?,?,      ?,?,
                    ?,?,?,      ?,?,
                    ?,?,?,?,      ?
                );
            """, (
                data["fecha_iso"],
                data["hora_hm"],
                data["electrolizador"],
                data["cantidad_celdas"],
                data["turno"],

                json.dumps(data["voltajes_celdas"], ensure_ascii=False),
                data["voltaje_total"],

                data["amperaje"],
                data["caudal_agua_l_h"],
                data["caudal_salmuera_l_h"],

                data["hipo_conc"],
                data["hipo_exceso_soda"],

                data["sal_temp"],
                data["sal_conc"],
                data["sal_ph"],

                data["soda_conc"],
                data["declor_ph"],

                data["operador"],
                data.get("lote", ""),
                data.get("observaciones", ""),
                data.get("atraso_motivo", ""),

                data["created_at_iso"],
            ))
            con.commit()



    def update_salmuera_by_id(self, rid: int, data: Dict[str, Any]) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                UPDATE salmuera_registros SET
                    fecha_iso = ?,
                    hora_hm = ?,
                    electrolizador = ?,
                    cantidad_celdas = ?,
                    turno = ?,
                    voltajes_json = ?,
                    voltaje_total = ?,
                    amperaje = ?,
                    caudal_agua_l_h = ?,
                    caudal_salmuera_l_h = ?,
                    hipo_conc = ?,
                    hipo_exceso_soda = ?,
                    sal_temp = ?,
                    sal_conc = ?,
                    sal_ph = ?,
                    soda_conc = ?,
                    declor_ph = ?,
                    operador = ?,
                    lote = ?,
                    observaciones = ?,
                    atraso_motivo = ?
                WHERE id = ?;
            """, (
                data["fecha_iso"],
                data["hora_hm"],
                data["electrolizador"],
                data["cantidad_celdas"],
                data["turno"],
                json.dumps(data["voltajes_celdas"], ensure_ascii=False),
                data["voltaje_total"],
                data["amperaje"],
                data["caudal_agua_l_h"],
                data["caudal_salmuera_l_h"],
                data["hipo_conc"],
                data["hipo_exceso_soda"],
                data["sal_temp"],
                data["sal_conc"],
                data["sal_ph"],
                data["soda_conc"],
                data["declor_ph"],
                data["operador"],
                data.get("lote", ""),
                data.get("observaciones", ""),
                data.get("atraso_motivo", ""),
                rid
            ))
            con.commit()

    def delete_salmuera_by_id(self, rid: int) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM salmuera_registros WHERE id = ?;", (rid,))
            con.commit()

    def fetch_salmuera_by_id(self, rid: int) -> Optional[Dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT
                    id, fecha_iso, hora_hm, electrolizador, cantidad_celdas, turno,
                    voltajes_json, voltaje_total,
                    amperaje, caudal_agua_l_h, caudal_salmuera_l_h,
                    hipo_conc, hipo_exceso_soda,
                    sal_temp, sal_conc, sal_ph,
                    soda_conc, declor_ph,
                    operador, lote, observaciones, atraso_motivo,
                    created_at_iso
                FROM salmuera_registros
                WHERE id = ?;
            """, (rid,))
            r = cur.fetchone()

        if not r:
            return None

        return {
            "id": r[0],
            "fecha_iso": r[1],
            "hora_hm": r[2],
            "electrolizador": r[3],
            "cantidad_celdas": r[4],
            "turno": r[5],
            "voltajes_celdas": _parse_voltajes_cell_list(r[6]),
            "voltaje_total": r[7],
            "amperaje": r[8],
            "caudal_agua_l_h": r[9],
            "caudal_salmuera_l_h": r[10],
            "hipo_conc": r[11],
            "hipo_exceso_soda": r[12],
            "sal_temp": r[13],
            "sal_conc": r[14],
            "sal_ph": r[15],
            "soda_conc": r[16],
            "declor_ph": r[17],
            "operador": r[18],
            "lote": r[19] or "",
            "observaciones": r[20] or "",
            "atraso_motivo": r[21] or "",
            "created_at_iso": r[22],
        }

    def fetch_salmuera_by_date(self, fecha_iso: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT
                    id, fecha_iso, hora_hm, electrolizador, cantidad_celdas, turno,
                    voltajes_json, voltaje_total,
                    amperaje, caudal_agua_l_h, caudal_salmuera_l_h,
                    hipo_conc, hipo_exceso_soda,
                    sal_temp, sal_conc, sal_ph,
                    soda_conc, declor_ph,
                    operador, lote, observaciones,
                    created_at_iso
                FROM salmuera_registros
                WHERE fecha_iso = ?
                ORDER BY id ASC;
            """, (fecha_iso,))
            rows = cur.fetchall()

        out = []
        for r in rows:
            out.append({
                "id": r[0],
                "fecha_iso": r[1],
                "hora_hm": r[2],
                "electrolizador": r[3],
                "cantidad_celdas": r[4],
                "turno": r[5],
                "voltajes_celdas": _parse_voltajes_cell_list(r[6]),
                "voltaje_total": r[7],
                "amperaje": r[8],
                "caudal_agua_l_h": r[9],
                "caudal_salmuera_l_h": r[10],
                "hipo_conc": r[11],
                "hipo_exceso_soda": r[12],
                "sal_temp": r[13],
                "sal_conc": r[14],
                "sal_ph": r[15],
                "soda_conc": r[16],
                "declor_ph": r[17],
                "operador": r[18],
                "lote": r[19] or "",
                "observaciones": r[20] or "",
                "created_at_iso": r[21]
            })
        return out

    def fetch_salmuera_range(self, fecha_desde_iso: str, fecha_hasta_iso: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT
                    id, fecha_iso, hora_hm, electrolizador, cantidad_celdas, turno,
                    voltajes_json, voltaje_total,
                    amperaje, caudal_agua_l_h, caudal_salmuera_l_h,
                    hipo_conc, hipo_exceso_soda,
                    sal_temp, sal_conc, sal_ph,
                    soda_conc, declor_ph,
                    operador, lote, observaciones, COALESCE(atraso_motivo, ''),
                    created_at_iso
                FROM salmuera_registros
                WHERE fecha_iso BETWEEN ? AND ?
                ORDER BY fecha_iso ASC, hora_hm ASC, id ASC;
            """, (fecha_desde_iso, fecha_hasta_iso))
            rows = cur.fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "id": r[0],
                "fecha_iso": r[1],
                "hora_hm": r[2],
                "electrolizador": r[3],
                "cantidad_celdas": r[4],
                "turno": r[5],
                "voltajes_celdas": _parse_voltajes_cell_list(r[6]),
                "voltaje_total": r[7],
                "amperaje": r[8],
                "caudal_agua_l_h": r[9],
                "caudal_salmuera_l_h": r[10],
                "hipo_conc": r[11],
                "hipo_exceso_soda": r[12],
                "sal_temp": r[13],
                "sal_conc": r[14],
                "sal_ph": r[15],
                "soda_conc": r[16],
                "declor_ph": r[17],
                "operador": r[18],
                "lote": r[19] or "",
                "observaciones": r[20] or "",
                "atraso_motivo": r[21] or "",
                "created_at_iso": r[22],
            })
        return out

    def get_daily_sample_count(self, module_key: str, fecha_iso: str) -> int:
        table_by_module = {
            "salmuera": "salmuera_registros",
            "reactor": "reactor_registros",
            "agua": "agua_registros",
        }
        table = table_by_module.get((module_key or "").strip())
        if not table:
            raise ValueError("Módulo inválido para cálculo de lote.")
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE fecha_iso = ?;", (fecha_iso,))
            row = cur.fetchone()
            return int(row[0] if row else 0)

    # =========================
    # Reactor (nuevo módulo)
    # =========================
    def insert_reactor(self, data: Dict[str, Any]) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                INSERT INTO reactor_registros (
                    fecha_iso, hora_hm,
                    operador, lote,
                    ph, temperatura, densidad,
                    concentracion_tabla,
                    exceso_naoh, exceso_na2co3,
                    observaciones,
                    created_at_iso
                ) VALUES (
                    ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    ?, ? , ?,
                    ?,
                    ?
                );
            """, (
                data["fecha_iso"],
                data["hora_hm"],
                data["operador"],
                data["lote"],
                data["ph"],
                data["temperatura"],
                data["densidad"],
                data["concentracion_tabla"],
                data["exceso_naoh"],
                data["exceso_na2co3"],
                data.get("observaciones", ""),
                data["created_at_iso"],
            ))
            con.commit()

    def fetch_reactor_by_date(self, fecha_iso: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT
                    id, fecha_iso, hora_hm,
                    operador, lote,
                    ph, temperatura, densidad,
                    concentracion_tabla,
                    exceso_naoh, exceso_na2co3,
                    observaciones,
                    created_at_iso
                FROM reactor_registros
                WHERE fecha_iso = ?
                ORDER BY id ASC;
            """, (fecha_iso,))
            rows = cur.fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "id": r[0],
                "fecha_iso": r[1],
                "hora_hm": r[2],
                "operador": r[3],
                "lote": r[4],
                "ph": r[5],
                "temperatura": r[6],
                "densidad": r[7],
                "concentracion_tabla": r[8],
                "exceso_naoh": r[9],
                "exceso_na2co3": r[10],
                "observaciones": r[11] or "",
                "created_at_iso": r[12],
            })
        return out

    def fetch_reactor_range(self, fecha_desde_iso: str, fecha_hasta_iso: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT
                    id, fecha_iso, hora_hm,
                    operador, lote,
                    ph, temperatura, densidad,
                    concentracion_tabla,
                    exceso_naoh, exceso_na2co3,
                    observaciones,
                    created_at_iso
                FROM reactor_registros
                WHERE fecha_iso BETWEEN ? AND ?
                ORDER BY fecha_iso ASC, id ASC;
            """, (fecha_desde_iso, fecha_hasta_iso))
            rows = cur.fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "id": r[0],
                "fecha_iso": r[1],
                "hora_hm": r[2],
                "operador": r[3],
                "lote": r[4],
                "ph": r[5],
                "temperatura": r[6],
                "densidad": r[7],
                "concentracion_tabla": r[8],
                "exceso_naoh": r[9],
                "exceso_na2co3": r[10],
                "observaciones": r[11] or "",
                "created_at_iso": r[12],
            })
        return out

    def delete_reactor_by_id(self, rid: int) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM reactor_registros WHERE id = ?;", (rid,))
            con.commit()

    # =========================
    # Control de agua (nuevo módulo)
    # =========================
    def insert_agua(self, data: Dict[str, Any]) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                INSERT INTO agua_registros (
                    fecha_iso, hora_hm,
                    turno,
                    operador, lote,
                    numero_columna,
                    temperatura, dureza,
                    observaciones,
                    created_at_iso
                ) VALUES (
                    ?, ?,
                    ?,
                    ?, ?,
                    ?, ? , ?,
                    ?,
                    ?
                );
            """, (
                data["fecha_iso"],
                data["hora_hm"],
                data["turno"],
                data["operador"],
                data["lote"],
                data["numero_columna"],
                data["temperatura"],
                data["dureza"],
                data.get("observaciones", ""),
                data["created_at_iso"],
            ))
            con.commit()

    def fetch_agua_by_date(self, fecha_iso: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT
                    id, fecha_iso, hora_hm, turno,
                    operador, lote, numero_columna,
                    temperatura, dureza,
                    observaciones,
                    created_at_iso
                FROM agua_registros
                WHERE fecha_iso = ?
                ORDER BY id ASC;
            """, (fecha_iso,))
            rows = cur.fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "id": r[0],
                "fecha_iso": r[1],
                "hora_hm": r[2],
                "turno": r[3],
                "operador": r[4],
                "lote": r[5],
                "numero_columna": r[6],
                "temperatura": r[7],
                "dureza": r[8],
                "observaciones": r[9] or "",
                "created_at_iso": r[10],
            })
        return out

    def fetch_agua_by_date_turno(self, fecha_iso: str, turno: str) -> Optional[Dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT
                    id, fecha_iso, hora_hm, turno,
                    operador, lote, numero_columna,
                    temperatura, dureza,
                    observaciones,
                    created_at_iso
                FROM agua_registros
                WHERE fecha_iso = ?
                  AND turno = ?
                ORDER BY id DESC
                LIMIT 1;
            """, (fecha_iso, turno))
            r = cur.fetchone()

        if not r:
            return None

        return {
            "id": r[0],
            "fecha_iso": r[1],
            "hora_hm": r[2],
            "turno": r[3],
            "operador": r[4],
            "lote": r[5],
            "numero_columna": r[6],
            "temperatura": r[7],
            "dureza": r[8],
            "observaciones": r[9] or "",
            "created_at_iso": r[10],
        }

    def fetch_agua_range(self, fecha_desde_iso: str, fecha_hasta_iso: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT
                    id, fecha_iso, hora_hm, turno,
                    operador, lote, numero_columna,
                    temperatura, dureza,
                    observaciones,
                    created_at_iso
                FROM agua_registros
                WHERE fecha_iso BETWEEN ? AND ?
                ORDER BY fecha_iso ASC, id ASC;
            """, (fecha_desde_iso, fecha_hasta_iso))
            rows = cur.fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "id": r[0],
                "fecha_iso": r[1],
                "hora_hm": r[2],
                "turno": r[3],
                "operador": r[4],
                "lote": r[5],
                "numero_columna": r[6],
                "temperatura": r[7],
                "dureza": r[8],
                "observaciones": r[9] or "",
                "created_at_iso": r[10],
            })
        return out

    def delete_agua_by_id(self, rid: int) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM agua_registros WHERE id = ?;", (rid,))
            con.commit()

    def get_latest_estado_columnas(self) -> Dict[int, Dict[str, Any]]:
        def _default_col(col: int) -> Dict[str, Any]:
            return {
                "id": None,
                "columna_numero": col,
                "estado": "En operación",
                "fecha_regeneracion": "",
                "hora_regeneracion": "",
                "dureza_salida_ppm": None,
                "dureza_post_regeneracion_ppm": None,
                "observaciones": "",
                "created_at_iso": "",
                "updated_at_iso": "",
            }

        out: Dict[int, Dict[str, Any]] = {}
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT
                    t.id, t.columna_numero, t.estado, t.fecha_regeneracion, t.hora_regeneracion,
                    t.dureza_salida_ppm, t.dureza_post_regeneracion_ppm, t.observaciones,
                    t.created_at_iso, t.updated_at_iso
                FROM columnas_intercambio_ionico t
                INNER JOIN (
                    SELECT columna_numero, MAX(id) AS mid
                    FROM columnas_intercambio_ionico
                    WHERE columna_numero IN (1, 2, 3)
                    GROUP BY columna_numero
                ) AS m ON t.id = m.mid AND t.columna_numero = m.columna_numero;
                """
            )
            for r in cur.fetchall():
                col = int(r[1])
                out[col] = {
                    "id": r[0],
                    "columna_numero": col,
                    "estado": r[2],
                    "fecha_regeneracion": r[3] or "",
                    "hora_regeneracion": r[4] or "",
                    "dureza_salida_ppm": r[5],
                    "dureza_post_regeneracion_ppm": r[6],
                    "observaciones": r[7] or "",
                    "created_at_iso": r[8],
                    "updated_at_iso": r[9],
                }
            cur.execute(
                """
                SELECT
                    t.columna_numero,
                    t.fecha_regeneracion, t.hora_regeneracion,
                    t.dureza_salida_ppm, t.dureza_post_regeneracion_ppm
                FROM columnas_intercambio_ionico t
                INNER JOIN (
                    SELECT columna_numero, MAX(id) AS mid
                    FROM columnas_intercambio_ionico
                    WHERE columna_numero IN (1, 2, 3) AND estado = 'Regenerada'
                    GROUP BY columna_numero
                ) AS m ON t.id = m.mid AND t.columna_numero = m.columna_numero;
                """
            )
            reg_by_col = {int(r[0]): r for r in cur.fetchall()}

        for col in (1, 2, 3):
            if col not in out:
                out[col] = _default_col(col)
            if col in reg_by_col:
                lr = reg_by_col[col]
                out[col]["fecha_regeneracion"] = lr[1] or ""
                out[col]["hora_regeneracion"] = lr[2] or ""
                out[col]["dureza_salida_ppm"] = lr[3]
                out[col]["dureza_post_regeneracion_ppm"] = lr[4]
        return out

    def save_estado_columna(
        self,
        columna_numero: int,
        estado: str,
        fecha_regeneracion: Optional[str],
        hora_regeneracion: Optional[str],
        dureza_salida_ppm: Optional[float],
        dureza_post_regeneracion_ppm: Optional[float],
        observaciones: str,
    ) -> None:
        estado = (estado or "").strip()
        now = datetime.now()
        now_iso = now.isoformat(timespec="seconds")
        if estado == "Regenerada":
            if not (fecha_regeneracion or "").strip():
                fecha_regeneracion = now.strftime("%d/%m/%Y")
            if not (hora_regeneracion or "").strip():
                hora_regeneracion = now.strftime("%H:%M")
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO columnas_intercambio_ionico (
                    columna_numero, estado, fecha_regeneracion, hora_regeneracion,
                    dureza_salida_ppm, dureza_post_regeneracion_ppm, observaciones,
                    created_at_iso, updated_at_iso
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    int(columna_numero),
                    estado,
                    fecha_regeneracion,
                    hora_regeneracion,
                    dureza_salida_ppm,
                    dureza_post_regeneracion_ppm,
                    (observaciones or "").strip(),
                    now_iso,
                    now_iso,
                ),
            )
            con.commit()

    def fetch_last_reactor(self) -> Optional[Dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT
                    id, fecha_iso, hora_hm,
                    operador, lote,
                    ph, temperatura, densidad,
                    concentracion_tabla,
                    exceso_naoh, exceso_na2co3,
                    observaciones,
                    created_at_iso
                FROM reactor_registros
                ORDER BY id DESC
                LIMIT 1;
            """)
            r = cur.fetchone()

        if not r:
            return None

        return {
            "id": r[0],
            "fecha_iso": r[1],
            "hora_hm": r[2],
            "operador": r[3],
            "lote": r[4],
            "ph": r[5],
            "temperatura": r[6],
            "densidad": r[7],
            "concentracion_tabla": r[8],
            "exceso_naoh": r[9],
            "exceso_na2co3": r[10],
            "observaciones": r[11] or "",
            "created_at_iso": r[12],
        }

    def fetch_last_agua(self) -> Optional[Dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT
                    id, fecha_iso, hora_hm, turno,
                    operador, lote, numero_columna,
                    temperatura, dureza,
                    observaciones,
                    created_at_iso
                FROM agua_registros
                ORDER BY id DESC
                LIMIT 1;
            """)
            r = cur.fetchone()

        if not r:
            return None

        return {
            "id": r[0],
            "fecha_iso": r[1],
            "hora_hm": r[2],
            "turno": r[3],
            "operador": r[4],
            "lote": r[5],
            "numero_columna": r[6],
            "temperatura": r[7],
            "dureza": r[8],
            "observaciones": r[9] or "",
            "created_at_iso": r[10],
        }

    # =========================
    # Autenticación / usuarios
    # =========================
    def _seed_default_admin_if_needed(self) -> None:
        """Crea usuario admin con hash si no hay ningún administrador activo."""
        from qdv_salmuera.auth.passwords import hash_password

        with self._connect() as con:
            cur = con.cursor()
            cur.execute("SELECT COUNT(*) FROM usuarios WHERE is_admin = 1 AND activo = 1;")
            if cur.fetchone()[0] > 0:
                return
            cur.execute("SELECT id FROM usuarios WHERE username = ? COLLATE NOCASE;", ("admin",))
            row = cur.fetchone()
            if row:
                cur.execute(
                    "UPDATE usuarios SET is_admin = 1, activo = 1 WHERE id = ?;",
                    (row[0],),
                )
                con.commit()
                return
            now = datetime.now().isoformat(timespec="seconds")
            ph = hash_password("marquez26")
            cur.execute(
                """
                INSERT INTO usuarios (username, password_hash, is_admin, activo, created_at_iso)
                VALUES (?, ?, ?, ?, ?);
                """,
                ("admin", ph, 1, 1, now),
            )
            con.commit()

    def fetch_usuario_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        u = (username or "").strip()
        if not u:
            return None
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT id, username, password_hash, is_admin, activo, created_at_iso
                FROM usuarios
                WHERE username = ? COLLATE NOCASE
                LIMIT 1;
                """,
                (u,),
            )
            r = cur.fetchone()
        if not r:
            return None
        return {
            "id": r[0],
            "username": r[1],
            "password_hash": r[2],
            "is_admin": int(r[3]),
            "activo": int(r[4]),
            "created_at_iso": r[5],
        }

    def fetch_usuarios_list(self) -> List[Dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT id, username, is_admin, activo, created_at_iso
                FROM usuarios
                ORDER BY username COLLATE NOCASE ASC;
                """
            )
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "username": r[1],
                "is_admin": int(r[2]),
                "activo": int(r[3]),
                "created_at_iso": r[4],
            }
            for r in rows
        ]

    def fetch_usuario_by_id(self, uid: int) -> Optional[Dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT id, username, password_hash, is_admin, activo, created_at_iso
                FROM usuarios WHERE id = ?;
                """,
                (uid,),
            )
            r = cur.fetchone()
        if not r:
            return None
        return {
            "id": r[0],
            "username": r[1],
            "password_hash": r[2],
            "is_admin": int(r[3]),
            "activo": int(r[4]),
            "created_at_iso": r[5],
        }

    def fetch_permisos_habilitados(self, user_id: int) -> List[str]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT permiso FROM permisos_usuario
                WHERE user_id = ? AND habilitado = 1
                ORDER BY permiso ASC;
                """,
                (user_id,),
            )
            return [row[0] for row in cur.fetchall()]

    def fetch_permisos_map(self, user_id: int) -> Dict[str, bool]:
        from qdv_salmuera.auth.permissions import PERMISSION_KEYS

        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                "SELECT permiso, habilitado FROM permisos_usuario WHERE user_id = ?;",
                (user_id,),
            )
            raw = {row[0]: bool(row[1]) for row in cur.fetchall()}
        return {k: bool(raw.get(k, False)) for k in PERMISSION_KEYS}

    def create_usuario(
        self,
        username: str,
        password_hash: str,
        is_admin: int,
        activo: int,
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO usuarios (username, password_hash, is_admin, activo, created_at_iso)
                VALUES (?, ?, ?, ?, ?);
                """,
                (username.strip(), password_hash, int(bool(is_admin)), int(bool(activo)), now),
            )
            rid = cur.lastrowid
            con.commit()
        return int(rid)

    def update_usuario_core(self, uid: int, username: str, is_admin: int, activo: int) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                UPDATE usuarios SET username = ?, is_admin = ?, activo = ?
                WHERE id = ?;
                """,
                (username.strip(), int(bool(is_admin)), int(bool(activo)), uid),
            )
            con.commit()

    def update_usuario_password(self, uid: int, password_hash: str) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                "UPDATE usuarios SET password_hash = ? WHERE id = ?;",
                (password_hash, uid),
            )
            con.commit()

    def delete_usuario(self, uid: int) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM usuarios WHERE id = ?;", (uid,))
            con.commit()

    def count_admins_activos(self) -> int:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM usuarios WHERE is_admin = 1 AND activo = 1;"
            )
            return int(cur.fetchone()[0])

    def set_permisos_usuario(self, user_id: int, permisos: Dict[str, bool]) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM permisos_usuario WHERE user_id = ?;", (user_id,))
            for key, on in permisos.items():
                if not on:
                    continue
                cur.execute(
                    """
                    INSERT INTO permisos_usuario (user_id, permiso, habilitado)
                    VALUES (?, ?, 1);
                    """,
                    (user_id, key),
                )
            con.commit()

    # =========================
    # Stock / consumos
    # =========================
    def _validate_categoria_stock(self, categoria: str) -> str:
        cat = (categoria or "").strip().lower()
        if cat not in ("materia_prima", "laboratorio"):
            raise ValueError("Categoría inválida.")
        return cat

    def get_productos_por_categoria(self, categoria: str) -> List[str]:
        cat = self._validate_categoria_stock(categoria)
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT nombre_producto
                FROM productos_catalogo
                WHERE categoria = ? AND activo = 1
                ORDER BY nombre_producto COLLATE NOCASE ASC;
                """,
                (cat,),
            )
            rows = cur.fetchall()
        return [str(r[0]) for r in rows]

    def create_new_product(self, categoria: str, nombre_producto: str, tipo_producto: str = "Normal") -> int:
        cat = self._validate_categoria_stock(categoria)
        nombre = (nombre_producto or "").strip()
        if not nombre:
            raise ValueError("Nombre de producto vacío.")
        tipo = normalize_tipo_producto(tipo_producto)
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                INSERT OR IGNORE INTO productos_catalogo (categoria, nombre_producto, tipo_producto, activo, created_at_iso)
                VALUES (?, ?, ?, 1, ?);
                """,
                (cat, nombre, tipo, now),
            )
            if cur.lastrowid:
                rid = int(cur.lastrowid)
            else:
                cur.execute(
                    """
                    SELECT id FROM productos_catalogo
                    WHERE categoria = ? AND nombre_producto = ?;
                    """,
                    (cat, nombre),
                )
                row = cur.fetchone()
                if not row:
                    raise RuntimeError("No se pudo crear ni recuperar el producto.")
                rid = int(row[0])
                cur.execute("UPDATE productos_catalogo SET activo = 1 WHERE id = ?;", (rid,))
            con.commit()
        return rid

    def is_filter_product(self, producto_id: int) -> bool:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                "SELECT tipo_producto FROM productos_catalogo WHERE id = ?;",
                (int(producto_id),),
            )
            row = cur.fetchone()
        if not row:
            return False
        return normalize_tipo_producto(row[0]) == "Filtro"

    def is_filter_product_by_categoria_nombre(self, categoria: str, nombre_producto: str) -> bool:
        cat = self._validate_categoria_stock(categoria)
        nombre = (nombre_producto or "").strip()
        if not nombre:
            return False
        key = nombre.lower()
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT tipo_producto FROM productos_catalogo
                WHERE categoria = ?
                  AND LOWER(TRIM(nombre_producto)) = ?
                  AND activo = 1;
                """,
                (cat, key),
            )
            row = cur.fetchone()
        if not row:
            return False
        return normalize_tipo_producto(row[0]) == "Filtro"

    def fetch_catalogo_productos_admin(self) -> List[Dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT id, categoria, nombre_producto, COALESCE(tipo_producto, 'Normal'), activo
                FROM productos_catalogo
                ORDER BY categoria ASC, nombre_producto COLLATE NOCASE ASC;
                """
            )
            rows = cur.fetchall()
        return [
            {
                "id": int(r[0]),
                "categoria": str(r[1]),
                "nombre_producto": str(r[2]),
                "tipo_producto": normalize_tipo_producto(str(r[3])),
                "activo": int(r[4]),
            }
            for r in rows
        ]

    def update_producto_tipo_catalogo(self, producto_id: int, tipo_producto: str) -> None:
        tipo = normalize_tipo_producto(tipo_producto)
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                "UPDATE productos_catalogo SET tipo_producto = ? WHERE id = ?;",
                (tipo, int(producto_id)),
            )
            con.commit()

    def get_equipos_activos(self) -> List[Dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT id, nombre_equipo
                FROM equipos
                WHERE activo = 1
                ORDER BY nombre_equipo COLLATE NOCASE ASC;
                """
            )
            rows = cur.fetchall()
        return [{"id": int(r[0]), "nombre_equipo": str(r[1])} for r in rows]

    def get_equipos_todos(self) -> List[Dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT id, nombre_equipo, COALESCE(descripcion, ''), activo
                FROM equipos
                ORDER BY nombre_equipo COLLATE NOCASE ASC;
                """
            )
            rows = cur.fetchall()
        return [
            {
                "id": int(r[0]),
                "nombre_equipo": str(r[1]),
                "descripcion": str(r[2]),
                "activo": int(r[3]),
            }
            for r in rows
        ]

    def create_equipo(self, nombre_equipo: str, descripcion: str = "") -> int:
        nombre = (nombre_equipo or "").strip()
        if not nombre:
            raise ValueError("El nombre del equipo es obligatorio.")
        desc = (descripcion or "").strip()
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO equipos (nombre_equipo, descripcion, activo, created_at_iso)
                VALUES (?, ?, 1, ?);
                """,
                (nombre, desc, now),
            )
            rid = int(cur.lastrowid)
            con.commit()
        return rid

    def update_equipo(self, equipo_id: int, nombre_equipo: str, descripcion: str, activo: int) -> None:
        nombre = (nombre_equipo or "").strip()
        if not nombre:
            raise ValueError("El nombre del equipo es obligatorio.")
        desc = (descripcion or "").strip()
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                UPDATE equipos SET nombre_equipo = ?, descripcion = ?, activo = ?
                WHERE id = ?;
                """,
                (nombre, desc, int(bool(activo)), int(equipo_id)),
            )
            con.commit()

    def validate_consumo_equipo(
        self,
        categoria: str,
        producto: str,
        equipo_id: Optional[int],
    ) -> Optional[int]:
        """
        Si el producto es tipo filtro, exige equipo_id válido y activo.
        Devuelve equipo_id normalizado o None si no aplica.
        """
        cat = self._validate_categoria_stock(categoria)
        prod = (producto or "").strip()
        if not self.is_filter_product_by_categoria_nombre(cat, prod):
            return None
        if equipo_id is None:
            raise ValueError("Debe seleccionar el equipo donde se instalará el filtro.")
        eid = int(equipo_id)
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                "SELECT id FROM equipos WHERE id = ? AND activo = 1;",
                (eid,),
            )
            if not cur.fetchone():
                raise ValueError("El equipo seleccionado no es válido o está inactivo.")
        return eid

    def save_ingreso_stock(
        self,
        categoria: str,
        producto: str,
        marca: str,
        vencimiento: str,
        lote: str,
        cantidad: float,
        operador: str,
    ) -> Dict[str, Any]:
        cat = self._validate_categoria_stock(categoria)
        prod = (producto or "").strip()
        mar = (marca or "").strip()
        ven = (vencimiento or "").strip()
        lot = (lote or "").strip()
        op = (operador or "").strip() or "sistema"
        qty = float(cantidad)
        if not prod:
            raise ValueError("Producto obligatorio.")
        if not mar:
            raise ValueError("Marca obligatoria.")
        if not ven:
            raise ValueError("Vencimiento obligatorio.")
        if not lot:
            raise ValueError("Lote obligatorio.")
        if qty <= 0:
            raise ValueError("La cantidad debe ser mayor a cero.")

        self.create_new_product(cat, prod)
        now = datetime.now()
        fecha = now.strftime("%Y-%m-%d")
        hora = now.strftime("%H:%M")
        created = now.isoformat(timespec="seconds")

        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO ingresos_stock (
                    categoria, producto, marca, vencimiento, lote, cantidad,
                    fecha, hora, operador, created_at_iso
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (cat, prod, mar, ven, lot, qty, fecha, hora, op, created),
            )
            rid = int(cur.lastrowid)
            con.commit()
        return {"id": rid, "fecha": fecha, "hora": hora, "created_at_iso": created}

    def get_stock_actual(self, categoria: str, producto: str, marca: str) -> float:
        cat = self._validate_categoria_stock(categoria)
        prod = (producto or "").strip()
        mar = (marca or "").strip()
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT COALESCE(SUM(cantidad), 0)
                FROM ingresos_stock
                WHERE categoria = ? AND producto = ? AND marca = ?;
                """,
                (cat, prod, mar),
            )
            ingresos = float(cur.fetchone()[0] or 0.0)
            cur.execute(
                """
                SELECT COALESCE(SUM(cantidad), 0)
                FROM consumos_stock
                WHERE categoria = ? AND producto = ? AND marca = ?;
                """,
                (cat, prod, mar),
            )
            consumos = float(cur.fetchone()[0] or 0.0)
        return max(ingresos - consumos, 0.0)

    def get_marcas_por_producto(self, categoria: str, producto: str) -> List[str]:
        cat = self._validate_categoria_stock(categoria)
        prod = (producto or "").strip()
        if not prod:
            return []
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT ing.marca
                FROM (
                    SELECT marca, SUM(cantidad) AS t_ing
                    FROM ingresos_stock
                    WHERE categoria = ? AND producto = ?
                    GROUP BY marca
                ) AS ing
                LEFT JOIN (
                    SELECT marca, SUM(cantidad) AS t_con
                    FROM consumos_stock
                    WHERE categoria = ? AND producto = ?
                    GROUP BY marca
                ) AS con ON ing.marca = con.marca
                WHERE (COALESCE(ing.t_ing, 0) - COALESCE(con.t_con, 0)) > 0
                ORDER BY ing.marca COLLATE NOCASE ASC;
                """,
                (cat, prod, cat, prod),
            )
            return [str(r[0]) for r in cur.fetchall()]

    def save_consumo_stock(
        self,
        categoria: str,
        producto: str,
        marca: str,
        cantidad: float,
        operador: str,
        observaciones: str = "",
        equipo_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        cat = self._validate_categoria_stock(categoria)
        prod = (producto or "").strip()
        mar = (marca or "").strip()
        op = (operador or "").strip() or "sistema"
        obs = (observaciones or "").strip()
        qty = float(cantidad)
        if not prod:
            raise ValueError("Producto obligatorio.")
        if not mar:
            raise ValueError("Marca obligatoria.")
        if qty <= 0:
            raise ValueError("La cantidad debe ser mayor a cero.")
        stock_actual = self.get_stock_actual(cat, prod, mar)
        if stock_actual <= 0:
            raise ValueError("No hay stock disponible.")
        if qty > stock_actual:
            raise ValueError("No puede consumir más de lo disponible.")

        equipo_sql: Optional[int] = self.validate_consumo_equipo(cat, prod, equipo_id)
        if not self.is_filter_product_by_categoria_nombre(cat, prod):
            equipo_sql = None

        now = datetime.now()
        fecha = now.strftime("%Y-%m-%d")
        hora = now.strftime("%H:%M")
        created = now.isoformat(timespec="seconds")
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO consumos_stock (
                    categoria, producto, marca, cantidad, fecha, hora,
                    operador, observaciones, equipo_id, created_at_iso
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (cat, prod, mar, qty, fecha, hora, op, obs, equipo_sql, created),
            )
            rid = int(cur.lastrowid)
            con.commit()
        return {"id": rid, "fecha": fecha, "hora": hora, "created_at_iso": created}

    def get_consumos_ultimos_30_dias(self) -> List[Dict[str, Any]]:
        """
        Consumos agregados por día y producto en los últimos 30 días (incluye hoy).
        Cada fila: fecha_iso (YYYY-MM-DD), producto, cantidad_total.
        """
        today = date.today()
        desde = (today - timedelta(days=29)).strftime("%Y-%m-%d")
        hasta = today.strftime("%Y-%m-%d")
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT fecha, producto, COALESCE(SUM(cantidad), 0) AS cantidad_total
                FROM consumos_stock
                WHERE fecha >= ? AND fecha <= ?
                GROUP BY fecha, producto
                ORDER BY fecha ASC, producto COLLATE NOCASE ASC;
                """,
                (desde, hasta),
            )
            rows = cur.fetchall()
        return [
            {"fecha_iso": str(r[0]), "producto": str(r[1]), "cantidad_total": float(r[2] or 0.0)}
            for r in rows
        ]

    def get_or_create_product_color(self, product_name: str) -> str:
        """
        Color persistente por producto (clave = nombre en minúsculas).
        Primera vez: elige un hex estable y lo guarda; siguientes lecturas desde DB.
        """
        display = (product_name or "").strip()
        key = display.lower()
        if not key:
            return "#888888"
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("SELECT color_hex FROM producto_colores WHERE nombre_clave = ?;", (key,))
            row = cur.fetchone()
            if row:
                return str(row[0])
            cur.execute("SELECT color_hex FROM producto_colores;")
            existing = [str(r[0]) for r in cur.fetchall()]
            hex_c = _allocate_product_color_hex(key, existing)
            now = datetime.now().isoformat(timespec="seconds")
            try:
                cur.execute(
                    """
                    INSERT INTO producto_colores (nombre_clave, nombre_display, color_hex, created_at_iso)
                    VALUES (?, ?, ?, ?);
                    """,
                    (key, display or key, hex_c, now),
                )
                con.commit()
            except sqlite3.IntegrityError:
                con.rollback()
                cur.execute("SELECT color_hex FROM producto_colores WHERE nombre_clave = ?;", (key,))
                row2 = cur.fetchone()
                if row2:
                    return str(row2[0])
                raise
            return hex_c

    def get_consumos_detalle_por_fecha(self, fecha_iso: str) -> List[Dict[str, Any]]:
        """Movimientos de consumo de un día; incluye equipo si el registro lo tiene."""
        fecha = (fecha_iso or "").strip()
        if not fecha:
            return []
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT c.hora, c.cantidad, c.producto, c.equipo_id, e.nombre_equipo
                FROM consumos_stock c
                LEFT JOIN equipos e ON e.id = c.equipo_id
                WHERE c.fecha = ?
                ORDER BY c.hora ASC, c.id ASC;
                """,
                (fecha,),
            )
            rows = cur.fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            eq_name = r[4]
            out.append(
                {
                    "hora": str(r[0]),
                    "cantidad": float(r[1] or 0.0),
                    "producto": str(r[2]),
                    "equipo_id": int(r[3]) if r[3] is not None else None,
                    "equipo_nombre": str(eq_name) if eq_name else "",
                }
            )
        return out

    def get_stock_consolidado(self, categoria: str) -> List[Dict[str, Any]]:
        cat = self._validate_categoria_stock(categoria)
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT producto,
                       COALESCE(SUM(cantidad), 0) AS total_ing
                FROM ingresos_stock
                WHERE categoria = ?
                GROUP BY producto;
                """,
                (cat,),
            )
            ing_map = {str(r[0]): float(r[1] or 0.0) for r in cur.fetchall()}
            cur.execute(
                """
                SELECT producto,
                       COALESCE(SUM(cantidad), 0) AS total_con
                FROM consumos_stock
                WHERE categoria = ?
                GROUP BY producto;
                """,
                (cat,),
            )
            con_map = {str(r[0]): float(r[1] or 0.0) for r in cur.fetchall()}

        out: List[Dict[str, Any]] = []
        for producto in sorted(set(ing_map.keys()) | set(con_map.keys()), key=lambda x: x.lower()):
            stock = ing_map.get(producto, 0.0) - con_map.get(producto, 0.0)
            if stock > 0:
                out.append({"producto": producto, "stock": stock})
        return out

    def get_stock_por_marca(self, categoria: str) -> List[Dict[str, Any]]:
        cat = self._validate_categoria_stock(categoria)
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                SELECT producto, marca, COALESCE(SUM(cantidad), 0)
                FROM ingresos_stock
                WHERE categoria = ?
                GROUP BY producto, marca;
                """,
                (cat,),
            )
            ing_rows = {(str(r[0]), str(r[1])): float(r[2] or 0.0) for r in cur.fetchall()}
            cur.execute(
                """
                SELECT producto, marca, COALESCE(SUM(cantidad), 0)
                FROM consumos_stock
                WHERE categoria = ?
                GROUP BY producto, marca;
                """,
                (cat,),
            )
            con_rows = {(str(r[0]), str(r[1])): float(r[2] or 0.0) for r in cur.fetchall()}

        out: List[Dict[str, Any]] = []
        keys = sorted(set(ing_rows.keys()) | set(con_rows.keys()), key=lambda x: (x[0].lower(), x[1].lower()))
        for producto, marca in keys:
            stock = ing_rows.get((producto, marca), 0.0) - con_rows.get((producto, marca), 0.0)
            if stock > 0:
                out.append({"producto": producto, "marca": marca, "stock": stock})
        return out