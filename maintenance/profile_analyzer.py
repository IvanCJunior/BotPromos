from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Iterable

from diagnostics.audit import registrar_sistema

PASTA_PROJETO = Path(__file__).resolve().parents[1]
ARQUIVO_HISTORICO = PASTA_PROJETO / "diagnostics" / "profile_sizes.jsonl"
INTERVALO_PADRAO_SEGUNDOS = 6 * 60 * 60


@dataclass(slots=True)
class PastaMedida:
    caminho: str
    tamanho_bytes: int


@dataclass(slots=True)
class PerfilMedido:
    nome: str
    caminho: str
    tamanho_total_bytes: int
    quantidade_arquivos: int
    quantidade_pastas: int
    erros_leitura: int
    duracao_ms: float
    maiores_pastas: list[PastaMedida]


def _formatar_tamanho(tamanho: int) -> str:
    valor = float(max(0, tamanho))
    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if valor < 1024 or unidade == "TB":
            return f"{valor:.2f} {unidade}"
        valor /= 1024
    return f"{valor:.2f} TB"


def _medir_perfil(nome: str, raiz: Path, limite: int = 15) -> PerfilMedido:
    inicio = perf_counter()
    total = 0
    arquivos = 0
    pastas = 0
    erros = 0
    tamanhos_diretos: dict[Path, int] = {}

    if not raiz.exists():
        return PerfilMedido(nome, str(raiz), 0, 0, 0, 0, 0.0, [])

    for pasta_atual, nomes_pastas, nomes_arquivos in os.walk(raiz, onerror=lambda _: None):
        pasta = Path(pasta_atual)
        pastas += len(nomes_pastas)
        subtotal = 0
        for nome_arquivo in nomes_arquivos:
            caminho = pasta / nome_arquivo
            try:
                tamanho = caminho.stat().st_size
            except OSError:
                erros += 1
                continue
            subtotal += tamanho
            total += tamanho
            arquivos += 1
        tamanhos_diretos[pasta] = subtotal

    tamanhos_acumulados: dict[Path, int] = dict(tamanhos_diretos)
    for pasta in sorted(tamanhos_diretos, key=lambda p: len(p.parts), reverse=True):
        pai = pasta.parent
        if pai == pasta or raiz not in pasta.parents:
            continue
        tamanhos_acumulados[pai] = tamanhos_acumulados.get(pai, 0) + tamanhos_acumulados[pasta]

    maiores: list[PastaMedida] = []
    for pasta, tamanho in sorted(tamanhos_acumulados.items(), key=lambda item: item[1], reverse=True):
        if pasta == raiz or tamanho <= 0:
            continue
        try:
            relativo = pasta.relative_to(raiz)
        except ValueError:
            continue
        maiores.append(PastaMedida(str(relativo), tamanho))
        if len(maiores) >= limite:
            break

    return PerfilMedido(
        nome=nome,
        caminho=str(raiz),
        tamanho_total_bytes=total,
        quantidade_arquivos=arquivos,
        quantidade_pastas=pastas,
        erros_leitura=erros,
        duracao_ms=round((perf_counter() - inicio) * 1000, 2),
        maiores_pastas=maiores,
    )


def analisar_perfis(origem: str = "MANUAL", exibir: bool = True) -> list[PerfilMedido]:
    perfis = [
        ("WhatsApp Profile", PASTA_PROJETO / "whatsapp_profile"),
        ("Chrome Bot Profile", PASTA_PROJETO / "chrome_bot_profile"),
    ]
    resultados = [_medir_perfil(nome, caminho) for nome, caminho in perfis]

    ARQUIVO_HISTORICO.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "origem": origem,
        "perfis": [asdict(item) for item in resultados],
    }
    with ARQUIVO_HISTORICO.open("a", encoding="utf-8", newline="") as arquivo:
        arquivo.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")

    registrar_sistema(
        "PERFIS_MEDIDOS",
        origem=origem,
        perfis=[asdict(item) for item in resultados],
        arquivo_historico=str(ARQUIVO_HISTORICO),
    )

    if exibir:
        print("=" * 70)
        print("ANÁLISE DOS PERFIS DO NAVEGADOR")
        print("=" * 70)
        for resultado in resultados:
            print(f"{resultado.nome + '.........':<28} {_formatar_tamanho(resultado.tamanho_total_bytes)}")
        whatsapp = resultados[0]
        print("-")
        print("Maiores pastas do WhatsApp:")
        for indice, pasta in enumerate(whatsapp.maiores_pastas[:10], start=1):
            print(f"{indice:>2}. {pasta.caminho:<48} {_formatar_tamanho(pasta.tamanho_bytes):>10}")
        print(f"Histórico................. {ARQUIVO_HISTORICO}")
        print("Nenhum arquivo foi apagado ou modificado.")
        print("=" * 70)
        print()

    return resultados


async def monitorar_perfis(
    intervalo_segundos: int = INTERVALO_PADRAO_SEGUNDOS,
) -> None:
    while True:
        await asyncio.sleep(intervalo_segundos)
        try:
            await asyncio.to_thread(analisar_perfis, "PERIODICA", True)
        except asyncio.CancelledError:
            raise
        except Exception as erro:
            registrar_sistema(
                "FALHA_MONITOR_PERFIS",
                status="ERRO",
                motivo=str(erro),
                tipo_erro=type(erro).__name__,
            )
