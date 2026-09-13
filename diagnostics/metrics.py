from __future__ import annotations

from collections import Counter
from threading import Lock


class MetricasDiagnostico:
    def __init__(self) -> None:
        self._lock = Lock()
        self.resultados: Counter[str] = Counter()
        self.erros: Counter[str] = Counter()
        self.alertas: Counter[str] = Counter()
        self.etapas: Counter[str] = Counter()

    def registrar_etapa(self, etapa: str) -> None:
        with self._lock:
            self.etapas[etapa] += 1

    def registrar_resultado(self, status: str) -> None:
        with self._lock:
            self.resultados[status] += 1

    def registrar_erro(self, codigo: str) -> None:
        with self._lock:
            self.erros[codigo] += 1

    def registrar_alerta(self, codigo: str) -> None:
        with self._lock:
            self.alertas[codigo] += 1

    def para_dict(self) -> dict:
        with self._lock:
            return {
                "resultados": dict(self.resultados),
                "erros": dict(self.erros),
                "alertas": dict(self.alertas),
                "etapas": dict(self.etapas),
            }
