from __future__ import annotations

from app.extensions import db


class Operador(db.Model):
    __tablename__ = "operadores"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(256), nullable=False, unique=True, index=True)
    created_at_iso = db.Column(db.String(32), nullable=False)


class SalmueraRegistro(db.Model):
    __tablename__ = "salmuera_registros"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fecha_iso = db.Column(db.String(16), nullable=False, index=True)
    hora_hm = db.Column(db.String(8), nullable=False)
    electrolizador = db.Column(db.Integer, nullable=False)
    cantidad_celdas = db.Column(db.Integer, nullable=False)
    turno = db.Column(db.String(64), nullable=False)
    voltajes_json = db.Column(db.Text, nullable=False)
    voltaje_total = db.Column(db.Float, nullable=False)
    amperaje = db.Column(db.Float, nullable=False)
    caudal_agua_l_h = db.Column(db.Float, nullable=False)
    caudal_salmuera_l_h = db.Column(db.Float, nullable=False)
    hipo_conc = db.Column(db.Float, nullable=False)
    hipo_exceso_soda = db.Column(db.Float, nullable=False)
    sal_temp = db.Column(db.Float, nullable=False)
    sal_conc = db.Column(db.Float, nullable=False)
    sal_ph = db.Column(db.Float, nullable=False)
    soda_conc = db.Column(db.Float, nullable=False)
    declor_ph = db.Column(db.Float, nullable=False)
    operador = db.Column(db.String(256), nullable=False)
    lote = db.Column(db.String(128))
    observaciones = db.Column(db.Text)
    atraso_motivo = db.Column(db.Text)
    created_at_iso = db.Column(db.String(32), nullable=False)


class SalmueraAnalisis8hs(db.Model):
    __tablename__ = "salmuera_analisis_8hs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fecha = db.Column(db.String(16), nullable=False, index=True)
    hora = db.Column(db.String(8), nullable=False)
    fecha_hora_iso = db.Column(db.String(32), nullable=False, index=True)
    turno = db.Column(db.String(64), nullable=False)
    operador = db.Column(db.String(256), nullable=False)
    dureza_salmuera = db.Column(db.Float, nullable=False)
    cloro_libre_salmuera = db.Column(db.Float, nullable=False)
    observaciones = db.Column(db.Text)
    file_dureza_path = db.Column(db.Text)
    file_cloro_libre_path = db.Column(db.Text)
    created_at_iso = db.Column(db.String(32), nullable=False)


class BolsonRegistro(db.Model):
    __tablename__ = "bolson_registros"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fecha_iso = db.Column(db.String(16), nullable=False, index=True)
    hora_hm = db.Column(db.String(8), nullable=False)
    created_at_iso = db.Column(db.String(32), nullable=False)


class ReactorRegistro(db.Model):
    __tablename__ = "reactor_registros"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fecha_iso = db.Column(db.String(16), nullable=False, index=True)
    hora_hm = db.Column(db.String(8), nullable=False)
    operador = db.Column(db.String(256), nullable=False)
    lote = db.Column(db.String(128), nullable=False)
    ph = db.Column(db.Float, nullable=False)
    temperatura = db.Column(db.Float, nullable=False)
    densidad = db.Column(db.Float, nullable=False)
    concentracion_tabla = db.Column(db.Float, nullable=False)
    exceso_naoh = db.Column(db.Float, nullable=False)
    exceso_na2co3 = db.Column(db.Float, nullable=False)
    observaciones = db.Column(db.Text)
    created_at_iso = db.Column(db.String(32), nullable=False)


class AguaRegistro(db.Model):
    __tablename__ = "agua_registros"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fecha_iso = db.Column(db.String(16), nullable=False, index=True)
    hora_hm = db.Column(db.String(8), nullable=False)
    turno = db.Column(db.String(64), nullable=False)
    operador = db.Column(db.String(256), nullable=False)
    lote = db.Column(db.String(128), nullable=False)
    numero_columna = db.Column(db.Integer, nullable=False)
    temperatura = db.Column(db.Float, nullable=False)
    dureza = db.Column(db.Float, nullable=False)
    observaciones = db.Column(db.Text)
    created_at_iso = db.Column(db.String(32), nullable=False)


class ColumnaIntercambio(db.Model):
    __tablename__ = "columnas_intercambio_ionico"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    columna_numero = db.Column(db.Integer, nullable=False)
    estado = db.Column(db.String(64), nullable=False)
    fecha_regeneracion = db.Column(db.String(32))
    hora_regeneracion = db.Column(db.String(16))
    dureza_salida_ppm = db.Column(db.Float)
    dureza_post_regeneracion_ppm = db.Column(db.Float)
    observaciones = db.Column(db.Text)
    created_at_iso = db.Column(db.String(32), nullable=False)
    updated_at_iso = db.Column(db.String(32), nullable=False)


class ProductoCatalogo(db.Model):
    __tablename__ = "productos_catalogo"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    categoria = db.Column(db.String(32), nullable=False)
    nombre_producto = db.Column(db.String(256), nullable=False)
    tipo_producto = db.Column(db.String(32), nullable=False, default="Normal")
    requiere_equipo = db.Column(db.Boolean, nullable=False, default=False)
    is_stockable = db.Column(db.Boolean, nullable=False, default=True)
    stock_minimo_alerta = db.Column(db.Float)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at_iso = db.Column(db.String(32), nullable=False)

    __table_args__ = (db.UniqueConstraint("categoria", "nombre_producto", name="uq_catalogo_cat_nombre"),)


