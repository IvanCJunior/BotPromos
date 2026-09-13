# main.py

from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
from pathlib import Path
from typing import Optional


# ============================================================
# DIRETÓRIO DO PROJETO
# ============================================================

PASTA_PROJETO = Path(__file__).resolve().parent


# ============================================================
# IMPORTAÇÕES DO BOT
# ============================================================

from telegram_bot.client import client
from config.settings import (
    BOT_MODE,
    LIMPAR_CACHE_NAVEGADORES,
    MONITORAR_PERFIS,
    PHONE,
)
from diagnostics.audit import encerrar_execucao, iniciar_execucao, registrar_sistema

# Esta importação registra o listener do Telegram.
import telegram_bot.listener  # noqa: F401

from whatsapp.queue import (
    encerrar_worker_whatsapp,
    iniciar_worker_whatsapp,
)


# ============================================================
# CONFIGURAÇÃO DO GOOGLE CHROME
# ============================================================

CAMINHOS_CHROME = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
]

PORTA_AFILIADOS = 9222
PORTA_WHATSAPP = 9223

PERFIL_AFILIADOS = PASTA_PROJETO / "chrome_bot_profile"
PERFIL_WHATSAPP = PASTA_PROJETO / "whatsapp_profile"

URL_MERCADO_LIVRE = (
    "https://www.mercadolivre.com.br/afiliados/linkbuilder#hub"
)

URL_WHATSAPP = "https://web.whatsapp.com/"


# ============================================================
# UTILITÁRIOS
# ============================================================

def encontrar_chrome() -> Path:
    """
    Localiza o executável do Google Chrome.
    """

    for caminho in CAMINHOS_CHROME:
        if caminho.exists():
            return caminho

    raise FileNotFoundError(
        "O Google Chrome não foi encontrado.\n\n"
        "Caminhos verificados:\n"
        + "\n".join(str(caminho) for caminho in CAMINHOS_CHROME)
    )


def porta_esta_aberta(
    porta: int,
    host: str = "127.0.0.1",
    timeout: float = 0.5,
) -> bool:
    """
    Verifica se uma porta local já está em uso.
    """

    try:
        with socket.create_connection(
            (host, porta),
            timeout=timeout,
        ):
            return True

    except OSError:
        return False


async def aguardar_porta(
    porta: int,
    tempo_maximo: int = 30,
) -> bool:
    """
    Aguarda até que uma porta de depuração do Chrome esteja aberta.
    """

    for _ in range(tempo_maximo * 2):
        if porta_esta_aberta(porta):
            return True

        await asyncio.sleep(0.5)

    return False


def abrir_chrome(
    chrome: Path,
    porta: int,
    perfil: Path,
    urls: list[str],
) -> Optional[subprocess.Popen]:
    """
    Abre uma instância independente do Chrome com depuração remota.

    Não abre outra instância caso a porta já esteja em uso.
    """

    if porta_esta_aberta(porta):
        return None

    perfil.mkdir(
        parents=True,
        exist_ok=True,
    )

    argumentos = [
        str(chrome),
        f"--remote-debugging-port={porta}",
        f"--user-data-dir={perfil}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--start-maximized",
        *urls,
    ]

    flags_criacao = 0

    if sys.platform == "win32":
        flags_criacao = subprocess.CREATE_NEW_PROCESS_GROUP

    return subprocess.Popen(
        argumentos,
        cwd=str(PASTA_PROJETO),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags_criacao,
    )


# ============================================================
# MANUTENÇÃO LEVE DOS PERFIS
# ============================================================


