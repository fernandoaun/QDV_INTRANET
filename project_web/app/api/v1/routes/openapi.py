from __future__ import annotations

from flask import Response, jsonify, url_for

from app.api.openapi_spec import build_openapi_document
from app.api.v1.blueprint import bp
from app.api.v1.docs_access import require_api_docs_auth


@bp.get("/openapi.json")
@require_api_docs_auth
def openapi_json():
    return jsonify(build_openapi_document())


@bp.get("/docs")
@require_api_docs_auth
def api_docs():
    spec_url = url_for("api_v1.openapi_json")
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>QDV API v1</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.min.css" crossorigin="anonymous"/>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.min.js" crossorigin="anonymous"></script>
  <script>
    window.ui = SwaggerUIBundle({{
      url: {spec_url!r},
      dom_id: "#swagger-ui",
      presets: [SwaggerUIBundle.presets.apis],
      layout: "BaseLayout"
    }});
  </script>
</body>
</html>"""
    return Response(html, mimetype="text/html; charset=utf-8")
