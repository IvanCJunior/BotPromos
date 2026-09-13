import re
from typing import Optional
from urllib.parse import urlparse


# ============================================================
# LINKS
# ============================================================

def extrair_links(texto: str) -> list[str]:
    """
    Extrai links HTTP/HTTPS existentes no texto.

    Remove caracteres que normalmente aparecem grudados no final
    do endereço, como parênteses, vírgulas e pontos.
    """

    if not texto:
        return []

    links_encontrados = re.findall(
        r"https?://[^\s<>\"']+",
        texto,
        flags=re.IGNORECASE,
    )

    links_limpos: list[str] = []

    for link in links_encontrados:
        link = link.rstrip(".,;:!?)]}>\"'")

        if link and link not in links_limpos:
            links_limpos.append(link)

    return links_limpos


# ============================================================
# PREÇO
# ============================================================

def _formatar_preco(valor: str) -> str:
    """
    Padroniza o preço no formato brasileiro.

    Exemplos:
        59       -> R$ 59
        59,90    -> R$ 59,90
        R$59     -> R$ 59
        R$ 59,90 -> R$ 59,90
    """

    if not valor:
        return ""

    valor = str(valor).strip()

    valor = re.sub(
        r"(?i)^r\$\s*",
        "",
        valor,
    )

    valor = valor.strip(" \t\n\r.,;:-")

    if not valor:
        return ""

    return f"R$ {valor}"


def _normalizar_valor_numerico(valor: str) -> Optional[float]:
    """
    Converte um preço brasileiro para número.

    Exemplos:
        1.299,90 -> 1299.90
        159      -> 159.00
        59,90    -> 59.90
    """

    if not valor:
        return None

    valor = str(valor).strip()

    valor = re.sub(
        r"(?i)r\$\s*",
        "",
        valor,
    )

    valor = valor.replace(".", "")
    valor = valor.replace(",", ".")

    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None

    if numero <= 0:
        return None

    return numero


def _extrair_valor_do_resultado(resultado: re.Match) -> str:
    """
    Obtém o primeiro grupo preenchido de um resultado regex.
    """

    for grupo in resultado.groups():
        if grupo:
            return grupo

    return resultado.group(0)


