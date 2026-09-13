from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from diagnostics.events import NivelEvento, StatusPromocao


def agora_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


@dataclass
class EventoDiagnostico:
    execucao_id: str
    promocao_id: str
    data_hora: str
    nivel: str
    etapa: str
    codigo: str
    mensagem: str
    dados: dict[str, Any] = field(default_factory=dict)

    def para_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PromocaoDiagnostico:
    execucao_id: str
    promocao_id: str = field(default_factory=lambda: uuid4().hex)
    status: str = StatusPromocao.EM_PROCESSAMENTO.value
    inicio: str = field(default_factory=agora_iso)
    fim: str = ""
    canal: str = ""
    telegram_id: int | str | None = None
    loja: str = ""
    link_original: str = ""
    link_resolvido: str = ""
    link_afiliado: str = ""
    preco: str = ""
    cupom: str = ""
    imagem: str = ""
    mensagem_final: str = ""
    grupo_whatsapp: str = ""
    alertas: list[str] = field(default_factory=list)
    metadados: dict[str, Any] = field(default_factory=dict)

    def para_dict(self) -> dict[str, Any]:
        return asdict(self)
