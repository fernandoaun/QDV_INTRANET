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
    orp = db.Column(db.Float)
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
    orp = db.Column(db.Float)
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
    codigo_interno = db.Column(db.String(64), nullable=True, index=True)
    nombre_equipo = db.Column(db.String(256), nullable=False)
    descripcion = db.Column(db.String(512), nullable=False, default="")
    tipo_equipo = db.Column(db.String(128), nullable=True, index=True)
    area_sector = db.Column(db.String(128), nullable=True, index=True)
    equipo_principal_id = db.Column(db.Integer, db.ForeignKey("equipos.id"), nullable=True, index=True)
    marca = db.Column(db.String(128), nullable=True)
    modelo = db.Column(db.String(128), nullable=True)
    numero_serie = db.Column(db.String(128), nullable=True)
    fecha_alta = db.Column(db.String(16), nullable=True)
    estado = db.Column(db.String(32), nullable=False, default="operativo", index=True)
    observaciones = db.Column(db.Text, nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at_iso = db.Column(db.String(32), nullable=False)

    equipo_principal = db.relationship("Equipo", remote_side=[id], backref="equipos_asociados")


class MaintenanceComponent(db.Model):
    __tablename__ = "maintenance_components"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    equipo_principal_id = db.Column(db.Integer, db.ForeignKey("equipos.id"), nullable=False, index=True)
    codigo_interno = db.Column(db.String(64), nullable=True, index=True)
    nombre = db.Column(db.String(256), nullable=False)
    tipo_componente = db.Column(db.String(128), nullable=True, index=True)
    marca = db.Column(db.String(128), nullable=True)
    modelo = db.Column(db.String(128), nullable=True)
    numero_serie = db.Column(db.String(128), nullable=True)
    estado = db.Column(db.String(32), nullable=False, default="operativo", index=True)
    observaciones = db.Column(db.Text, nullable=True)
    created_at_iso = db.Column(db.String(32), nullable=False)
    updated_at_iso = db.Column(db.String(32), nullable=False)

    equipo_principal = db.relationship("Equipo", backref="maintenance_components")


class MaintenanceFailure(db.Model):
    __tablename__ = "maintenance_failures"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    detected_at_iso = db.Column(db.String(32), nullable=False, index=True)
    equipo_id = db.Column(db.Integer, db.ForeignKey("equipos.id"), nullable=False, index=True)
    component_id = db.Column(db.Integer, db.ForeignKey("maintenance_components.id"), nullable=True, index=True)
    reported_by_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True, index=True)
    reported_by_display = db.Column(db.String(256), nullable=False, default="")
    descripcion_falla = db.Column(db.Text, nullable=False)
    sintoma_observado = db.Column(db.Text, nullable=True)
    causa_probable = db.Column(db.Text, nullable=True)
    causa_real = db.Column(db.Text, nullable=True)
    criticidad = db.Column(db.String(16), nullable=False, default="media", index=True)
    estado = db.Column(db.String(32), nullable=False, default="reportado", index=True)
    tiempo_fuera_servicio_horas = db.Column(db.Float, nullable=True)
    accion_realizada = db.Column(db.Text, nullable=True)
    repuestos_utilizados = db.Column(db.Text, nullable=True)
    recursos_utilizados = db.Column(db.Text, nullable=True)
    responsable_trabajo = db.Column(db.String(256), nullable=True, index=True)
    closed_at_iso = db.Column(db.String(32), nullable=True, index=True)
    observaciones = db.Column(db.Text, nullable=True)
    created_at_iso = db.Column(db.String(32), nullable=False)
    updated_at_iso = db.Column(db.String(32), nullable=False)

    equipo = db.relationship("Equipo", backref="maintenance_failures")
    component = db.relationship("MaintenanceComponent", backref="failures")
    reported_by = db.relationship("User", foreign_keys=[reported_by_user_id])