def limpar_caches_antes_dos_navegadores() -> None:
    """Limpa caches seguros apenas quando o Chrome do perfil está fechado."""

    if not LIMPAR_CACHE_NAVEGADORES:
        print("Limpeza de caches.... ⏸ DESATIVADA")
        print()
        return

    from maintenance.browser_profile_cleanup import (
        imprimir_resultado_limpeza,
        limpar_perfil_seguro,
    )

    print("=" * 60)
    print("LIMPEZA SEGURA DOS PERFIS")
    print("=" * 60)

    resultado_ml = limpar_perfil_seguro(
        PERFIL_AFILIADOS,
        "Chrome afiliados",
        navegador_aberto=porta_esta_aberta(PORTA_AFILIADOS),
    )
    imprimir_resultado_limpeza(resultado_ml)

    resultado_whatsapp = limpar_perfil_seguro(
        PERFIL_WHATSAPP,
        "Chrome WhatsApp",
        navegador_aberto=porta_esta_aberta(PORTA_WHATSAPP),
    )
    imprimir_resultado_limpeza(resultado_whatsapp)

    print("Dados de sessão....... ✅ PRESERVADOS")
    print("=" * 60)
    print()


# ============================================================
# INICIALIZAÇÃO DOS NAVEGADORES
# ============================================================

async def iniciar_navegadores() -> None:
    """
    Abre automaticamente os Chromes usados pelo robô.
    """

    chrome = encontrar_chrome()

    print("=" * 60)
    print("INICIALIZAÇÃO DOS NAVEGADORES")
    print("=" * 60)

    # --------------------------------------------------------
    # Chrome dos afiliados
    # --------------------------------------------------------

    if porta_esta_aberta(PORTA_AFILIADOS):
        print(
            f"Chrome afiliados..... ✅ JÁ ABERTO "
            f"(porta {PORTA_AFILIADOS})"
        )

    else:
        print(
            f"Chrome afiliados..... ⏳ ABRINDO "
            f"(porta {PORTA_AFILIADOS})"
        )

        abrir_chrome(
            chrome=chrome,
            porta=PORTA_AFILIADOS,
            perfil=PERFIL_AFILIADOS,
            urls=[
                URL_MERCADO_LIVRE,
            ],
        )

        abriu = await aguardar_porta(
            PORTA_AFILIADOS,
            tempo_maximo=30,
        )

        if not abriu:
            raise RuntimeError(
                "O Chrome dos afiliados foi iniciado, mas a porta "
                f"{PORTA_AFILIADOS} não respondeu."
            )

        print(
            f"Chrome afiliados..... ✅ ABERTO "
            f"(porta {PORTA_AFILIADOS})"
        )

    # --------------------------------------------------------
    # Chrome do WhatsApp
    # --------------------------------------------------------

    if porta_esta_aberta(PORTA_WHATSAPP):
        print(
            f"Chrome WhatsApp...... ✅ JÁ ABERTO "
            f"(porta {PORTA_WHATSAPP})"
        )

    else:
        print(
            f"Chrome WhatsApp...... ⏳ ABRINDO "
            f"(porta {PORTA_WHATSAPP})"
        )

        abrir_chrome(
            chrome=chrome,
            porta=PORTA_WHATSAPP,
            perfil=PERFIL_WHATSAPP,
            urls=[
                URL_WHATSAPP,
            ],
        )

        abriu = await aguardar_porta(
            PORTA_WHATSAPP,
            tempo_maximo=30,
        )

        if not abriu:
            raise RuntimeError(
                "O Chrome do WhatsApp foi iniciado, mas a porta "
                f"{PORTA_WHATSAPP} não respondeu."
            )

        print(
            f"Chrome WhatsApp...... ✅ ABERTO "
            f"(porta {PORTA_WHATSAPP})"
        )

    print("=" * 60)
    print()

    # Tempo adicional para as páginas carregarem.
    await asyncio.sleep(3)


# ============================================================
# BOT PRINCIPAL
# ============================================================

