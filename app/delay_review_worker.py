"""Compatibilidad: el antiguo worker ya no genera avisos desde Demoras.

La revisión vencida se consulta en delay_zones, /api/delays y el mapa.
Se conserva este módulo para que invocaciones antiguas terminen sin escrituras.
"""

from __future__ import annotations

from datetime import datetime


def run_once(database, as_of: datetime | None = None, batch_size: int = 100) -> int:
    if not 1 <= batch_size <= 1000:
        raise ValueError("batch_size debe estar entre 1 y 1000")
    return 0


def main() -> None:
    print("El worker de avisos por demora fue retirado; las revisiones se consultan en Demoras.")


if __name__ == "__main__":
    main()
