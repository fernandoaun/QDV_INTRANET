import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from qdv_salmuera.config import settings as cfg

# PEGAR AQUÍ: class DB completa (V4 125–581)
# Luego ajustar cualquier referencia a DB_FILENAME por self.db_path o por el path que se pasa al constructor.
# =========================
# DB
# =========================
class DB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()
        self._seed_operators_if_empty()

    def _connect(self):
        return sqlite3.connect(self.db_path)
    

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

            # Migración simple: agregar columna atraso_motivo si no existe
            try:
                cur.execute("PRAGMA table_info(salmuera_registros);")
                cols = [row[1] for row in cur.fetchall()]
                if "atraso_motivo" not in cols:
                    cur.execute("ALTER TABLE salmuera_registros ADD COLUMN atraso_motivo TEXT;")
            except Exception:
                pass

            con.commit()
    
    def fetch_salmuera_range(self, desde_iso: str, hasta_iso: str):
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
                    operador, COALESCE(observaciones,''), COALESCE(atraso_motivo,''),
                    created_at_iso
                FROM salmuera_registros
                WHERE fecha_iso BETWEEN ? AND ?
                ORDER BY fecha_iso ASC, hora_hm ASC, id ASC;
            """, (desde_iso, hasta_iso))
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
                "voltajes_celdas": json.loads(r[6]) if r[6] else [],
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
            })
        return out

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

        import json
        return {
            "id": r[0],
            "fecha_iso": r[1],
            "hora_hm": r[2],
            "electrolizador": r[3],
            "cantidad_celdas": r[4],
            "turno": r[5],
            "voltajes_celdas": json.loads(r[6]) if r[6] else [],
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
                    operador, observaciones, atraso_motivo,
                    created_at_iso
                ) VALUES (
                    ?,?,?,?,?,   ?,?,
                    ?,?,?,      ?,?,
                    ?,?,?,      ?,?,
                    ?,?,?,      ?
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
                    operador, observaciones, atraso_motivo,
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
            "voltajes_celdas": json.loads(r[6]) if r[6] else [],
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
            "observaciones": r[19] or "",
            "atraso_motivo": r[20] or "",
            "created_at_iso": r[21],
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
                    operador, observaciones,
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
                "voltajes_celdas": json.loads(r[6]),
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
                "observaciones": r[19] or "",
                "created_at_iso": r[20]
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
                    operador, observaciones,
                    created_at_iso
                FROM salmuera_registros
                WHERE fecha_iso BETWEEN ? AND ?
                ORDER BY fecha_iso ASC, id ASC;
            """, (fecha_desde_iso, fecha_hasta_iso))
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
                "voltajes_celdas": json.loads(r[6]),
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
                "observaciones": r[19] or "",
                "created_at_iso": r[20]
            })
        return out