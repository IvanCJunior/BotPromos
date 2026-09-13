# whatsapp/queue.py

from __future__ import annotations

import asyncio
import json
import socket
import time
import uuid
from urllib.error import URLError
from urllib.request import urlopen
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Optional

from diagnostics.audit import finalizar_promocao, registrar_erro, registrar_etapa
from whatsapp.config import GRUPOS_WHATSAPP
from whatsapp.service import WhatsAppService
from utils.file_cleanup import apagar_imagem_temporaria


@dataclass
class ItemFilaWhatsApp:
    mensagem: str
    imagem: Optional[str] = None
    origem: str = ""
    telegram_id: Optional[int] = None
    audit_id: str = ""
    enfileirado_em: float = 0.0
    item_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "PENDENTE"
    grupos_enviados: list[str] = field(default_factory=list)

    def para_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> "ItemFilaWhatsApp":
        return cls(
            mensagem=str(dados.get("mensagem") or ""),
            imagem=dados.get("imagem"),
            origem=str(dados.get("origem") or ""),
            telegram_id=dados.get("telegram_id"),
            audit_id=str(dados.get("audit_id") or ""),
            enfileirado_em=float(dados.get("enfileirado_em") or time.time()),
            item_id=str(dados.get("item_id") or uuid.uuid4().hex),
            status="PENDENTE",
            grupos_enviados=list(dados.get("grupos_enviados") or []),
        )


fila_whatsapp: asyncio.Queue[ItemFilaWhatsApp] = asyncio.Queue()
_service = WhatsAppService()
_worker_task: Optional[asyncio.Task] = None
_watchdog_task: Optional[asyncio.Task] = None
_healthcheck_task: Optional[asyncio.Task] = None

INTERVALO_WATCHDOG_WHATSAPP = 60
INTERVALO_HEALTH_CHECK = 300
ATRASO_INICIAL_HEALTH_CHECK = 15

# A fila é salva fora da pasta whatsapp para sobreviver a atualizações de código.
ARQUIVO_FILA_WHATSAPP = (
    Path(__file__).resolve().parents[1] / "database" / "fila_whatsapp.json"
)
VERSAO_ARQUIVO_FILA = 1
_itens_persistidos: dict[str, ItemFilaWhatsApp] = {}
_lock_persistencia = asyncio.Lock()
_persistencia_carregada = False


def _gravar_fila_em_disco() -> None:
    """Grava a fila de forma atômica para evitar arquivo incompleto."""
    ARQUIVO_FILA_WHATSAPP.parent.mkdir(parents=True, exist_ok=True)
    temporario = ARQUIVO_FILA_WHATSAPP.with_suffix(".tmp")
    conteudo = {
        "versao": VERSAO_ARQUIVO_FILA,
        "atualizado_em": time.time(),
        "itens": [item.para_dict() for item in _itens_persistidos.values()],
    }
    temporario.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporario.replace(ARQUIVO_FILA_WHATSAPP)


def _ler_fila_do_disco() -> list[ItemFilaWhatsApp]:
    if not ARQUIVO_FILA_WHATSAPP.exists():
        return []

    try:
        dados = json.loads(ARQUIVO_FILA_WHATSAPP.read_text(encoding="utf-8"))
        itens_brutos = dados.get("itens", []) if isinstance(dados, dict) else []
        itens: list[ItemFilaWhatsApp] = []
        for item_bruto in itens_brutos:
            if not isinstance(item_bruto, dict):
                continue
            item = ItemFilaWhatsApp.de_dict(item_bruto)
            if item.mensagem.strip():
                itens.append(item)
        return itens
    except Exception as erro:
        corrompido = ARQUIVO_FILA_WHATSAPP.with_name(
            f"fila_whatsapp_corrompida_{int(time.time())}.json"
        )
        try:
            ARQUIVO_FILA_WHATSAPP.replace(corrompido)
        except OSError:
            pass
        print(
            "⚠ Não foi possível carregar a fila persistida do WhatsApp: "
            f"{type(erro).__name__}: {erro}"
        )
        print(f"   O arquivo problemático foi preservado em: {corrompido}")
        return []


async def _salvar_item(item: ItemFilaWhatsApp) -> None:
    async with _lock_persistencia:
        _itens_persistidos[item.item_id] = item
        await asyncio.to_thread(_gravar_fila_em_disco)


