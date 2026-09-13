import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

API_ID = int(os.getenv("API_ID"))

API_HASH = os.getenv("API_HASH")

PHONE = os.getenv("PHONE")

AMAZON_TAG = os.getenv("AMAZON_TAG")

# Modo de execução: "production" prioriza baixo consumo;
# "development" mantém diagnósticos detalhados.
BOT_MODE = (os.getenv("BOT_MODE") or "production").strip().lower()
MODO_PRODUCAO = BOT_MODE == "production"
DIAGNOSTICOS_DETALHADOS = (
    os.getenv("DIAGNOSTICOS_DETALHADOS", "false").strip().lower()
    in {"1", "true", "sim", "yes", "on"}
)
MONITORAR_PERFIS = (
    os.getenv("MONITORAR_PERFIS", "false").strip().lower()
    in {"1", "true", "sim", "yes", "on"}
)


def _ler_booleano(nome: str, padrao: bool = False) -> bool:
    valor = os.getenv(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in {"1", "true", "sim", "yes", "on"}


# Saída detalhada no terminal é útil no desenvolvimento, mas gera limpeza de
# tela, consultas extras ao banco e muito texto a cada promoção.
EXIBIR_DIAGNOSTICO_TERMINAL = _ler_booleano(
    "EXIBIR_DIAGNOSTICO_TERMINAL",
    padrao=not MODO_PRODUCAO,
)

EXIBIR_HISTORICO_TERMINAL = _ler_booleano(
    "EXIBIR_HISTORICO_TERMINAL",
    padrao=not MODO_PRODUCAO,
)


# Limpeza conservadora dos caches dos perfis antes da abertura dos Chromes.
# O main.py ignora automaticamente um perfil se o navegador correspondente
# já estiver aberto.
LIMPAR_CACHE_NAVEGADORES = _ler_booleano(
    "LIMPAR_CACHE_NAVEGADORES",
    padrao=MODO_PRODUCAO,
)
