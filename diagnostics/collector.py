from __future__ import annotations

import traceback
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from diagnostics.events import NivelEvento, StatusPromocao
from diagnostics.logger import GravadorJSONL
from diagnostics.metrics import MetricasDiagnostico
from diagnostics.models import EventoDiagnostico, PromocaoDiagnostico, agora_iso
from diagnostics.timers import Cronometro


class ColetorDiagnostico:
    def __init__(self, pasta_logs: Path | None = None) -> None:
        raiz = Path(__file__).resolve().parents[1]
        self.pasta_logs = pasta_logs or raiz / "logs" / "diagnostico"
        self.execucao_id = (
            datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_"
            + uuid4().hex[:8]
        )

        self.gravador = GravadorJSONL(self.pasta_logs)
        self.metricas = MetricasDiagnostico()
        self._promocoes: dict[str, PromocaoDiagnostico] = {}
        self._cronometros: dict[str, Cronometro] = {}

    def iniciar_promocao(
        self,
        *,
        canal: str = "",
        telegram_id: int | str | None = None,
        texto: str = "",
        **dados: Any,
    ) -> str:
        promocao = PromocaoDiagnostico(
            execucao_id=self.execucao_id,
            canal=canal,
            telegram_id=telegram_id,
            metadados={
                "texto_original": texto,
                **dados,
            },
        )

        self._promocoes[promocao.promocao_id] = promocao
        self._cronometros[promocao.promocao_id] = Cronometro()

        self.evento(
            promocao.promocao_id,
            nivel=NivelEvento.INFO.value,
            etapa="RECEBIDA",
            codigo="PROMO_RECEBIDA",
            mensagem="Promoção recebida para processamento.",
        )

        return promocao.promocao_id

    def evento(
        self,
        promocao_id: str,
        *,
        nivel: str,
        etapa: str,
        codigo: str,
        mensagem: str,
        **dados: Any,
    ) -> None:
        try:
            cronometro = self._cronometros.get(promocao_id)
            if cronometro is not None:
                dados.setdefault(
                    "tempo_desde_inicio_segundos",
                    cronometro.marcar(etapa),
                )

            registro = EventoDiagnostico(
                execucao_id=self.execucao_id,
                promocao_id=promocao_id,
                data_hora=agora_iso(),
                nivel=nivel,
                etapa=etapa,
                codigo=codigo,
                mensagem=mensagem,
                dados=dados,
            )

            data = datetime.now().strftime("%Y-%m-%d")
            self.gravador.gravar(
                f"eventos_{data}.jsonl",
                registro.para_dict(),
            )
            self.gravador.gravar(
                f"execucao_{self.execucao_id}.jsonl",
                registro.para_dict(),
            )

            self.metricas.registrar_etapa(etapa)

            if nivel == NivelEvento.ALERTA.value:
                self.metricas.registrar_alerta(codigo)

            if nivel == NivelEvento.ERRO.value:
                self.metricas.registrar_erro(codigo)

        except Exception as erro:
            print(
                "⚠ O diagnóstico não conseguiu registrar um evento, "
                f"mas o bot continuará funcionando: {erro}"
            )

    def atualizar(self, promocao_id: str, **campos: Any) -> None:
        try:
            promocao = self._promocoes.get(promocao_id)
            if promocao is None:
                return

            for nome, valor in campos.items():
                if hasattr(promocao, nome):
                    setattr(promocao, nome, valor)
                else:
                    promocao.metadados[nome] = valor

        except Exception as erro:
            print(
                "⚠ O diagnóstico não conseguiu atualizar uma promoção, "
                f"mas o bot continuará funcionando: {erro}"
            )

    def alerta(
        self,
        promocao_id: str,
        *,
        etapa: str,
        codigo: str,
        mensagem: str,
        **dados: Any,
    ) -> None:
        promocao = self._promocoes.get(promocao_id)
        if promocao is not None and codigo not in promocao.alertas:
            promocao.alertas.append(codigo)

        self.evento(
            promocao_id,
            nivel=NivelEvento.ALERTA.value,
            etapa=etapa,
            codigo=codigo,
            mensagem=mensagem,
            **dados,
        )

    def erro(
        self,
        promocao_id: str,
        *,
        etapa: str,
        codigo: str,
        mensagem: str,
        excecao: BaseException | None = None,
        **dados: Any,
    ) -> None:
        if excecao is not None:
            dados.setdefault("tipo_excecao", type(excecao).__name__)
            dados.setdefault("detalhes_excecao", str(excecao))
            dados.setdefault(
                "traceback",
                "".join(
                    traceback.format_exception(
                        type(excecao),
                        excecao,
                        excecao.__traceback__,
                    )
                ),
            )

        self.evento(
            promocao_id,
            nivel=NivelEvento.ERRO.value,
            etapa=etapa,
            codigo=codigo,
            mensagem=mensagem,
            **dados,
        )

    def finalizar(
        self,
        promocao_id: str,
        *,
        status: str,
        codigo: str,
        mensagem: str,
        **dados: Any,
    ) -> None:
        try:
            promocao = self._promocoes.get(promocao_id)
            cronometro = self._cronometros.get(promocao_id)

            if promocao is not None:
                promocao.status = status
                promocao.fim = agora_iso()

                if cronometro is not None:
                    promocao.metadados["tempo_total_segundos"] = (
                        cronometro.total()
                    )
                    promocao.metadados["tempos_etapas"] = (
                        cronometro.para_dict()
                    )

                data = datetime.now().strftime("%Y-%m-%d")
                self.gravador.gravar(
                    f"promocoes_{data}.jsonl",
                    promocao.para_dict(),
                )

            nivel = (
                NivelEvento.SUCESSO.value
                if status == StatusPromocao.ENVIADA.value
                else NivelEvento.INFO.value
            )

            self.evento(
                promocao_id,
                nivel=nivel,
                etapa="FINALIZADA",
                codigo=codigo,
                mensagem=mensagem,
                status=status,
                **dados,
            )

            self.metricas.registrar_resultado(status)

        except Exception as erro:
            print(
                "⚠ O diagnóstico não conseguiu finalizar uma promoção, "
                f"mas o bot continuará funcionando: {erro}"
            )
        finally:
            self._promocoes.pop(promocao_id, None)
            self._cronometros.pop(promocao_id, None)

    def resumo(self) -> dict:
        return {
            "execucao_id": self.execucao_id,
            **self.metricas.para_dict(),
        }