async def _remover_item(item: ItemFilaWhatsApp) -> None:
    async with _lock_persistencia:
        _itens_persistidos.pop(item.item_id, None)
        await asyncio.to_thread(_gravar_fila_em_disco)


async def _carregar_fila_persistida() -> int:
    global _persistencia_carregada

    async with _lock_persistencia:
        if _persistencia_carregada:
            return 0

        itens = await asyncio.to_thread(_ler_fila_do_disco)
        recuperados = 0
        for item in itens:
            if item.item_id in _itens_persistidos:
                continue
            item.status = "PENDENTE"
            _itens_persistidos[item.item_id] = item
            await fila_whatsapp.put(item)
            recuperados += 1

        _persistencia_carregada = True
        if itens:
            await asyncio.to_thread(_gravar_fila_em_disco)
        return recuperados


# Primeira tentativa imediata + três novas tentativas.
# Os valores representam a espera antes de cada tentativa.
ATRASOS_TENTATIVAS_WHATSAPP = (0, 5, 15, 30)


def _erro_permanente_whatsapp(erro: Exception) -> bool:
    """Erros de entrada não melhoram com uma nova tentativa."""
    return isinstance(erro, (FileNotFoundError, ValueError))


async def _enviar_grupo_com_retry(
    item: ItemFilaWhatsApp,
    grupo: str,
) -> tuple[str, int]:
    """Envia para um grupo com até quatro tentativas e backoff progressivo."""
    ultimo_erro: Optional[Exception] = None
    total_tentativas = len(ATRASOS_TENTATIVAS_WHATSAPP)

    for tentativa, atraso in enumerate(ATRASOS_TENTATIVAS_WHATSAPP, start=1):
        if atraso:
            print(
                f"   Nova tentativa em {atraso}s "
                f"({tentativa}/{total_tentativas})..."
            )
            if item.audit_id:
                registrar_etapa(
                    item.audit_id,
                    "WHATSAPP_RETRY",
                    status="AGUARDANDO",
                    codigo="AGUARDANDO_NOVA_TENTATIVA",
                    grupo=grupo,
                    tentativa=tentativa,
                    total_tentativas=total_tentativas,
                    espera_segundos=atraso,
                )
            await asyncio.sleep(atraso)

        inicio_tentativa = perf_counter()
        try:
            if tentativa > 1:
                await _service.preparar_nova_tentativa(
                    audit_id=item.audit_id,
                    grupo=grupo,
                    tentativa=tentativa,
                )

            if item.audit_id:
                registrar_etapa(
                    item.audit_id,
                    "WHATSAPP_RETRY",
                    codigo="TENTATIVA_INICIADA",
                    grupo=grupo,
                    tentativa=tentativa,
                    total_tentativas=total_tentativas,
                )

            tipo_envio = await _service.enviar_promocao(
                nome_grupo=grupo,
                mensagem=item.mensagem,
                imagem=item.imagem,
                audit_id=item.audit_id,
            )

            if item.audit_id:
                registrar_etapa(
                    item.audit_id,
                    "WHATSAPP_RETRY",
                    codigo=(
                        "ENVIO_NA_PRIMEIRA_TENTATIVA"
                        if tentativa == 1
                        else "ENVIO_RECUPERADO_APOS_RETRY"
                    ),
                    grupo=grupo,
                    tentativa=tentativa,
                    total_tentativas=total_tentativas,
                    duracao_ms=(perf_counter() - inicio_tentativa) * 1000,
                )
            return tipo_envio, tentativa

        except asyncio.CancelledError:
            raise
        except Exception as erro:
            ultimo_erro = erro
            permanente = _erro_permanente_whatsapp(erro)
            print(
                f"   Tentativa {tentativa}/{total_tentativas} falhou: "
                f"{type(erro).__name__}: {erro}"
            )

            if item.audit_id:
                registrar_erro(
                    item.audit_id,
                    "WHATSAPP_RETRY",
                    erro,
                    codigo=(
                        "ERRO_PERMANENTE_SEM_RETRY"
                        if permanente
                        else "TENTATIVA_FALHOU"
                    ),
                    grupo=grupo,
                    tentativa=tentativa,
                    total_tentativas=total_tentativas,
                    duracao_ms=(perf_counter() - inicio_tentativa) * 1000,
                )

            if permanente or tentativa == total_tentativas:
                break

    if ultimo_erro is None:
        raise RuntimeError("O envio ao WhatsApp falhou sem informar o motivo.")
    raise ultimo_erro


