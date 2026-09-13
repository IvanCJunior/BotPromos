from __future__ import annotations

from time import perf_counter


class Cronometro:
    def __init__(self) -> None:
        self._inicio = perf_counter()
        self._marcas: dict[str, float] = {}

    def marcar(self, etapa: str) -> float:
        decorrido = perf_counter() - self._inicio
        self._marcas[etapa] = decorrido
        return round(decorrido, 3)

    def total(self) -> float:
        return round(perf_counter() - self._inicio, 3)

    def para_dict(self) -> dict[str, float]:
        return dict(self._marcas)
