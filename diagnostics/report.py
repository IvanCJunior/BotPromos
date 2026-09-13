from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

PASTA_PROJETO = Path(__file__).resolve().parents[1]
PASTA_LOGS = PASTA_PROJETO / "logs" / "diagnostico"


def _ler_jsonl(caminho: Path) -> list[dict[str, Any]]:
    eventos: list[dict[str, Any]] = []
    if not caminho.exists():
        return eventos
    with caminho.open("r", encoding="utf-8") as fp:
        for numero, linha in enumerate(fp, start=1):
            linha = linha.strip()
            if not linha:
                continue
            try:
                eventos.append(json.loads(linha))
            except json.JSONDecodeError:
                eventos.append(
                    {
                        "tipo_evento": "LINHA_INVALIDA",
                        "codigo": "JSON_INVALIDO",
                        "motivo": f"Linha {numero} inválida",
                    }
                )
    return eventos


def _formatar_duracao(segundos: float) -> str:
    segundos = max(0, int(segundos))
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{horas:02d}h {minutos:02d}min {segundos:02d}s"


def _valor(dados: dict[str, Any], chave: str, padrao: Any = None) -> Any:
    valor = dados.get("dados") or {}
    return valor.get(chave, padrao)


def gerar_relatorio_execucao(caminho_eventos: Optional[Path | str] = None) -> Path:
    PASTA_LOGS.mkdir(parents=True, exist_ok=True)

    if caminho_eventos is None:
        meta = PASTA_LOGS / "ultima_execucao.json"
        if not meta.exists():
            raise FileNotFoundError("Nenhuma execução registrada.")
        caminho_eventos = json.loads(meta.read_text(encoding="utf-8"))["arquivo_eventos"]

    caminho = Path(caminho_eventos)
    eventos = _ler_jsonl(caminho)
    session_id = next((e.get("session_id") for e in eventos if e.get("session_id")), caminho.stem)

    recebidas: dict[str, dict[str, Any]] = {}
    finais: dict[str, dict[str, Any]] = {}
    etapas_por_promo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    contagem_etapas_erro: Counter[str] = Counter()
    contagem_codigos: Counter[str] = Counter()
    contagem_alertas: Counter[str] = Counter()
    lojas: Counter[str] = Counter()
    canais: Counter[str] = Counter()
    tempos: list[float] = []

    inicio = None
    fim = None

    for evento in eventos:
        ts = evento.get("timestamp")
        if ts:
            try:
                data = datetime.fromisoformat(ts)
                inicio = data if inicio is None or data < inicio else inicio
                fim = data if fim is None or data > fim else fim
            except ValueError:
                pass

        audit_id = evento.get("audit_id")
        tipo = evento.get("tipo_evento")

        if tipo == "PROMOCAO_RECEBIDA" and audit_id:
            recebidas[audit_id] = evento
            canal = _valor(evento, "canal", "Desconhecido")
            canais[str(canal)] += 1

        if audit_id and tipo == "ETAPA":
            etapas_por_promo[audit_id].append(evento)
            status = evento.get("status_etapa")
            codigo = evento.get("codigo") or "SEM_CODIGO"
            etapa = evento.get("etapa") or "SEM_ETAPA"
            if status == "ERRO":
                contagem_etapas_erro[etapa] += 1
                contagem_codigos[codigo] += 1
            elif status == "ALERTA":
                contagem_alertas[codigo] += 1
            if evento.get("duracao_ms") is not None:
                tempos.append(float(evento["duracao_ms"]))
            loja = _valor(evento, "loja")
            if loja:
                lojas[str(loja)] += 1

        if tipo == "PROMOCAO_FINALIZADA" and audit_id:
            finais[audit_id] = evento
            codigo = evento.get("codigo")
            if codigo and evento.get("status_final") in {"ERRO", "CANCELADA"}:
                contagem_codigos[codigo] += 1

    status_counter = Counter(
        (finais.get(aid) or {}).get("status_final", "SEM_FINALIZACAO")
        for aid in recebidas
    )
    total = len(recebidas)
    enviadas = status_counter.get("ENVIADA", 0)
    taxa = (enviadas / total * 100) if total else 0.0
    duracao_s = (fim - inicio).total_seconds() if inicio and fim else 0.0

    pendentes = []
    for aid, recebido in recebidas.items():
        if aid not in finais:
            pendentes.append(
                {
                    "audit_id": aid,
                    "canal": _valor(recebido, "canal", ""),
                    "telegram_id": _valor(recebido, "telegram_id"),
                    "ultima_etapa": (etapas_por_promo.get(aid) or [{}])[-1].get("etapa", "RECEBIDA"),
                }
            )

    resumo = {
        "session_id": session_id,
        "arquivo_eventos": str(caminho),
        "iniciada_em": inicio.isoformat(timespec="seconds") if inicio else None,
        "encerrada_em": fim.isoformat(timespec="seconds") if fim else None,
        "duracao_segundos": round(duracao_s, 2),
        "total_recebidas": total,
        "status": dict(status_counter),
        "taxa_sucesso_percentual": round(taxa, 2),
        "erros_por_etapa": dict(contagem_etapas_erro.most_common()),
        "principais_codigos": dict(contagem_codigos.most_common()),
        "alertas": dict(contagem_alertas.most_common()),
        "lojas": dict(lojas.most_common()),
        "canais": dict(canais.most_common()),
        "promocoes_sem_finalizacao": pendentes,
        "tempo_medio_etapa_ms": round(sum(tempos) / len(tempos), 2) if tempos else 0,
    }

    arquivo_resumo = PASTA_LOGS / f"resumo_{session_id}.json"
    arquivo_resumo.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")

    linhas = [
        "RELATÓRIO DO BOT — EXECUÇÃO",
        "=" * 78,
        f"Sessão................ {session_id}",
        f"Início................ {resumo['iniciada_em'] or 'Não identificado'}",
        f"Fim................... {resumo['encerrada_em'] or 'Não identificado'}",
        f"Tempo em execução..... {_formatar_duracao(duracao_s)}",
        f"Arquivo técnico....... {caminho}",
        "",
        "RESULTADOS",
        "-" * 78,
        f"Promoções recebidas... {total}",
        f"Promoções enviadas.... {enviadas}",
        f"Taxa de sucesso....... {taxa:.2f}%".replace(f"{taxa:.2f}", f"{taxa:.2f}".replace(".", ",")),
    ]

    ordem = ["ENVIADA", "CANCELADA", "IGNORADA", "DUPLICADA", "ERRO", "SEM_FINALIZACAO"]
    for status in ordem:
        linhas.append(f"{status.title():<22} {status_counter.get(status, 0)}")

    linhas += ["", "ERROS POR ETAPA", "-" * 78]
    if contagem_etapas_erro:
        for nome, qtd in contagem_etapas_erro.most_common():
            linhas.append(f"{nome:<50} {qtd}")
    else:
        linhas.append("Nenhum erro de etapa registrado.")

    linhas += ["", "PRINCIPAIS MOTIVOS/CÓDIGOS", "-" * 78]
    if contagem_codigos:
        for nome, qtd in contagem_codigos.most_common(30):
            linhas.append(f"{nome:<58} {qtd}")
    else:
        linhas.append("Nenhum código de erro registrado.")

    linhas += ["", "ALERTAS DE QUALIDADE", "-" * 78]
    if contagem_alertas:
        for nome, qtd in contagem_alertas.most_common(30):
            linhas.append(f"{nome:<58} {qtd}")
    else:
        linhas.append("Nenhum alerta de qualidade registrado.")

    linhas += ["", "PROMOÇÕES SEM FINALIZAÇÃO", "-" * 78]
    if pendentes:
        for item in pendentes[:50]:
            linhas.append(
                f"{item['audit_id']} | {item['canal']} | Telegram {item['telegram_id']} | {item['ultima_etapa']}"
            )
    else:
        linhas.append("Nenhuma promoção ficou sem finalização.")

    linhas += [
        "",
        "ARQUIVOS PARA INSPEÇÃO",
        "-" * 78,
        f"Relatório............. {PASTA_LOGS / f'relatorio_{session_id}.txt'}",
        f"Resumo JSON........... {arquivo_resumo}",
        f"Eventos completos..... {caminho}",
        "=" * 78,
    ]

    arquivo_relatorio = PASTA_LOGS / f"relatorio_{session_id}.txt"
    arquivo_relatorio.write_text("\n".join(linhas) + "\n", encoding="utf-8")

    (PASTA_LOGS / "relatorio_ultima_execucao.txt").write_text(
        arquivo_relatorio.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (PASTA_LOGS / "resumo_ultima_execucao.json").write_text(
        arquivo_resumo.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return arquivo_relatorio


if __name__ == "__main__":
    caminho = gerar_relatorio_execucao()
    print(f"Relatório criado em: {caminho}")