async def adicionar_promocao_na_fila(
    mensagem: str,
    imagem: Optional[str] = None,
    origem: str = "",
    telegram_id: Optional[int] = None,
    audit_id: str = "",
) -> None:
    await _carregar_fila_persistida()

    mensagem = (mensagem or "").strip()
    if not mensagem:
        raise ValueError("Não é possível adicionar uma mensagem vazia à fila.")

    item = ItemFilaWhatsApp(
        mensagem=mensagem,
        imagem=imagem,
        origem=origem,
        telegram_id=telegram_id,
        audit_id=audit_id,
        enfileirado_em=time.time(),
    )

    # Primeiro salva no disco; só depois disponibiliza ao worker.
    # Assim, uma queda entre essas etapas não perde a promoção.
    await _salvar_item(item)
    await fila_whatsapp.put(item)

    if audit_id:
        registrar_etapa(
            audit_id,
            "FILA_WHATSAPP",
            codigo="ITEM_ENFILEIRADO",
            tamanho_fila=fila_whatsapp.qsize(),
            grupos=list(GRUPOS_WHATSAPP),
        )

    print()
    print("-" * 70)
    print("FILA DO WHATSAPP")
    print("-" * 70)
    print("Status.............. ✅ PROMOÇÃO ADICIONADA")
    print(f"Itens aguardando.... {fila_whatsapp.qsize()}")
    if origem:
        print(f"Origem.............. {origem}")
    if telegram_id is not None:
        print(f"Telegram ID......... {telegram_id}")
    if audit_id:
        print(f"Auditoria ID........ {audit_id}")
    print("-" * 70)
    print()


