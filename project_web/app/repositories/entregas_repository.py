from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Entrega
from app.repositories.base import BaseRepository


class EntregasRepository(BaseRepository):
    def list_with_catalogos(self) -> list[Entrega]:
        return list(
            self.session.scalars(
                select(Entrega)
                .options(
                    selectinload(Entrega.producto_terminado),
                    selectinload(Entrega.cliente_row),
                    selectinload(Entrega.lugar_row),
                    selectinload(Entrega.chofer_row),
                )
                .order_by(Entrega.fecha_prevista.asc(), Entrega.id.asc())
            ).all()
        )


entregas_repo = EntregasRepository()
