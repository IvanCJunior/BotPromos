from __future__ import annotations

import json
import os
import platform
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Optional

from config.settings import AUDITORIA_ARQUIVO_DIARIO

PASTA_PROJETO = Path(__file__).resolve().parents[1]
PASTA_LOGS = PASTA_PROJETO / "logs" / "diagnostico"
PASTA_LOGS.mkdir(parents=True, exist_ok=True)

_lock = threading.RLock()
_session_id: Optional[str] = None
_session_started_at: Optional[datetime] = None
_session_started_perf: Optional[float] = None
_session_file: Optional[Path] = None
_daily_file: Optional[Path] = None


def _agora() -> datetime:
    return datetime.now().astimezone()


def _json_safe(valor: Any) -> Any:
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    if isinstance(valor, Path):
        return str(valor)
    if isinstance(valor, (list, tuple, set)):
        return [_json_safe(item) for item in valor]
    if isinstance(valor, dict):
        return {str(k): _json_safe(v) for k, v in valor.items()}
    return str(valor)


def _garantir_sessao() -> str:
    global _session_id
    if not _session_id:
        iniciar_execucao()
    assert _session_id is not None
    return _session_id


def iniciar_execucao() -> str:
    global _session_id, _session_started_at, _session_started_perf
    global _session_file, _daily_file

    with _lock:
        if _session_id:
            return _session_id

        agora = _agora()
        _session_id = agora.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        _session_started_at = agora
        _session_started_perf = perf_counter()
        _daily_file = PASTA_LOGS / f"eventos_{agora:%Y-%m-%d}.jsonl"
        _session_file = PASTA_LOGS / f"execucao_{_session_id}.jsonl"

        _gravar(
            {
                "tipo_evento": "EXECUCAO_INICIADA",
                "codigo": "BOT_START",
                "dados": {
                    "python": platform.python_version(),
                    "sistema": platform.platform(),
                    "pid": os.getpid(),
                    "pasta_projeto": str(PASTA_PROJETO),
                },
            }
        )

        (PASTA_LOGS / "ultima_execucao.json").write_text(
            json.dumps(
                {
                    "session_id": _session_id,
                    "arquivo_eventos": str(_session_file),
                    "iniciada_em": agora.isoformat(timespec="seconds"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return _session_id


def _gravar(evento: dict[str, Any]) -> None:
    session_id = _session_id or "SEM_SESSAO"
    agora = _agora()
    payload = {
        "timestamp": agora.isoformat(timespec="milliseconds"),
        "session_id": session_id,
        **_json_safe(evento),
    }
    linha = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"

    # O arquivo da execução é suficiente para o relatório e para a
    # recuperação dos diagnósticos. O arquivo diário é opcional porque,
    # quando habilitado, duplica todas as escritas em disco.
    arquivos = [_session_file]
    if AUDITORIA_ARQUIVO_DIARIO:
        arquivos.insert(0, _daily_file)

    with _lock:
        for arquivo in arquivos:
            if arquivo is None:
                continue
            with arquivo.open("a", encoding="utf-8", newline="") as fp:
                fp.write(linha)
                fp.flush()


def nova_promocao(
    *,
    canal: str,
    telegram_id: Optional[int],
    texto: str,
    chat_id: Optional[int] = None,
) -> str:
    _garantir_sessao()
    audit_id = uuid.uuid4().hex
    _gravar(
        {
            "tipo_evento": "PROMOCAO_RECEBIDA",
            "audit_id": audit_id,
            "etapa": "RECEBIDA",
            "status_etapa": "OK",
            "dados": {
                "canal": canal,
                "chat_id": chat_id,
                "telegram_id": telegram_id,
                "texto_original": texto,
            },
        }
    )
    return audit_id


def registrar_etapa(
    audit_id: str,
    etapa: str,
    *,
    status: str = "OK",
    codigo: str = "",
    motivo: str = "",
    duracao_ms: Optional[float] = None,
    **dados: Any,
) -> None:
    _garantir_sessao()
    _gravar(
        {
            "tipo_evento": "ETAPA",
            "audit_id": audit_id,
            "etapa": etapa,
            "status_etapa": status,
            "codigo": codigo,
            "motivo": motivo,
            "duracao_ms": round(duracao_ms, 2) if duracao_ms is not None else None,
            "dados": dados,
        }
    )


def registrar_alerta(
    audit_id: str,
    codigo: str,
    motivo: str,
    *,
    etapa: str = "QUALIDADE",
    **dados: Any,
) -> None:
    registrar_etapa(
        audit_id,
        etapa,
        status="ALERTA",
        codigo=codigo,
        motivo=motivo,
        **dados,
    )


def registrar_erro(
    audit_id: str,
    etapa: str,
    erro: BaseException,
    *,
    codigo: str = "ERRO_NAO_CLASSIFICADO",
    duracao_ms: Optional[float] = None,
    **dados: Any,
) -> None:
    registrar_etapa(
        audit_id,
        etapa,
        status="ERRO",
        codigo=codigo,
        motivo=str(erro),
        duracao_ms=duracao_ms,
        tipo_erro=type(erro).__name__,
        traceback="".join(traceback.format_exception(type(erro), erro, erro.__traceback__))[-8000:],
        **dados,
    )


def finalizar_promocao(
    audit_id: str,
    status_final: str,
    *,
    etapa: str = "FINALIZADA",
    codigo: str = "",
    motivo: str = "",
    **dados: Any,
) -> None:
    _garantir_sessao()
    _gravar(
        {
            "tipo_evento": "PROMOCAO_FINALIZADA",
            "audit_id": audit_id,
            "etapa": etapa,
            "status_final": status_final,
            "codigo": codigo,
            "motivo": motivo,
            "dados": dados,
        }
    )


def registrar_sistema(
    codigo: str,
    *,
    status: str = "INFO",
    motivo: str = "",
    **dados: Any,
) -> None:
    _garantir_sessao()
    _gravar(
        {
            "tipo_evento": "SISTEMA",
            "status_etapa": status,
            "codigo": codigo,
            "motivo": motivo,
            "dados": dados,
        }
    )


def encerrar_execucao() -> Optional[Path]:
    global _session_id, _session_started_at, _session_started_perf
    if not _session_id:
        return None

    duracao = None
    if _session_started_perf is not None:
        duracao = perf_counter() - _session_started_perf

    _gravar(
        {
            "tipo_evento": "EXECUCAO_ENCERRADA",
            "codigo": "BOT_STOP",
            "dados": {
                "duracao_segundos": round(duracao or 0, 2),
                "iniciada_em": _session_started_at.isoformat(timespec="seconds")
                if _session_started_at
                else None,
            },
        }
    )

    from diagnostics.report import gerar_relatorio_execucao

    relatorio = gerar_relatorio_execucao(_session_file)
    return relatorio


def arquivo_execucao_atual() -> Optional[Path]:
    return _session_file


# ---------------------------------------------------------------------
# COMPATIBILIDADE COM A ESTRUTURA EM FASES
# ---------------------------------------------------------------------
# Este adaptador mantém as funções antigas usadas pelo bot e também
# disponibiliza o objeto "audit", utilizado pelo teste da Fase 1.
# Assim, não é necessário escolher entre a pasta antiga e a nova.


class _AuditoriaCompatibilidade:
    @property
    def execucao_id(self) -> str:
        return _garantir_sessao()

    def iniciar_promocao(self, **dados: Any) -> str:
        try:
            return nova_promocao(
                canal=str(dados.pop("canal", "") or ""),
                telegram_id=dados.pop("telegram_id", None),
                texto=str(dados.pop("texto", "") or ""),
                chat_id=dados.pop("chat_id", None),
            )
        except Exception as erro:
            print(
                "⚠ O diagnóstico não conseguiu iniciar a promoção, "
                f"mas o bot continuará funcionando: {erro}"
            )
            return ""

    def etapa(
        self,
        promocao_id: str,
        *,
        etapa: str,
        codigo: str = "",
        mensagem: str = "",
        **dados: Any,
    ) -> None:
        if not promocao_id:
            return
        try:
            registrar_etapa(
                promocao_id,
                etapa,
                status="OK",
                codigo=codigo,
                motivo=mensagem,
                **dados,
            )
        except Exception as erro:
            print(
                "⚠ O diagnóstico não conseguiu registrar a etapa, "
                f"mas o bot continuará funcionando: {erro}"
            )

    def atualizar(self, promocao_id: str, **campos: Any) -> None:
        if not promocao_id:
            return
        try:
            registrar_etapa(
                promocao_id,
                "ATUALIZACAO",
                status="OK",
                codigo="DADOS_ATUALIZADOS",
                motivo="Dados complementares da promoção registrados.",
                **campos,
            )
        except Exception as erro:
            print(
                "⚠ O diagnóstico não conseguiu atualizar os dados, "
                f"mas o bot continuará funcionando: {erro}"
            )

    def alerta(
        self,
        promocao_id: str,
        *,
        etapa: str,
        codigo: str,
        mensagem: str = "",
        **dados: Any,
    ) -> None:
        if not promocao_id:
            return
        try:
            registrar_alerta(
                promocao_id,
                codigo,
                mensagem,
                etapa=etapa,
                **dados,
            )
        except Exception as erro:
            print(
                "⚠ O diagnóstico não conseguiu registrar o alerta, "
                f"mas o bot continuará funcionando: {erro}"
            )

    def erro(
        self,
        promocao_id: str,
        *,
        etapa: str,
        codigo: str,
        mensagem: str = "",
        excecao: BaseException | None = None,
        **dados: Any,
    ) -> None:
        if not promocao_id:
            return
        try:
            erro_real = excecao or RuntimeError(mensagem or codigo)
            registrar_erro(
                promocao_id,
                etapa,
                erro_real,
                codigo=codigo,
                **dados,
            )
        except Exception as erro:
            print(
                "⚠ O diagnóstico não conseguiu registrar o erro, "
                f"mas o bot continuará funcionando: {erro}"
            )

    def finalizar(
        self,
        promocao_id: str,
        *,
        status: str,
        codigo: str,
        mensagem: str = "",
        **dados: Any,
    ) -> None:
        if not promocao_id:
            return
        try:
            if dados:
                registrar_etapa(
                    promocao_id,
                    "DADOS_FINAIS",
                    status="OK",
                    codigo="DADOS_FINAIS_REGISTRADOS",
                    motivo="Dados finais registrados antes da conclusão.",
                    **dados,
                )
            finalizar_promocao(
                promocao_id,
                status,
                etapa="FINALIZADA",
                codigo=codigo,
                motivo=mensagem,
            )
        except Exception as erro:
            print(
                "⚠ O diagnóstico não conseguiu finalizar a promoção, "
                f"mas o bot continuará funcionando: {erro}"
            )

    def resumo(self) -> dict[str, Any]:
        try:
            return {
                "execucao_id": _garantir_sessao(),
                "arquivo_execucao": str(arquivo_execucao_atual() or ""),
            }
        except Exception:
            return {}


audit = _AuditoriaCompatibilidade()