async def worker_whatsapp() -> None:
    itens_recuperados = await _carregar_fila_persistida()

    print()
    print("=" * 70)
    print("WORKER DO WHATSAPP")
    print("=" * 70)
    print("Status.............. ✅ ONLINE")
    print(f"Grupos configurados. {len(GRUPOS_WHATSAPP)}")
    print(f"Fila recuperada..... {itens_recuperados}")
    print(f"Arquivo persistente. {ARQUIVO_FILA_WHATSAPP}")
    print("=" * 70)
    print()

    while True:
        item = await fila_whatsapp.get()
        inicio_total = perf_counter()
        tempo_espera_ms = (time.time() - item.enfileirado_em) * 1000 if item.enfileirado_em else 0.0
        grupos_ja_enviados = [
            grupo for grupo in GRUPOS_WHATSAPP if grupo in item.grupos_enviados
        ]
        sucessos = len(grupos_ja_enviados)
        falhas = 0
        resultados: list[dict[str, str]] = [
            {
                "grupo": grupo,
                "status": "ENVIADO_ANTES_DA_RECUPERACAO",
                "tipo": "RECUPERADO_DO_DISCO",
                "tentativas": "0",
            }
            for grupo in grupos_ja_enviados
        ]
        processamento_concluido = False

        item.status = "PROCESSANDO"
        await _salvar_item(item)

        try:
            print()
            print("=" * 70)
            print("ENVIO PELO WHATSAPP")
            print("=" * 70)
            if item.origem:
                print(f"Origem.............. {item.origem}")
            if item.telegram_id is not None:
                print(f"Telegram ID......... {item.telegram_id}")
            if item.audit_id:
                print(f"Auditoria ID........ {item.audit_id}")
            print(f"Grupos.............. {len(GRUPOS_WHATSAPP)}")
            print(f"Fila restante....... {fila_whatsapp.qsize()}")
            print("-" * 70)

            if item.audit_id:
                registrar_etapa(
                    item.audit_id,
                    "ENVIO_WHATSAPP",
                    codigo="ENVIO_INICIADO",
                    grupos=list(GRUPOS_WHATSAPP),
                    fila_restante=fila_whatsapp.qsize(),
                    tempo_espera_fila_ms=tempo_espera_ms,
                )

            for indice, grupo in enumerate(GRUPOS_WHATSAPP, start=1):
                if grupo in item.grupos_enviados:
                    print(
                        f"{indice}. {grupo} — ✅ JÁ ENVIADO "
                        "(recuperado da fila persistente)"
                    )
                    continue

                inicio_grupo = perf_counter()
                try:
                    tipo_envio, tentativas_usadas = await _enviar_grupo_com_retry(
                        item=item,
                        grupo=grupo,
                    )
                    descricao = "IMAGEM + LEGENDA" if tipo_envio == "imagem_com_legenda" else "TEXTO"
                    sucessos += 1
                    if grupo not in item.grupos_enviados:
                        item.grupos_enviados.append(grupo)
                    await _salvar_item(item)
                    resultados.append(
                        {
                            "grupo": grupo,
                            "status": "ENVIADO",
                            "tipo": descricao,
                            "tentativas": str(tentativas_usadas),
                        }
                    )
                    print(
                        f"{indice}. {grupo} — ✅ ENVIADO ({descricao}) "
                        f"— tentativa {tentativas_usadas}"
                    )

                    if item.audit_id:
                        registrar_etapa(
                            item.audit_id,
                            "ENVIO_WHATSAPP_GRUPO",
                            codigo="GRUPO_ENVIADO",
                            duracao_ms=(perf_counter() - inicio_grupo) * 1000,
                            grupo=grupo,
                            tipo_envio=descricao,
                            tentativas_usadas=tentativas_usadas,
                        )

                except Exception as erro:
                    falhas += 1
                    resultados.append(
                        {
                            "grupo": grupo,
                            "status": "ERRO",
                            "tipo_erro": type(erro).__name__,
                            "motivo": str(erro),
                        }
                    )
                    print(f"{indice}. {grupo} — ❌ ERRO: {erro}")
                    if item.audit_id:
                        registrar_erro(
                            item.audit_id,
                            "ENVIO_WHATSAPP_GRUPO",
                            erro,
                            codigo="FALHA_ENVIO_GRUPO",
                            grupo=grupo,
                            duracao_ms=(perf_counter() - inicio_grupo) * 1000,
                        )

            duracao_ms = (perf_counter() - inicio_total) * 1000
            if item.audit_id:
                if sucessos == len(GRUPOS_WHATSAPP) and falhas == 0:
                    finalizar_promocao(
                        item.audit_id,
                        "ENVIADA",
                        etapa="FINALIZADA",
                        codigo="WHATSAPP_TODOS_GRUPOS_ENVIADOS",
                        motivo="A promoção foi enviada para todos os grupos configurados.",
                        sucessos=sucessos,
                        falhas=falhas,
                        resultados=resultados,
                        duracao_envio_ms=round(duracao_ms, 2),
                        tempo_espera_fila_ms=round(tempo_espera_ms, 2),
                    )
                elif sucessos > 0:
                    finalizar_promocao(
                        item.audit_id,
                        "ERRO",
                        etapa="ENVIO_WHATSAPP",
                        codigo="WHATSAPP_ENVIO_PARCIAL",
                        motivo="A promoção foi enviada para alguns grupos, mas falhou em outros.",
                        sucessos=sucessos,
                        falhas=falhas,
                        resultados=resultados,
                        duracao_envio_ms=round(duracao_ms, 2),
                        tempo_espera_fila_ms=round(tempo_espera_ms, 2),
                    )
                else:
                    finalizar_promocao(
                        item.audit_id,
                        "ERRO",
                        etapa="ENVIO_WHATSAPP",
                        codigo="WHATSAPP_NENHUM_GRUPO_ENVIADO",
                        motivo="A promoção não foi enviada para nenhum grupo.",
                        sucessos=sucessos,
                        falhas=falhas,
                        resultados=resultados,
                        duracao_envio_ms=round(duracao_ms, 2),
                        tempo_espera_fila_ms=round(tempo_espera_ms, 2),
                    )

            processamento_concluido = True
            await _remover_item(item)

            imagem_apagada, motivo_limpeza = await asyncio.to_thread(
                apagar_imagem_temporaria,
                item.imagem,
            )
            if item.audit_id:
                registrar_etapa(
                    item.audit_id,
                    "LIMPEZA_IMAGEM",
                    status="OK" if imagem_apagada or motivo_limpeza in {"SEM_IMAGEM", "ARQUIVO_JA_INEXISTENTE"} else "ALERTA",
                    codigo="IMAGEM_TEMPORARIA_APAGADA" if imagem_apagada else "IMAGEM_TEMPORARIA_NAO_APAGADA",
                    motivo=motivo_limpeza,
                    caminho_imagem=item.imagem or "",
                )
            if imagem_apagada:
                print("Imagem temporária... ✅ APAGADA")
            elif motivo_limpeza not in {"SEM_IMAGEM", "ARQUIVO_JA_INEXISTENTE"}:
                print(f"Imagem temporária... ⚠ NÃO APAGADA ({motivo_limpeza})")

            print("=" * 70)
            print()

        except asyncio.CancelledError:
            item.status = "PENDENTE"
            await _salvar_item(item)
            if item.audit_id:
                finalizar_promocao(
                    item.audit_id,
                    "ERRO",
                    etapa="ENVIO_WHATSAPP",
                    codigo="WORKER_CANCELADO_DURANTE_ENVIO",
                    motivo="O worker foi encerrado enquanto processava a promoção.",
                )
            raise

        except Exception as erro:
            if item.audit_id:
                registrar_erro(
                    item.audit_id,
                    "ENVIO_WHATSAPP",
                    erro,
                    codigo="ERRO_WORKER_WHATSAPP",
                )
                finalizar_promocao(
                    item.audit_id,
                    "ERRO",
                    etapa="ENVIO_WHATSAPP",
                    codigo="ERRO_WORKER_WHATSAPP",
                    motivo=str(erro),
                )
            print()
            print("=" * 70)
            print("ERRO NO WORKER DO WHATSAPP")
            print("=" * 70)
            print(f"Tipo................ {type(erro).__name__}")
            print(f"Detalhes............ {erro}")
            print("=" * 70)
            print()
            processamento_concluido = True
            await _remover_item(item)
            imagem_apagada, motivo_limpeza = await asyncio.to_thread(
                apagar_imagem_temporaria,
                item.imagem,
            )
            if item.audit_id:
                registrar_etapa(
                    item.audit_id,
                    "LIMPEZA_IMAGEM",
                    status="OK" if imagem_apagada or motivo_limpeza in {"SEM_IMAGEM", "ARQUIVO_JA_INEXISTENTE"} else "ALERTA",
                    codigo="IMAGEM_TEMPORARIA_APAGADA" if imagem_apagada else "IMAGEM_TEMPORARIA_NAO_APAGADA",
                    motivo=motivo_limpeza,
                    caminho_imagem=item.imagem or "",
                )

        finally:
            # Em encerramento/cancelamento o item permanece no disco.
            # Em processamento normal ou erro tratado ele já foi removido.
            fila_whatsapp.task_done()



