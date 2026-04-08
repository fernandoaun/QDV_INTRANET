from __future__ import annotations

from typing import Any


def build_openapi_document() -> dict[str, Any]:
    """OpenAPI 3.0 — rutas bajo /api/v1 (mantener alineado al registrar endpoints nuevos)."""
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "QDV Planta API",
            "version": "1.0.0",
            "description": (
                "API REST v1. Autenticación: sesión web (cookie) y/o "
                "`Authorization: Bearer <token>` si el servidor define `API_BEARER_TOKEN` "
                "y `API_BEARER_USER_ID`. Los permisos siguen al usuario resuelto.\n\n"
                "Documentación interactiva: `GET /api/v1/docs` (en producción suele exigir sesión o Bearer; "
                "ver `API_DOCS_REQUIRE_AUTH`). "
                "CORS: variable `CORS_ORIGINS` (lista separada por comas) habilita cabeceras solo bajo `/api/v1/*`. "
                "Rate limit: límite global (`RATELIMIT_DEFAULT`) y límites adicionales por ruta "
                "en `app/api/v1/limits.py` (se aplica el conjunto; un 429 si se viola cualquiera). "
                "Respuesta 429 y cabeceras "
                "`X-RateLimit-*` si están habilitadas. `/openapi.json` y `/docs` sin límite."
            ),
        },
        "tags": [
            {"name": "meta", "description": "Estado y contrato de sync"},
            {"name": "turno", "description": "Turno operativo"},
            {"name": "entregas", "description": "Entregas PT"},
            {"name": "stock", "description": "Stock y consumos"},
            {"name": "panel", "description": "Resumen tipo dashboard"},
        ],
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Token de servicio (env `API_BEARER_TOKEN`).",
                }
            },
            "schemas": {
                "Error": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                        "message": {"type": "string"},
                    },
                },
                "HealthOk": {
                    "type": "object",
                    "properties": {
                        "ok": {"type": "boolean"},
                        "service": {"type": "string"},
                    },
                },
                "SyncMeta": {
                    "type": "object",
                    "properties": {
                        "api_version": {"type": "integer"},
                        "server_time_utc": {"type": "string", "format": "date-time"},
                    },
                },
            },
        },
        "paths": {
            "/api/v1/health": {
                "get": {
                    "tags": ["meta"],
                    "summary": "Estado del servicio",
                    "security": [],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/HealthOk"}
                                }
                            },
                        }
                    },
                }
            },
            "/api/v1/sync/meta": {
                "get": {
                    "tags": ["meta"],
                    "summary": "Metadatos para clientes offline / sync",
                    "security": [],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/SyncMeta"}
                                }
                            },
                        }
                    },
                }
            },
            "/api/v1/shift/status": {
                "get": {
                    "tags": ["turno"],
                    "summary": "Estado de turno para el usuario actual",
                    "security": [{"BearerAuth": []}],
                    "responses": {
                        "200": {"description": "OK"},
                        "401": {
                            "description": "Sin sesión / sin usuario",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/v1/entregas": {
                "get": {
                    "tags": ["entregas"],
                    "summary": "Listado de entregas",
                    "security": [{"BearerAuth": []}],
                    "responses": {
                        "200": {"description": "OK — { items: [...] }"},
                        "401": {
                            "description": "No autorizado",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            },
                        },
                        "403": {
                            "description": "Sin acceso al hub de entregas",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/v1/stock/existencias": {
                "get": {
                    "tags": ["stock"],
                    "summary": "Existencias consolidadas",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {
                            "name": "categoria",
                            "in": "query",
                            "schema": {
                                "type": "string",
                                "enum": [
                                    "todas",
                                    "materia_prima",
                                    "laboratorio",
                                    "producto_terminado",
                                ],
                            },
                            "description": "Por defecto: todas",
                        }
                    ],
                    "responses": {
                        "200": {"description": "OK — { categoria, items }"},
                        "401": {
                            "description": "No autorizado",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            },
                        },
                        "403": {
                            "description": "Sin permiso stock_existencias",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/v1/stock/consumos/producto": {
                "get": {
                    "tags": ["stock"],
                    "summary": "Consumos recientes por producto",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {
                            "name": "categoria",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "producto",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer", "default": 50},
                        },
                    ],
                    "responses": {
                        "200": {"description": "OK"},
                        "400": {"description": "Parámetros inválidos"},
                        "401": {"description": "No autorizado"},
                        "403": {"description": "Sin permiso stock_consumos"},
                    },
                }
            },
            "/api/v1/stock/consumos/ultimos-dias": {
                "get": {
                    "tags": ["stock"],
                    "summary": "Consumos en ventana de fechas",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {
                            "name": "dias",
                            "in": "query",
                            "schema": {"type": "integer", "default": 30},
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer", "default": 300},
                        },
                    ],
                    "responses": {
                        "200": {"description": "OK"},
                        "401": {"description": "No autorizado"},
                        "403": {"description": "Sin permiso stock_historial"},
                    },
                }
            },
            "/api/v1/stock/alertas": {
                "get": {
                    "tags": ["stock"],
                    "summary": "Productos en o bajo umbral de alerta",
                    "security": [{"BearerAuth": []}],
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer", "default": 100},
                        }
                    ],
                    "responses": {
                        "200": {"description": "OK"},
                        "401": {"description": "No autorizado"},
                        "403": {"description": "Sin acceso al hub de stock"},
                    },
                }
            },
            "/api/v1/dashboard/snapshot": {
                "get": {
                    "tags": ["panel"],
                    "summary": "Resumen tipo dashboard (claves según permisos)",
                    "security": [{"BearerAuth": []}],
                    "responses": {
                        "200": {"description": "OK — objeto parcial"},
                        "401": {"description": "No autorizado"},
                    },
                }
            },
        },
    }
