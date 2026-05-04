"""
Límites por ruta (Flask-Limiter), además del global `RATELIMIT_DEFAULT`.
Valores conservadores para lecturas costosas; ajustá si un cliente legítimo los pisa.
"""

# Consultas agregadas / muchas filas
LIMIT_HEAVY_READ = "45 per minute"

# Varios bloques de dashboard (salmuera, agua, stock, etc.)
LIMIT_DASHBOARD = "30 per minute"

# Lecturas de stock típicas
LIMIT_STOCK_READ = "60 per minute"

# Turno: consultas frecuentes pero baratas
LIMIT_SHIFT_STATUS = "90 per minute"

# Lecturas públicas mínimas (health, meta sync)
LIMIT_PUBLIC_LIGHT = "240 per minute"