class MaintenanceAttachment(db.Model):
    __tablename__ = "maintenance_attachments"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    failure_id = db.Column(db.Integer, db.ForeignKey("maintenance_failures.id", ondelete="CASCADE"), nullable=True, index=True)
    equipo_id = db.Column(db.Integer, db.ForeignKey("equipos.id"), nullable=True, index=True)
    component_id = db.Column(db.Integer, db.ForeignKey("maintenance_components.id"), nullable=True, index=True)
    original_filename = db.Column(db.String(256), nullable=False)
    stored_path = db.Column(db.Text, nullable=False)
    content_type = db.Column(db.String(128), nullable=True)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    created_at_iso = db.Column(db.String(32), nullable=False)

    failure = db.relationship("MaintenanceFailure", backref="attachments")
    equipo = db.relationship("Equipo", backref="maintenance_attachments")
    component = db.relationship("MaintenanceComponent", backref="attachments")
    uploaded_by = db.relationship("User", foreign_keys=[uploaded_by_user_id])


class MaintenancePlan(db.Model):
    __tablename__ = "maintenance_plans"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    equipo_id = db.Column(db.Integer, db.ForeignKey("equipos.id"), nullable=False, index=True)
    component_id = db.Column(db.Integer, db.ForeignKey("maintenance_components.id"), nullable=True, index=True)
    tipo_mantenimiento = db.Column(db.String(32), nullable=False, default="preventivo", index=True)
    nombre = db.Column(db.String(256), nullable=False)
    frecuencia_dias = db.Column(db.Integer, nullable=True)
    frecuencia_horas_uso = db.Column(db.Float, nullable=True)
    frecuencia_periodo = db.Column(db.String(32), nullable=True)
    proxima_fecha = db.Column(db.String(16), nullable=True, index=True)
    responsable = db.Column(db.String(256), nullable=True, index=True)
    duracion_estimada_horas = db.Column(db.Float, nullable=True)
    tareas = db.Column(db.Text, nullable=True)
    recursos_necesarios = db.Column(db.Text, nullable=True)
    repuestos_necesarios = db.Column(db.Text, nullable=True)
    herramientas_necesarias = db.Column(db.Text, nullable=True)
    epp_necesarios = db.Column(db.Text, nullable=True)
    observaciones = db.Column(db.Text, nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at_iso = db.Column(db.String(32), nullable=False)
    updated_at_iso = db.Column(db.String(32), nullable=False)

    equipo = db.relationship("Equipo", backref="maintenance_plans")
    component = db.relationship("MaintenanceComponent", backref="maintenance_plans")


class MaintenanceOrder(db.Model):
    __tablename__ = "maintenance_orders"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("maintenance_plans.id"), nullable=True, index=True)
    failure_id = db.Column(db.Integer, db.ForeignKey("maintenance_failures.id"), nullable=True, index=True)
    prediction_id = db.Column(db.Integer, db.ForeignKey("maintenance_predictions.id"), nullable=True, index=True)
    equipo_id = db.Column(db.Integer, db.ForeignKey("equipos.id"), nullable=False, index=True)
    component_id = db.Column(db.Integer, db.ForeignKey("maintenance_components.id"), nullable=True, index=True)
    tipo_mantenimiento = db.Column(db.String(32), nullable=False, default="preventivo", index=True)
    fecha_programada = db.Column(db.String(16), nullable=False, index=True)
    prioridad = db.Column(db.String(16), nullable=False, default="media", index=True)
    criticidad = db.Column(db.String(16), nullable=False, default="media", index=True)
    responsable = db.Column(db.String(256), nullable=True, index=True)
    estado = db.Column(db.String(32), nullable=False, default="programado", index=True)
    tareas = db.Column(db.Text, nullable=True)
    recursos_necesarios = db.Column(db.Text, nullable=True)
    repuestos_necesarios = db.Column(db.Text, nullable=True)
    herramientas_necesarias = db.Column(db.Text, nullable=True)
    epp_necesarios = db.Column(db.Text, nullable=True)
    tiempo_estimado_horas = db.Column(db.Float, nullable=True)
    observaciones = db.Column(db.Text, nullable=True)
    executed_at_iso = db.Column(db.String(32), nullable=True, index=True)
    closed_at_iso = db.Column(db.String(32), nullable=True, index=True)
    resultado = db.Column(db.Text, nullable=True)
    created_at_iso = db.Column(db.String(32), nullable=False)
    updated_at_iso = db.Column(db.String(32), nullable=False)

    plan = db.relationship("MaintenancePlan", backref="orders")
    failure = db.relationship("MaintenanceFailure", backref="orders")
    prediction = db.relationship("MaintenancePrediction", backref="orders")
    equipo = db.relationship("Equipo", backref="maintenance_orders")
    component = db.relationship("MaintenanceComponent", backref="maintenance_orders")


