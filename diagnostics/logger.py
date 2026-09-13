from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any


class GravadorJSONL:
    def __init__(self, pasta: Path) -> None:
        self.pasta = pasta
        self.pasta.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def gravar(self, nome_arquivo: str, registro: dict[str, Any]) -> None:
        caminho = self.pasta / nome_arquivo
        linha = json.dumps(
            registro,
            ensure_ascii=False,
            default=str,
        )

        with self._lock:
            with caminho.open("a", encoding="utf-8") as arquivo:
                arquivo.write(linha + "\n")
