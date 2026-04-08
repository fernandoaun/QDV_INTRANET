from __future__ import annotations

from sqlalchemy import func, select

from app.models import ConsumoStock, Equipo, IngresoStock, ProductoCatalogo
from app.repositories.base import BaseRepository


class StockRepository(BaseRepository):
    def sum_ingresos_by_producto(self, categoria: str) -> dict[str, float]:
        rows = self.session.execute(
            select(IngresoStock.producto, func.sum(IngresoStock.cantidad))
            .where(IngresoStock.categoria == categoria)
            .group_by(IngresoStock.producto)
        ).all()
        return {str(r[0]): float(r[1] or 0) for r in rows}

    def sum_consumos_by_producto(self, categoria: str) -> dict[str, float]:
        rows = self.session.execute(
            select(ConsumoStock.producto, func.sum(ConsumoStock.cantidad))
            .where(ConsumoStock.categoria == categoria)
            .group_by(ConsumoStock.producto)
        ).all()
        return {str(r[0]): float(r[1] or 0) for r in rows}

    def catalog_is_stockable_map(self, categoria: str) -> dict[str, bool]:
        rows = self.session.scalars(
            select(ProductoCatalogo)
            .where(ProductoCatalogo.categoria == categoria, ProductoCatalogo.activo.is_(True))
            .order_by(ProductoCatalogo.nombre_producto.asc())
        ).all()
        return {str(r.nombre_producto): bool(getattr(r, "is_stockable", True)) for r in rows}

    def list_catalog_con_umbral_alerta(self) -> list[ProductoCatalogo]:
        """Productos activos, stockeables, con mínimo de alerta definido."""
        return list(
            self.session.scalars(
                select(ProductoCatalogo)
                .where(
                    ProductoCatalogo.activo.is_(True),
                    ProductoCatalogo.stock_minimo_alerta.is_not(None),
                    ProductoCatalogo.is_stockable.is_(True),
                )
                .order_by(ProductoCatalogo.categoria, ProductoCatalogo.nombre_producto)
            ).all()
        )

    def list_consumos_stock_in_interval(self, started_at_iso: str, ended_at_iso: str) -> list[ConsumoStock]:
        return list(
            self.session.scalars(
                select(ConsumoStock)
                .where(
                    ConsumoStock.created_at_iso >= started_at_iso,
                    ConsumoStock.created_at_iso <= ended_at_iso,
                )
                .order_by(ConsumoStock.created_at_iso.asc(), ConsumoStock.id.asc())
            ).all()
        )

    def equipo_nombres_by_ids(self, equipo_ids: set[int]) -> dict[int, str]:
        if not equipo_ids:
            return {}
        rows = self.session.scalars(select(Equipo).where(Equipo.id.in_(equipo_ids))).all()
        return {int(e.id): (e.nombre_equipo or "").strip() for e in rows}

    def list_consumos_for_product(self, categoria: str, producto: str, limit: int) -> list[ConsumoStock]:
        return list(
            self.session.scalars(
                select(ConsumoStock)
                .where(ConsumoStock.categoria == categoria, ConsumoStock.producto == producto)
                .order_by(ConsumoStock.created_at_iso.desc(), ConsumoStock.id.desc())
                .limit(limit)
            ).all()
        )

    def list_consumos_since_fecha(self, fecha_min_inclusive: str, limit: int) -> list[ConsumoStock]:
        return list(
            self.session.scalars(
                select(ConsumoStock)
                .where(ConsumoStock.fecha >= fecha_min_inclusive)
                .order_by(ConsumoStock.fecha.desc(), ConsumoStock.hora.desc(), ConsumoStock.id.desc())
                .limit(limit)
            ).all()
        )


stock_repo = StockRepository()
