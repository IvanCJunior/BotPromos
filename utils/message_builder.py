import re


def valor_valido(valor) -> bool:
    if valor is None:
        return False
    texto = str(valor).strip()
    if not texto:
        return False
    return texto.lower() not in {
        "não", "nao", "nenhum", "não encontrado", "nao encontrado",
        "desconhecido", "none", "null", "-",
    }


def substituir_primeira_linha(texto_original: str, nova_chamada: str) -> str:
    linhas = (texto_original or "").splitlines()
    if not nova_chamada.strip():
        return texto_original or ""

    for indice, linha in enumerate(linhas):
        if linha.strip():
            linhas[indice] = nova_chamada.strip()
            return "\n".join(linhas)

    return nova_chamada.strip()


def remover_links(texto: str) -> str:
    texto = re.sub(r"https?://\S+", "", texto or "", flags=re.IGNORECASE)
    linhas = [linha.rstrip() for linha in texto.splitlines()]

    resultado = []
    vazio_anterior = False
    for linha in linhas:
        vazia = not linha.strip()
        if vazia and vazio_anterior:
            continue
        resultado.append(linha)
        vazio_anterior = vazia

    return "\n".join(resultado).strip()


def contem_preco(texto: str) -> bool:
    return bool(re.search(r"R\$\s*\d", texto or "", re.IGNORECASE))


def contem_cupom(texto: str) -> bool:
    return bool(re.search(r"\b(?:cupom|código|codigo)\b", texto or "", re.IGNORECASE))


def montar_mensagem_final(
    texto_original: str,
    texto_reformulado: str,
    preco,
    cupom,
    link_afiliado: str,
) -> str:
    """
    Altera somente a primeira linha da promoção.
    Todo o restante do texto original é preservado, inclusive descrição,
    nome do produto, preço, cupom e condições. O link original é removido
    e substituído pelo link final do bot.
    """

    corpo = substituir_primeira_linha(
        texto_original=texto_original,
        nova_chamada=texto_reformulado,
    )
    corpo = remover_links(corpo)

    partes = [corpo] if corpo else []

    # Só acrescenta preço/cupom quando eles não estavam no texto original.
    if valor_valido(preco) and not contem_preco(corpo):
        preco_texto = str(preco).strip()
        partes.append(
            f"💰 {preco_texto}" if preco_texto.lower().startswith("r$")
            else f"💰 R$ {preco_texto}"
        )

    if valor_valido(cupom) and not contem_cupom(corpo):
        partes.append(f"🎟 Cupom: {str(cupom).strip()}")

    if link_afiliado and str(link_afiliado).strip():
        partes.append(f"🔗 {str(link_afiliado).strip()}")

    return "\n\n".join(parte for parte in partes if parte).strip()
