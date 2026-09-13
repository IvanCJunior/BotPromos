from __future__ import annotations

from pathlib import Path

PASTA_PROJETO = Path(__file__).resolve().parents[1]
PASTA_DOWNLOADS = (PASTA_PROJETO / "downloads").resolve()


def apagar_imagem_temporaria(caminho_imagem: str | None) -> tuple[bool, str]:
    """Apaga somente arquivos localizados dentro de downloads/."""
    if not caminho_imagem:
        return False, "SEM_IMAGEM"

    caminho = Path(caminho_imagem)
    if not caminho.is_absolute():
        caminho = PASTA_PROJETO / caminho

    try:
        resolvido = caminho.resolve(strict=False)
        resolvido.relative_to(PASTA_DOWNLOADS)
    except (OSError, ValueError):
        return False, "CAMINHO_FORA_DE_DOWNLOADS"

    if not resolvido.exists():
        return False, "ARQUIVO_JA_INEXISTENTE"
    if not resolvido.is_file():
        return False, "CAMINHO_NAO_E_ARQUIVO"

    try:
        resolvido.unlink()
    except OSError as erro:
        return False, f"{type(erro).__name__}: {erro}"

    try:
        pai = resolvido.parent
        while pai != PASTA_DOWNLOADS and pai.exists() and not any(pai.iterdir()):
            pai.rmdir()
            pai = pai.parent
    except OSError:
        pass

    return True, "APAGADA"