async def main() -> None:
    worker_whatsapp = None
    monitor_perfis_task = None

    print()
    print("=" * 60)
    print("BOT DE PROMOÇÕES")
    print("=" * 60)
    print()

    try:
        session_id = iniciar_execucao()
        registrar_sistema("BOT_INICIALIZANDO", session_id=session_id)
        print(f"Auditoria........... ✅ ATIVA ({session_id})")
        print()

        print(f"Modo de execução..... {BOT_MODE.upper()}")
        print()

        # O monitor de perfis é útil em desenvolvimento, mas fica desligado
        # por padrão em produção para evitar varreduras periódicas de disco.
        if MONITORAR_PERFIS:
            # Importação sob demanda: em produção, o módulo de análise de
            # perfis nem sequer é carregado na memória.
            from maintenance.profile_analyzer import (
                analisar_perfis,
                monitorar_perfis,
            )

            await asyncio.to_thread(analisar_perfis, "INICIALIZACAO", True)
            monitor_perfis_task = asyncio.create_task(
                monitorar_perfis(),
                name="monitor_perfis_navegador",
            )
        else:
            print("Monitor de perfis... ⏸ DESATIVADO")
            print()

        # Limpa somente caches descartáveis com os navegadores fechados.
        # A operação é deslocada para uma thread para não bloquear o loop.
        await asyncio.to_thread(limpar_caches_antes_dos_navegadores)

        # Abre os navegadores automaticamente.
        await iniciar_navegadores()

        # Conecta ao Telegram.
        print("=" * 60)
        print("CONEXÃO COM O TELEGRAM")
        print("=" * 60)
        print("Telegram............ ⏳ CONECTANDO")

        await client.start(phone=PHONE)

        print("Telegram............ ✅ CONECTADO")
        registrar_sistema("TELEGRAM_CONECTADO")
        print("=" * 60)
        print()

        # Inicia a fila responsável pelos envios ao WhatsApp.
        worker_whatsapp = iniciar_worker_whatsapp()
        registrar_sistema("WORKER_WHATSAPP_ATIVO")

        print("=" * 60)
        print("BOT ONLINE")
        print("=" * 60)
        print("Telegram............ ✅ MONITORANDO")
        print("WhatsApp............ ✅ WORKER ATIVO")
        print("Amazon.............. ⏸ DESATIVADA")
        print("Mercado Livre....... ✅ PREPARADO")
        print()
        print("Aguardando novas promoções...")
        print()
        print("Para encerrar o robô, pressione CTRL+C.")
        print("=" * 60)
        print()

        await client.run_until_disconnected()

    except KeyboardInterrupt:
        print()
        print("Encerramento solicitado pelo usuário.")

    except Exception as erro:
        registrar_sistema(
            "ERRO_INICIALIZACAO_BOT",
            status="ERRO",
            motivo=str(erro),
            tipo_erro=type(erro).__name__,
        )
        print()
        print("=" * 60)
        print("ERRO NA INICIALIZAÇÃO DO ROBÔ")
        print("=" * 60)
        print(f"Tipo................ {type(erro).__name__}")
        print(f"Detalhes............ {erro}")
        print("=" * 60)
        print()

        raise

    finally:
        print()
        print("=" * 60)
        print("ENCERRANDO O ROBÔ")
        print("=" * 60)

        if monitor_perfis_task is not None:
            monitor_perfis_task.cancel()
            try:
                await monitor_perfis_task
            except asyncio.CancelledError:
                pass
            except Exception as erro:
                print(f"Monitor de perfis... ⚠ ERRO AO ENCERRAR: {erro}")
            else:
                print("Monitor de perfis... ✅ ENCERRADO")

        try:
            await encerrar_worker_whatsapp()
            print("Worker WhatsApp..... ✅ ENCERRADO")

        except Exception as erro:
            print(
                "Worker WhatsApp..... ⚠ ERRO AO ENCERRAR:",
                erro,
            )

        try:
            if client.is_connected():
                await client.disconnect()

            print("Telegram............ ✅ DESCONECTADO")

        except Exception as erro:
            print(
                "Telegram............ ⚠ ERRO AO DESCONECTAR:",
                erro,
            )

        try:
            relatorio = encerrar_execucao()
            if relatorio:
                print(f"Relatório auditoria. ✅ {relatorio}")
        except Exception as erro:
            print(f"Relatório auditoria. ⚠ ERRO: {erro}")

        print()
        print(
            "Os navegadores permanecerão abertos para preservar "
            "as sessões."
        )
        print("=" * 60)
        print()


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    try:
        with client:
            client.loop.run_until_complete(main())

    except KeyboardInterrupt:
        print()
        print("Robô encerrado.")