class IngresoStock(db.Model):
    __tablename__ = "ingresos_stock"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    categoria = db.Column(db.String(32), nullable=False)
    producto = db.Column(db.String(256), nullable=False)
    marca = db.Column(db.String(256), nullable=False)
    vencimiento = db.Column(db.String(64), nullable=False)
    lote = db.Column(db.String(128), nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    unidad = db.Column(db.String(64), nullable=False, default="")
    fecha = db.Column(db.String(16), nullable=False)
    hora = db.Column(db.String(8), nullable=False)
    operador = db.Column(db.String(256), nullable=False)
    observaciones = db.Column(db.Text)
    proveedor = db.Column(db.String(256))
    cargado_por_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    created_at_iso = db.Column(db.String(32), nullable=False)


class ConsumoStock(db.Model):
    __tablename__ = "consumos_stock"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    categoria = db.Column(db.String(32), nullable=False)
    producto = db.Column(db.String(256), nullable=False)
    marca = db.Column(db.String(256), nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    fecha = db.Column(db.String(16), nullable=False)
    hora = db.Column(db.String(8), nullable=False)
    operador = db.Column(db.String(256), nullable=False)
    observaciones = db.Column(db.Text)
    equipo_id = db.Column(db.Integer, db.ForeignKey("equipos.id"))
    ingreso_stock_id = db.Column(db.Integer, db.ForeignKey("ingresos_stock.id"), nullable=True, index=True)
    created_at_iso = db.Column(db.String(32), nullable=False)


class Equipo(db.Model):
    __tablename__ = "equipos"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_equipo = db.Column(db.String(256), nullable=False)
    descripcion = db.Column(db.String(512), nullable=False, default="")
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at_iso = db.Column(db.String(32), nullable=False)


class ProductoColor(db.Model):
    __tablename__ = "producto_colores"

    nombre_clave = db.Column(db.String(256), primary_key=True)
    nombre_display = db.Column(db.String(256), nullable=False)
    color_hex = db.Column(db.String(16), nullable=False)
    created_at_iso = db.Column(db.String(32), nullable=False)


class Entrega(db.Model):
    __tablename__ = "entregas"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cliente = db.Column(db.String(256), nullable=False)
    lugar_entrega = db.Column(db.String(512), nullable=False)
    producto = db.Column(db.String(256), nullable=False)

    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes_entrega.id"), nullable=True, index=True)
    lugar_entrega_id = db.Column(db.Integer, db.ForeignKey("lugares_entrega.id"), nullable=True, index=True)
    producto_terminado_id = db.Column(db.Integer, db.ForeignKey("productos_terminados_entrega.id"), nullable=True, index=True)
    chofer_entrega_id = db.Column(db.Integer, db.ForeignKey("choferes_entrega.id"), nullable=True, index=True)
    cantidad = db.Column(db.Float, nullable=False)
    unidad = db.Column(db.String(64), nullable=True)
    fecha_prevista = db.Column(db.String(16), nullable=False, index=True)
    observaciones = db.Column(db.Text)
    chofer_previsto = db.Column(db.String(256), nullable=True)

    estado = db.Column(db.String(32), nullable=False, default="programada", index=True)

    created_at_iso = db.Column(db.String(32), nullable=False)
    updated_at_iso = db.Column(db.String(32), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)

    cargada_at_iso = db.Column(db.String(32), nullable=True)
    cargada_by_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    consumo_stock_id = db.Column(db.Integer, db.ForeignKey("consumos_stock.id"), nullable=True, unique=True)

    stock_categoria = db.Column(db.String(32), nullable=True)
    stock_marca = db.Column(db.String(256), nullable=True)
    stock_equipo_id = db.Column(db.Integer, db.ForeignKey("equipos.id"), nullable=True)

    entregada_at_iso = db.Column(db.String(32), nullable=True)
    entregada_by_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    entregada_chofer_nombre = db.Column(db.String(256), nullable=True)
    entregada_lugar = db.Column(db.String(512), nullable=True)
    entregada_dia_semana = db.Column(db.String(32), nullable=True)

    producto_terminado = db.relationship("ProductoTerminado", foreign_keys=[producto_terminado_id])
    cliente_row = db.relationship("ClienteEntrega", foreign_keys=[cliente_id])
    lugar_row = db.relationship("LugarEntrega", foreign_keys=[lugar_entrega_id])
    chofer_row = db.relationship("ChoferEntrega", foreign_keys=[chofer_entrega_id])


class EntregaEvento(db.Model):
    __tablename__ = "entrega_eventos"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    entrega_id = db.Column(db.Integer, db.ForeignKey("entregas.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo = db.Column(db.String(32), nullable=False, index=True)
    at_iso = db.Column(db.String(32), nullable=False)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    actor_display = db.Column(db.String(256), nullable=False, default="")
    detalle = db.Column(db.Text)
