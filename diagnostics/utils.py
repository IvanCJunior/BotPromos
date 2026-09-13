from __future__ import annotations

from typing import Any


def limitar_texto(valor: Any, limite: int = 5000) -> str:
    texto = "" if valor is None else str(valor)

    if len(texto) <= limite:
        return texto

    return texto[:limite] + "... [conteúdo reduzido]"