def extrair_preco(texto: str) -> str:
    """
    Extrai preferencialmente o preço promocional.

    Ordem de prioridade:

    1. Preço depois de "por"
    2. Preço junto de "Pix" ou "à vista"
    3. Preço depois de palavras como "agora" e "oferta"
    4. Último preço escrito com R$
    5. Valor decimal sem R$, como 132,39
    6. Valor inteiro em contextos claros de promoção

    A função procura evitar:

    - número de parcelas;
    - porcentagem de desconto;
    - valores antigos quando existe "de ... por ...";
    - números de cupons;
    - quantidade de unidades.
    """

    if not texto:
        return ""

    texto = str(texto)

    valor_com_ou_sem_rs = (
        r"(?:R\$\s*)?"
        r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?"
        r"|\d+(?:,\d{2})?)"
    )

    # --------------------------------------------------------
    # 1. Valor depois de "por"
    #
    # Exemplos:
    # De R$ 159 por R$ 59
    # De 159 por 59 no Pix
    # Por apenas 132,39
    # --------------------------------------------------------

    padroes_por = [
        rf"\bpor\s+(?:apenas\s+|só\s+|somente\s+)?{valor_com_ou_sem_rs}",
        rf"\bsaindo\s+por\s+{valor_com_ou_sem_rs}",
        rf"\bfica\s+por\s+{valor_com_ou_sem_rs}",
    ]

    for padrao in padroes_por:
        resultado = re.search(
            padrao,
            texto,
            flags=re.IGNORECASE,
        )

        if resultado:
            valor = _extrair_valor_do_resultado(resultado)
            return _formatar_preco(valor)

    # --------------------------------------------------------
    # 2. Valores relacionados a Pix ou pagamento à vista
    #
    # Exemplos:
    # No Pix: R$ 59
    # Pix 59,90
    # R$ 59 no Pix
    # 59 à vista
    # --------------------------------------------------------

    padroes_pix = [
        (
            rf"\b(?:no\s+pix|via\s+pix|pix|à\s+vista|a\s+vista)"
            rf"\s*[:\-]?\s*{valor_com_ou_sem_rs}"
        ),
        (
            rf"{valor_com_ou_sem_rs}"
            rf"\s*(?:no\s+pix|via\s+pix|pix|à\s+vista|a\s+vista)\b"
        ),
    ]

    for padrao in padroes_pix:
        resultado = re.search(
            padrao,
            texto,
            flags=re.IGNORECASE,
        )

        if resultado:
            valor = _extrair_valor_do_resultado(resultado)
            return _formatar_preco(valor)

    # --------------------------------------------------------
    # 3. Termos promocionais explícitos
    #
    # Exemplos:
    # Agora R$ 89
    # Oferta: 59,90
    # Preço final R$ 120
    # --------------------------------------------------------

    padroes_promocionais = [
        (
            rf"\b(?:agora|oferta|preço\s+final|valor\s+final)"
            rf"\s*[:\-]?\s*{valor_com_ou_sem_rs}"
        ),
        (
            rf"\b(?:apenas|somente|só)"
            rf"\s*{valor_com_ou_sem_rs}"
        ),
    ]

    for padrao in padroes_promocionais:
        resultado = re.search(
            padrao,
            texto,
            flags=re.IGNORECASE,
        )

        if resultado:
            valor = _extrair_valor_do_resultado(resultado)
            return _formatar_preco(valor)

    # --------------------------------------------------------
    # 4. Todos os valores explicitamente escritos com R$
    #
    # Quando existem vários valores, o último normalmente é
    # o promocional:
    #
    # De R$ 159 por R$ 59
    # --------------------------------------------------------

    valores_com_rs = re.findall(
        r"R\$\s*"
        r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?"
        r"|\d+(?:,\d{2})?)",
        texto,
        flags=re.IGNORECASE,
    )

    if valores_com_rs:
        return _formatar_preco(valores_com_rs[-1])

    # --------------------------------------------------------
    # 5. Valores decimais sem R$
    #
    # Exemplo:
    # 132,39 em até quatro vezes
    #
    # Valores decimais são mais seguros que inteiros porque
    # dificilmente representam quantidade ou número de parcela.
    # --------------------------------------------------------

    valores_decimais: list[str] = []

    for linha in texto.splitlines():
        linha = linha.strip()

        if not linha:
            continue

        if "%" in linha:
            continue

        encontrados = re.findall(
            r"(?<![\d.,])"
            r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})"
            r"(?![\d.,])",
            linha,
        )

        valores_decimais.extend(encontrados)

    if valores_decimais:
        return _formatar_preco(valores_decimais[-1])

    # --------------------------------------------------------
    # 6. Valores inteiros em contextos claramente promocionais
    #
    # Exemplos:
    # por 59
    # preço 89
    # oferta 120
    #
    # Esta etapa fica por último para evitar interpretar como
    # preço números de parcelas, percentuais ou quantidades.
    # --------------------------------------------------------

    padrao_inteiro_contextual = re.search(
        r"\b(?:preço|valor|oferta|apenas|somente|agora)"
        r"\s*[:\-]?\s*"
        r"(?:R\$\s*)?"
        r"(\d{2,6})\b",
        texto,
        flags=re.IGNORECASE,
    )

    if padrao_inteiro_contextual:
        valor = padrao_inteiro_contextual.group(1)
        return _formatar_preco(valor)

    return ""


# ============================================================
# CUPOM
# ============================================================