class MaintenanceResource(db.Model):
    __tablename__ = "maintenance_resources"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    equipo_id = db.Column(db.Integer, db.ForeignKey("equipos.id"), nullable=True, index=True)
    component_id = db.Column(db.Integer, db.ForeignKey("maintenance_components.id"), nullable=True, index=True)
    tipo_mantenimiento = db.Column(db.String(32), nullable=False, default="preventivo", index=True)
    categoria = db.Column(db.String(32), nullable=False, index=True)
    nombre = db.Column(db.String(256), nullable=False)
    cantidad = db.Column(db.Float, nullable=True)
    unidad = db.Column(db.String(64), nullable=True)
    tiempo_estimado_horas = db.Column(db.Float, nullable=True)
    observaciones = db.Column(db.Text, nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at_iso = db.Column(db.String(32), nullable=False)
    updated_at_iso = db.Column(db.String(32), nullable=False)

    equipo = db.relationship("Equipo", backref="maintenance_resources")
    component = db.relationship("MaintenanceComponent", backref="maintenance_resources")


class MaintenanceOrderResource(db.Model):
    __tablename__ = "maintenance_order_resources"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    order_id = db.Column(db.Integer, db.ForeignKey("maintenance_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_id = db.Column(db.Integer, db.ForeignKey("maintenance_resources.id"), nullable=True)
    categoria = db.Column(db.String(32), nullable=False, index=True)
    nombre = db.Column(db.String(256), nullable=False)
    cantidad = db.Column(db.Float, nullable=True)
    unidad = db.Column(db.String(64), nullable=True)
    tiempo_estimado_horas = db.Column(db.Float, nullable=True)
    observaciones = db.Column(db.Text, nullable=True)
    created_at_iso = db.Column(db.String(32), nullable=False)

    order = db.relationship("MaintenanceOrder", backref="order_resources")
    resource = db.relationship("MaintenanceResource")


class MaintenancePrediction(db.Model):
    __tablename__ = "maintenance_predictions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    equipo_id = db.Column(db.Integer, db.ForeignKey("equipos.id"), nullable=False, index=True)
    component_id = db.Column(db.Integer, db.ForeignKey("maintenance_components.id"), nullable=True, index=True)
    tipo_falla = db.Column(db.String(256), nullable=False, index=True)
    cantidad_fallas = db.Column(db.Integer, nullable=False, default=0)
    promedio_dias_entre_fallas = db.Column(db.Float, nullable=True)
    ultima_fecha_falla = db.Column(db.String(16), nullable=True, index=True)
    fecha_estimada_proxima = db.Column(db.String(16), nullable=True, index=True)
    nivel_confianza = db.Column(db.String(16), nullable=False, default="bajo", index=True)
    recomendacion = db.Column(db.Text, nullable=True)
    estado = db.Column(db.String(32), nullable=False, default="sugerida", index=True)
    source_key = db.Column(db.String(512), nullable=False, unique=True, index=True)
    created_at_iso = db.Column(db.String(32), nullable=False)
    updated_at_iso = db.Column(db.String(32), nullable=False)

    equipo = db.relationship("Equipo", backref="maintenance_predictions")
    component = db.relationship("MaintenanceComponent", backref="maintenance_predictions")


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