def _porta_local_aberta(porta: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=timeout):
            return True
    except OSError:
        return False


def _ollama_respondendo() -> tuple[bool, str]:
    try:
        with urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as resposta:
            if 200 <= getattr(resposta, "status", 0) < 300:
                return True, "API local respondendo."
            return False, f"Resposta HTTP inesperada: {getattr(resposta, 'status', '?')}"
    except (OSError, URLError, TimeoutError) as erro:
        return False, f"{type(erro).__name__}: {erro}"


async def _verificar_telegram() -> tuple[bool, str]:
    try:
        from telegram_bot.client import client
        conectado = bool(client.is_connected())
        return conectado, "Cliente conectado." if conectado else "Cliente desconectado."
    except Exception as erro:
        return False, f"{type(erro).__name__}: {erro}"


async def _verificar_whatsapp() -> tuple[bool, str]:
    try:
        return await _service.verificar_saude()
    except Exception as erro:
        return False, f"{type(erro).__name__}: {erro}"


async def _verificar_ollama() -> tuple[bool, str]:
    return await asyncio.to_thread(_ollama_respondendo)


async def _verificar_mercado_livre() -> tuple[bool, str]:
    # O Chrome de afiliados usa a porta 9222. Este health check não altera
    # a página nem tenta gerar links; apenas confirma que o navegador está vivo.
    aberta = await asyncio.to_thread(_porta_local_aberta, 9222)
    if aberta:
        return True, "Chrome de afiliados respondendo na porta 9222."
    return False, "Chrome de afiliados não respondeu na porta 9222."


def _icone_status(ok: bool) -> str:
    return "✅ ONLINE" if ok else "❌ OFFLINE"


