"""
Contextos industriales QDV (mapa mental → código).

No es una capa DDD obligatoria: centraliza nombres de negocio y dónde vive cada pieza
para que nuevas features no mezclen reglas en vistas.

+---------------------------+------------------------------------------+
| Contexto                  | Modelos / servicios / rutas              |
+---------------------------+------------------------------------------+
| Cambio de turno           | models.shift; shift_handover_service     |
|                           | (persistencia parte/recepción);          |
|                           | web.modules.shift                        |
| Stock operativo           | IngresoStock, ConsumoStock, Equipo;      |
|                           | services.stock_service;                  |
|                           | repositories.stock_repository;           |
|                           | web stock bajo blueprint produccion      |
| Entregas y trazabilidad   | Entrega, EntregaEvento, catálogos PT;    |
|                           | services.entregas_*; entregas_web_service|
|                           | web.modules.entregas                     |
| Hipoclorito               | indicadores en turno;                    |
|                           | services.shift_hypochlorite_indicators;  |
|                           | utils.hipoclorito_producto               |
| Circuito salmuera         | SalmueraRegistro; web.modules.salmuera   |
| Circuito agua             | AguaRegistro; web.modules.agua           |
| Reactor / bolsones / lab  | ReactorRegistro, BolsonRegistro,         |
|                           | LaboratoryReagent*; módulos reactor,     |
|                           | bolson, lab → registrados en produccion  |
| Usuarios y permisos       | User, PermisoUsuario; auth_utils;        |
|                           | web.modules.admin, auth                  |
| PDFs y referencias        | AppUploadedDocument;                       |
|                           | services.analysis_ref_pdf                |
| Gráficos producción       | services.produccion_graficos_service     |
| Panel / dashboard         | services.dashboard_service               |
| Hub producción (operadores)| services.produccion_hub_service        |
+---------------------------+------------------------------------------+
"""
