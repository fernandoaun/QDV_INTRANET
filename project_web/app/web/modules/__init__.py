"""Blueprints HTML por dominio industrial.

Prioridad de producto (implementar y endurecer primero):
1. auth — login, sesión, base de permisos en planta
2. panel — dashboard operativo (`main`)
3. produccion — hub de circuitos (salmuera, agua, reactor, bolsones, lab, gráficos)
4. entregas — programación, carga y entrega PT; trazabilidad asociada
5. stock — pantallas bajo ``/produccion/stock/*`` (blueprint ``produccion``); lógica en services/repos
6. admin — usuarios, roles, equipos, permisos granulares

Además (acoplado al turno operativo):
- shift — entrega/recepción de turno, bloqueo de escritura sin turno

Carpetas temáticas sin URL prefix propio (documentación / extracción futura):
- hipoclorito, documentos, trazabilidad — ver ``app.domain`` y docstrings en cada paquete
- bolson, lab, reactor, agua, salmuera — rutas registradas desde ``produccion.routes``
"""