async def health_check_servicos() -> None:
    """Monitora os serviços principais sem interferir no processamento."""
    await asyncio.sleep(ATRASO_INICIAL_HEALTH_CHECK)
    ultimo_estado: dict[str, bool] = {}

    while True:
        try:
            resultados = {
                "Telegram": await _verificar_telegram(),
                "WhatsApp": await _verificar_whatsapp(),
                "Ollama": await _verificar_ollama(),
                "Mercado Livre": await _verificar_mercado_livre(),
            }

            mudou = not ultimo_estado or any(
                ultimo_estado.get(nome) != ok
                for nome, (ok, _detalhe) in resultados.items()
            )

            if mudou:
                print()
                print("=" * 70)
                print("HEALTH CHECK DOS SERVIÇOS")
                print("=" * 70)
                for nome, (ok, detalhe) in resultados.items():
                    print(f"{nome + '':<21} {_icone_status(ok)}")
                    if not ok:
                        print(f"  Detalhes........... {detalhe}")
                print(f"Fila WhatsApp....... {fila_whatsapp.qsize()} item(ns)")
                print(f"Intervalo........... {INTERVALO_HEALTH_CHECK} segundos")
                print("=" * 70)
                print()

            ultimo_estado = {nome: ok for nome, (ok, _detalhe) in resultados.items()}
            await asyncio.sleep(INTERVALO_HEALTH_CHECK)

        except asyncio.CancelledError:
            raise
        except Exception as erro:
            print(
                "⚠ Health check encontrou um erro inesperado: "
                f"{type(erro).__name__}: {erro}"
            )
            await asyncio.sleep(30)


async def watchdog_whatsapp() -> None:
    """Verifica e recupera o serviço do WhatsApp continuamente."""
    print()
    print("=" * 70)
    print("WATCHDOG DO WHATSAPP")
    print("=" * 70)
    print("Status.............. ✅ ONLINE")
    print(f"Intervalo........... {INTERVALO_WATCHDOG_WHATSAPP} segundos")
    print("=" * 70)
    print()

    ultimo_status = ""

    while True:
        try:
            await asyncio.sleep(INTERVALO_WATCHDOG_WHATSAPP)
            status, detalhe = await _service.watchdog_verificar_e_recuperar()

            # Evita poluir o terminal a cada minuto quando tudo está normal.
            if status == "RECUPERADO":
                print("✅ Watchdog: conexão do WhatsApp recuperada automaticamente.")
                print(f"   Detalhes: {detalhe}")
            elif status == "OFFLINE":
                print("⚠ Watchdog: WhatsApp indisponível; nova verificação será feita.")
                print(f"   Detalhes: {detalhe}")
            elif status == "ONLINE" and ultimo_status in {"OFFLINE", "RECUPERADO"}:
                print("✅ Watchdog: WhatsApp voltou ao estado normal.")

            ultimo_status = status

        except asyncio.CancelledError:
            raise
        except Exception as erro:
            print(
                "⚠ Watchdog do WhatsApp encontrou um erro inesperado: "
                f"{type(erro).__name__}: {erro}"
            )
            await asyncio.sleep(5)

def iniciar_worker_whatsapp() -> asyncio.Task:
    global _worker_task, _watchdog_task, _healthcheck_task

    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(worker_whatsapp(), name="worker_whatsapp")

    if _watchdog_task is None or _watchdog_task.done():
        _watchdog_task = asyncio.create_task(
            watchdog_whatsapp(),
            name="watchdog_whatsapp",
        )

    if _healthcheck_task is None or _healthcheck_task.done():
        _healthcheck_task = asyncio.create_task(
            health_check_servicos(),
            name="health_check_servicos",
        )

    return _worker_task


async def encerrar_worker_whatsapp() -> None:
    global _worker_task, _watchdog_task, _healthcheck_task

    if _healthcheck_task is not None:
        _healthcheck_task.cancel()
        try:
            await _healthcheck_task
        except asyncio.CancelledError:
            pass
        _healthcheck_task = None

    if _watchdog_task is not None:
        _watchdog_task.cancel()
        try:
            await _watchdog_task
        except asyncio.CancelledError:
            pass
        _watchdog_task = None

    if _worker_task is not None:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None

    await _service.fechar()