def extrair_cupom(texto: str) -> str:
    """
    Extrai códigos reais de cupom.

    Reconhece exemplos como:

        Cupom: PROMO20
        Cupom PROMO20
        Código: OFERTA10
        Use o cupom VARDOMELI

    Evita capturar palavras soltas como:

        D
        DE
        OFF
        PIX
        DISPONÍVEL
        DESCONTO
    """

    if not texto:
        return ""

    texto = str(texto)

    palavras_ignoradas = {
        "A",
        "AS",
        "COM",
        "DA",
        "DAS",
        "DE",
        "DESCONTO",
        "DISPONIVEL",
        "DISPONÍVEL",
        "DO",
        "DOS",
        "EM",
        "NA",
        "NAS",
        "NO",
        "NOS",
        "OFF",
        "PARA",
        "PIX",
        "RECORRENCIA",
        "RECORRÊNCIA",
        "SELECIONE",
        "UM",
        "UMA",
        "USE",
    }

    padroes = [
        # Cupom: PROMO20
        # Código - OFERTA10
        (
            r"\b(?:cupom|c[oó]digo)"
            r"\s*[:=\-]\s*"
            r"([A-Za-z0-9][A-Za-z0-9_-]{2,})\b"
        ),

        # Cupom PROMO20
        # Código OFERTA10
        (
            r"\b(?:cupom|c[oó]digo)"
            r"\s+"
            r"([A-Za-z0-9][A-Za-z0-9_-]{2,})\b"
        ),

        # Use o cupom PROMO20
        (
            r"\buse\s+(?:o\s+)?(?:cupom|c[oó]digo)"
            r"\s*[:=\-]?\s*"
            r"([A-Za-z0-9][A-Za-z0-9_-]{2,})\b"
        ),

        # Com o cupom PROMO20
        (
            r"\bcom\s+(?:o\s+)?(?:cupom|c[oó]digo)"
            r"\s*[:=\-]?\s*"
            r"([A-Za-z0-9][A-Za-z0-9_-]{2,})\b"
        ),
    ]

    for padrao in padroes:
        resultados = re.finditer(
            padrao,
            texto,
            flags=re.IGNORECASE,
        )

        for resultado in resultados:
            cupom = resultado.group(1).strip()

            cupom_normalizado = cupom.upper()

            if cupom_normalizado in palavras_ignoradas:
                continue

            # Evita resultados muito curtos, como "D".
            if len(cupom) < 3:
                continue

            # Evita interpretar um número puro como cupom.
            if cupom.isdigit():
                continue

            # Exige ao menos uma letra.
            if not re.search(r"[A-Za-z]", cupom):
                continue

            return cupom

    return ""


# ============================================================
# LOJA
# ============================================================

def descobrir_loja(link: str) -> str:
    """
    Identifica somente as lojas mantidas pelo projeto:

    - Mercado Livre
    - Amazon

    Qualquer outra loja será considerada desconhecida.
    """

    if not link:
        return "Desconhecida"

    link_normalizado = str(link).strip().lower()

    # Tenta analisar apenas o domínio para evitar falsos positivos.
    try:
        endereco = urlparse(link_normalizado)
        dominio = endereco.netloc.lower()

        if dominio.startswith("www."):
            dominio = dominio[4:]
    except (TypeError, ValueError):
        dominio = link_normalizado

    dominios_amazon = (
        "amazon.com.br",
        "amazon.com",
        "amzn.to",
        "amzn.com",
        "a.co",
    )

    dominios_mercado_livre = (
        "mercadolivre.com.br",
        "mercadolivre.com",
        "mercadolibre.com",
        "mercadolibre.com.br",
        "meli.la",
        "meli.co",
    )

    if any(
        dominio == item or dominio.endswith(f".{item}")
        for item in dominios_amazon
    ):
        return "Amazon"

    if any(
        dominio == item or dominio.endswith(f".{item}")
        for item in dominios_mercado_livre
    ):
        return "Mercado Livre"

    # Compatibilidade com links que eventualmente chegam incompletos.
    if any(item in link_normalizado for item in dominios_amazon):
        return "Amazon"

    if any(item in link_normalizado for item in dominios_mercado_livre):
        return "Mercado Livre"

    return "Desconhecida"