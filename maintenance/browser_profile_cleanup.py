from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


# Somente diretórios claramente descartáveis do Chromium.
# Não incluir aqui Cookies, IndexedDB, Local Storage, Session Storage,
# Network, Web Data ou Service Worker/CacheStorage.
PASTAS_DESCARTAVEIS = {
    "Cache",
    "Code Cache",
    "GPUCache",
    "GrShaderCache",
    "ShaderCache",
    "DawnCache",
    "BrowserMetrics",
    "Crashpad",
    "component_crx_cache",
    "extensions_crx_cache",
}


@dataclass(slots=True)
class ResultadoLimpezaPerfil:
    perfil: str
    caminho: str
    removidos: int = 0
    bytes_liberados: int = 0
    erros: int = 0
    ignorado: bool = False
    motivo: str = ""


def _tamanho_arquivo_ou_pasta(caminho: Path) -> int:
    try:
        if caminho.is_file() or caminho.is_symlink():
            return caminho.stat().st_size
    except OSError:
        return 0

    total = 0
    try:
        for item in caminho.rglob("*"):
            try:
                if item.is_file() and not item.is_symlink():
                    total += item.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total


def _formatar_bytes(valor: int) -> str:
    numero = float(max(0, valor))
    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if numero < 1024 or unidade == "TB":
            return f"{numero:.2f} {unidade}"
        numero /= 1024
    return f"{numero:.2f} TB"


def limpar_perfil_seguro(
    perfil: Path,
    nome: str,
    *,
    navegador_aberto: bool = False,
) -> ResultadoLimpezaPerfil:
    """Remove somente caches conhecidos de um perfil Chromium.

    A função não tenta limpar um perfil cujo navegador esteja aberto.
    Falhas individuais são contabilizadas e nunca impedem a inicialização
    do bot.
    """

    perfil = perfil.resolve()
    resultado = ResultadoLimpezaPerfil(
        perfil=nome,
        caminho=str(perfil),
    )

    if navegador_aberto:
        resultado.ignorado = True
        resultado.motivo = "navegador já está aberto"
        return resultado

    if not perfil.exists():
        resultado.ignorado = True
        resultado.motivo = "perfil ainda não existe"
        return resultado

    candidatos: list[Path] = []

    try:
        # Copiamos a lista antes de apagar para não alterar a árvore durante
        # a própria iteração do rglob.
        for caminho in perfil.rglob("*"):
            try:
                if caminho.is_dir() and caminho.name in PASTAS_DESCARTAVEIS:
                    candidatos.append(caminho)
            except OSError:
                continue
    except OSError:
        resultado.erros += 1
        return resultado

    # Remove primeiro os caminhos mais profundos, evitando colisões caso um
    # diretório descartável contenha outro diretório também descartável.
    candidatos.sort(key=lambda p: len(p.parts), reverse=True)

    removidos_ancestrais: list[Path] = []
    for caminho in candidatos:
        if any(ancestral in caminho.parents for ancestral in removidos_ancestrais):
            continue
        if not caminho.exists():
            continue

        tamanho = _tamanho_arquivo_ou_pasta(caminho)

        try:
            shutil.rmtree(caminho)
        except FileNotFoundError:
            continue
        except (OSError, PermissionError):
            resultado.erros += 1
            continue

        resultado.removidos += 1
        resultado.bytes_liberados += tamanho
        removidos_ancestrais.append(caminho)

    return resultado


def imprimir_resultado_limpeza(resultado: ResultadoLimpezaPerfil) -> None:
    if resultado.ignorado:
        print(
            f"{resultado.perfil:<21} ⏭ IGNORADO "
            f"({resultado.motivo})"
        )
        return

    status = "✅" if resultado.erros == 0 else "⚠"
    print(
        f"{resultado.perfil:<21} {status} "
        f"{_formatar_bytes(resultado.bytes_liberados)} liberados "
        f"({resultado.removidos} pasta(s), {resultado.erros} erro(s))"
    )
