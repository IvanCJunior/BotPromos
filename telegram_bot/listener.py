# telegram_bot/listener.py

from __future__ import annotations

import re
from datetime import datetime
from time import perf_counter
from typing import Any

from telethon import events

from affiliate.manager import gerar_link_afiliado
from ai.rewriter import reformular_promocao
from config.channels import CHANNELS
from config.settings import (
    EXIBIR_DIAGNOSTICO_TERMINAL,
    EXIBIR_HISTORICO_TERMINAL,
)
from database.database import (
    extrair_identificador_produto_ml,
    promocao_existe,
    salvar_promocao,
)
from diagnostics.audit import (
    finalizar_promocao,
    nova_promocao as iniciar_auditoria_promocao,
    registrar_alerta,
    registrar_erro,
    registrar_etapa,
)
from telegram_bot.client import client
from telegram_bot.downloader import baixar_imagem
from telegram_bot.filters import e_promocao
from telegram_bot.parser import (
    descobrir_loja,
    extrair_cupom,
    extrair_links,
    extrair_preco,
)
from utils.link_resolver import resolver_link
from utils.message_builder import montar_mensagem_final
from whatsapp.queue import adicionar_promocao_na_fila


# A Amazon continua reconhecida pelo parser, mas não é processada.
LOJA_ATIVA = "Mercado Livre"
CODIGO_AMAZON_DESABILITADA = "AMAZON_DESABILITADA"
CODIGO_SEM_LINK_VALIDO = "SEM_LINK_VALIDO"




def _mostrar_resumo_producao(
    *,
    canal: str,
    telegram_id: int,
    loja: str,
    preco: str,
    cupom: str,
    link_afiliado: str,
    imagem: str | None,
) -> None:
    """Mostra somente informações essenciais no modo de produção."""
    print()
    print("-" * 60)
    print("PROMOÇÃO PROCESSADA")
    print("-" * 60)
    print(f"Canal............... {canal or 'Não identificado'}")
    print(f"Telegram ID......... {telegram_id}")
    print(f"Loja................ {loja or 'Não identificada'}")
    print(f"Preço............... {preco or 'Não identificado'}")
    print(f"Cupom............... {cupom or 'Não'}")
    print(f"Link afiliado....... {'OK' if link_afiliado else 'FALHOU'}")
    print(f"Imagem.............. {'OK' if imagem else 'NÃO'}")
    print("Status.............. ENVIADA PARA A FILA")
    print("-" * 60)
    print()

# ============================================================
# LINKS
# ============================================================


def normalizar_link(link: str) -> str:
    """Remove espaços e a barra final de um endereço."""
    return (link or "").strip().rstrip("/")


def _adicionar_link_unico(lista: list[str], link: str) -> None:
    """Adiciona um link não vazio sem repetir endereços já encontrados."""
    link_normalizado = (link or "").strip()

    if link_normalizado and link_normalizado not in lista:
        lista.append(link_normalizado)


def extrair_links_da_mensagem(event: Any, texto: str) -> list[str]:
    """
    Extrai links visíveis e links embutidos nas entidades do Telegram.

    A ordem original é preservada porque o primeiro link válido costuma ser
    o produto principal da promoção.
    """
    links: list[str] = []
    mensagem = getattr(event, "message", None)
    entidades = getattr(mensagem, "entities", None) or []

    for entidade in entidades:
        _adicionar_link_unico(links, getattr(entidade, "url", ""))

        offset = getattr(entidade, "offset", None)
        length = getattr(entidade, "length", None)

        if isinstance(offset, int) and isinstance(length, int):
            trecho = texto[offset : offset + length].strip()

            if trecho.lower().startswith(("http://", "https://")):
                _adicionar_link_unico(links, trecho)

    for link in extrair_links(texto):
        _adicionar_link_unico(links, link)

    return links


def _resolver_link_com_seguranca(link: str) -> str:
    """Tenta resolver um encurtador sem interromper o processamento."""
    try:
        return resolver_link(link) or link
    except Exception:
        return link


def escolher_link_da_promocao(
    links: list[str],
) -> tuple[str, str, str, str]:
    """
    Escolhe apenas links do Mercado Livre.

    A Amazon é reconhecida, porém ignorada antes da resolução e da conversão.

    Retorna:
        link_original,
        link_processado,
        loja,
        motivo_ignorado.
    """
    amazon_encontrada = ""

    for link_original in links:
        loja_original = descobrir_loja(link_original)

        # Não resolve nem converte links já reconhecidos como Amazon.
        if loja_original == "Amazon":
            if not amazon_encontrada:
                amazon_encontrada = link_original
            continue

        # Um link direto do Mercado Livre pode seguir imediatamente.
        if loja_original == LOJA_ATIVA:
            return link_original, link_original, LOJA_ATIVA, ""

        # Links desconhecidos podem ser encurtadores do Mercado Livre.
        link_processado = _resolver_link_com_seguranca(link_original)
        loja_resolvida = descobrir_loja(link_processado)

        if loja_resolvida == "Amazon":
            if not amazon_encontrada:
                amazon_encontrada = link_original
            continue

        if loja_resolvida == LOJA_ATIVA:
            return link_original, link_processado, LOJA_ATIVA, ""

    if amazon_encontrada:
        return (
            amazon_encontrada,
            amazon_encontrada,
            "Amazon",
            CODIGO_AMAZON_DESABILITADA,
        )

    return "", "", "Desconhecida", CODIGO_SEM_LINK_VALIDO


# ============================================================
# VALIDAÇÕES E DUPLICIDADE
# ============================================================


def _quantidade_preco_na_mensagem(mensagem: str, preco: str) -> int:
    """Conta quantas vezes o preço extraído aparece na mensagem final."""
    if not mensagem or not preco:
        return 0

    numeros = re.findall(r"\d[\d.]*,\d{2}", preco)

    if not numeros:
        numeros = re.findall(r"\d+(?:[.,]\d{1,2})?", preco)

    if not numeros:
        return 0

    alvo = numeros[-1].replace(".", "").replace(",", ".")
    contagem = 0

    for achado in re.findall(r"\d[\d.]*,\d{2}", mensagem):
        normalizado = achado.replace(".", "").replace(",", ".")

        if normalizado == alvo:
            contagem += 1

    return contagem


async def preparar_identificador_duplicidade_ml(
    link_original: str,
    link_processado: str,
    texto: str,
) -> tuple[str, str]:
    """
    Obtém um endereço verificável e o código MLB antes do Link Builder.

    Se o identificador já estiver presente no link ou no texto, evita uma
    resolução adicional. Se a resolução falhar, mantém o endereço recebido.
    """
    link_verificacao = link_processado or link_original
    produto_id = extrair_identificador_produto_ml(
        link_verificacao,
        link_original,
        texto,
    )

    if produto_id:
        return link_verificacao, produto_id

    link_resolvido = _resolver_link_com_seguranca(link_verificacao)

    if link_resolvido and descobrir_loja(link_resolvido) == LOJA_ATIVA:
        link_verificacao = link_resolvido

    produto_id = extrair_identificador_produto_ml(
        link_verificacao,
        link_original,
        texto,
    )

    return link_verificacao, produto_id


def _promocao_ja_existe(
    *,
    link: str,
    produto_id: str,
    telegram_id: int,
    canal: str,
    texto: str,
) -> bool:
    """Centraliza a chamada ao banco usada nas duas proteções de duplicidade."""
    return promocao_existe(
        link=link,
        produto_id=produto_id,
        telegram_id=telegram_id,
        canal=canal,
        mensagem=texto,
    )


# ============================================================
# SAÍDAS DO TERMINAL
# ============================================================


def mostrar_promocao_ignorada(loja: str, link: str) -> None:
    print()
    print("-" * 70)
    print("PROMOÇÃO IGNORADA")
    print("-" * 70)
    print(f"Loja................ {loja or 'Desconhecida'}")
    print("Motivo.............. Nenhum link válido do Mercado Livre foi encontrado.")

    if link:
        print(f"Link recebido....... {link}")

    print("-" * 70)
    print()


def mostrar_amazon_desabilitada(link: str) -> None:
    print()
    print("-" * 70)
    print("PROMOÇÃO IGNORADA")
    print("-" * 70)
    print("Loja................ Amazon")
    print("Motivo.............. Amazon temporariamente desativada.")

    if link:
        print(f"Link recebido....... {link}")

    print("-" * 70)
    print()


def mostrar_promocao_cancelada_mercado_livre(link: str, motivo: str) -> None:
    print()
    print("-" * 70)
    print("PROMOÇÃO DO MERCADO LIVRE CANCELADA")
    print("-" * 70)
    print(f"Motivo.............. {motivo}")

    if link:
        print(f"Link recebido....... {link}")

    print("Envio ao WhatsApp... ❌ CANCELADO")
    print("-" * 70)
    print()


def mostrar_promocao_repetida(
    loja: str,
    produto_id: str,
    link: str,
) -> None:
    print()
    print("-" * 70)
    print("⚠ PROMOÇÃO REPETIDA")
    print("-" * 70)
    print(f"Loja................ {loja or 'Desconhecida'}")

    if produto_id:
        print(f"Produto............. {produto_id}")
    else:
        print("Produto............. Reconhecido pelo texto da promoção")

    if link:
        print(f"Link recebido....... {link}")

    print("Ação................ Ignorada; seguindo para a próxima.")
    print("-" * 70)
    print()


# ============================================================
# ETAPAS DO PROCESSAMENTO
# ============================================================


def _ignorar_mensagem_que_nao_e_promocao(audit_id: str) -> None:
    motivo = "A mensagem não passou pelo filtro de promoção."

    registrar_etapa(
        audit_id,
        "FILTRO",
        status="IGNORADA",
        codigo="NAO_PARECE_PROMOCAO",
        motivo=motivo,
    )
    finalizar_promocao(
        audit_id,
        "IGNORADA",
        etapa="FILTRO",
        codigo="NAO_PARECE_PROMOCAO",
        motivo=motivo,
    )


def _ignorar_amazon(
    *,
    audit_id: str,
    link_original: str,
    links_encontrados: list[str],
) -> None:
    mostrar_amazon_desabilitada(link_original)

    registrar_etapa(
        audit_id,
        "FILTRO_LOJA",
        status="IGNORADA",
        codigo=CODIGO_AMAZON_DESABILITADA,
        motivo=(
            "A promoção da Amazon foi ignorada antes da resolução "
            "e da conversão do link."
        ),
        loja="Amazon",
        links_encontrados=links_encontrados,
        link_original=link_original,
    )

    finalizar_promocao(
        audit_id,
        "IGNORADA",
        etapa="FILTRO_LOJA",
        codigo=CODIGO_AMAZON_DESABILITADA,
        motivo="Amazon temporariamente desativada.",
        loja="Amazon",
        link_original=link_original,
    )


def _ignorar_sem_link_valido(
    *,
    audit_id: str,
    links_encontrados: list[str],
) -> None:
    primeiro_link = links_encontrados[0] if links_encontrados else ""
    mostrar_promocao_ignorada("Desconhecida", primeiro_link)

    finalizar_promocao(
        audit_id,
        "IGNORADA",
        etapa="EXTRACAO_LINK",
        codigo=CODIGO_SEM_LINK_VALIDO,
        motivo="Nenhum link válido do Mercado Livre foi encontrado.",
        links_encontrados=links_encontrados,
    )


def _finalizar_como_duplicada(
    *,
    audit_id: str,
    etapa: str,
    codigo: str,
    motivo: str,
    loja: str,
    produto_id: str,
    link_original: str,
    link_processado: str = "",
    link_final: str = "",
) -> None:
    mostrar_promocao_repetida(
        loja=loja,
        produto_id=produto_id,
        link=link_original,
    )

    dados_etapa = {
        "loja": loja,
        "produto_id": produto_id,
        "link_original": link_original,
    }

    if link_processado:
        dados_etapa["link_processado"] = link_processado

    if link_final:
        dados_etapa["link_final"] = link_final

    registrar_etapa(
        audit_id,
        etapa,
        status="DUPLICADA",
        codigo=codigo,
        **dados_etapa,
    )

    finalizar_promocao(
        audit_id,
        "DUPLICADA",
        etapa=etapa,
        codigo=codigo,
        motivo=motivo,
        **dados_etapa,
    )


async def _converter_link_mercado_livre(
    *,
    audit_id: str,
    loja: str,
    link_original: str,
    link_processado: str,
) -> str:
    inicio = perf_counter()

    try:
        link_afiliado = await gerar_link_afiliado(
            loja,
            link_processado,
            audit_id=audit_id,
        )

        registrar_etapa(
            audit_id,
            "CONVERSAO_AFILIADO",
            status="OK" if link_afiliado else "ERRO",
            codigo=(
                "LINK_AFILIADO_GERADO"
                if link_afiliado
                else "LINK_AFILIADO_VAZIO"
            ),
            duracao_ms=(perf_counter() - inicio) * 1000,
            loja=loja,
            link_original=link_original,
            link_processado=link_processado,
            link_afiliado=link_afiliado,
        )

        return link_afiliado or ""

    except Exception as erro:
        registrar_erro(
            audit_id,
            "CONVERSAO_AFILIADO",
            erro,
            codigo="FALHA_CONVERSAO_AFILIADO",
            loja=loja,
            link_original=link_original,
            link_processado=link_processado,
            duracao_ms=(perf_counter() - inicio) * 1000,
        )
        print(f"\n⚠ Não foi possível converter o link: {erro}\n")
        return ""


async def _reformular_texto(
    *,
    audit_id: str,
    texto: str,
    loja: str,
    preco: str,
    cupom: str,
) -> str:
    inicio = perf_counter()

    try:
        texto_reformulado = await reformular_promocao(
            texto_original=texto,
            loja=loja,
            preco=preco,
            cupom=cupom,
            audit_id=audit_id,
        )

        registrar_etapa(
            audit_id,
            "IA",
            status="OK" if texto_reformulado else "ALERTA",
            codigo=(
                "IA_REFORMULACAO_APROVADA"
                if texto_reformulado
                else "IA_TEXTO_ORIGINAL_MANTIDO"
            ),
            motivo=(
                ""
                if texto_reformulado
                else (
                    "A IA não produziu uma chamada aprovada; "
                    "o original será mantido."
                )
            ),
            duracao_ms=(perf_counter() - inicio) * 1000,
            texto_reformulado=texto_reformulado,
        )

        return texto_reformulado or ""

    except Exception as erro:
        registrar_erro(
            audit_id,
            "IA",
            erro,
            codigo="IA_FALHA_REFORMULACAO",
            duracao_ms=(perf_counter() - inicio) * 1000,
        )
        print(f"\n⚠ Não foi possível reformular o texto: {erro}")
        print("O bot continuará usando o texto original.\n")
        return ""


async def _baixar_imagem_com_seguranca(
    *,
    audit_id: str,
    event: Any,
) -> Any:
    inicio = perf_counter()

    try:
        imagem = await baixar_imagem(event)

        registrar_etapa(
            audit_id,
            "DOWNLOAD_IMAGEM",
            status="OK" if imagem else "ALERTA",
            codigo="IMAGEM_BAIXADA" if imagem else "SEM_IMAGEM",
            duracao_ms=(perf_counter() - inicio) * 1000,
            imagem=imagem,
        )

        if not imagem:
            registrar_alerta(
                audit_id,
                "IMAGEM_AUSENTE",
                "A promoção será enviada sem imagem.",
            )

        return imagem

    except Exception as erro:
        registrar_erro(
            audit_id,
            "DOWNLOAD_IMAGEM",
            erro,
            codigo="FALHA_DOWNLOAD_IMAGEM",
            duracao_ms=(perf_counter() - inicio) * 1000,
        )
        print(f"\n⚠ Não foi possível baixar a imagem: {erro}\n")
        return None


def _registrar_validacoes_mensagem(
    *,
    audit_id: str,
    mensagem_final: str,
    link_final: str,
    link_afiliado: str,
    link_original: str,
    loja: str,
    preco: str,
) -> None:
    if link_final and link_final not in mensagem_final:
        registrar_alerta(
            audit_id,
            "MENSAGEM_SEM_LINK_FINAL",
            "O link final não foi encontrado literalmente na mensagem montada.",
            link_final=link_final,
        )

    if not link_afiliado and link_final == link_original:
        registrar_alerta(
            audit_id,
            "LINK_ORIGINAL_USADO",
            "A mensagem usa o link original porque a conversão não foi confirmada.",
            loja=loja,
        )

    ocorrencias_preco = _quantidade_preco_na_mensagem(
        mensagem_final,
        preco,
    )

    if ocorrencias_preco > 1:
        registrar_alerta(
            audit_id,
            "PRECO_REPETIDO",
            f"O preço apareceu {ocorrencias_preco} vezes na mensagem final.",
            preco=preco,
            ocorrencias=ocorrencias_preco,
        )


def _salvar_promocao_com_seguranca(
    *,
    audit_id: str,
    telegram_id: int,
    canal: str,
    texto: str,
    link_final: str,
    preco: str,
    cupom: str,
    loja: str,
    imagem: Any,
    produto_id: str,
) -> None:
    try:
        salvar_promocao(
            telegram_id,
            canal,
            datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            texto,
            link_final,
            preco,
            cupom,
            loja,
            imagem,
            produto_id=produto_id,
        )
        registrar_etapa(
            audit_id,
            "BANCO",
            codigo="PROMOCAO_SALVA",
            link_final=link_final,
        )
    except Exception as erro:
        registrar_erro(
            audit_id,
            "BANCO",
            erro,
            codigo="FALHA_SALVAR_PROMOCAO",
        )


async def _adicionar_na_fila_whatsapp(
    *,
    audit_id: str,
    inicio_total: float,
    mensagem_final: str,
    imagem: Any,
    canal: str,
    telegram_id: int,
) -> bool:
    try:
        await adicionar_promocao_na_fila(
            mensagem=mensagem_final,
            imagem=imagem,
            origem=canal,
            telegram_id=telegram_id,
            audit_id=audit_id,
        )

        registrar_etapa(
            audit_id,
            "FILA_WHATSAPP",
            codigo="ADICIONADA_A_FILA",
            duracao_ms=(perf_counter() - inicio_total) * 1000,
        )
        return True

    except Exception as erro:
        registrar_erro(
            audit_id,
            "FILA_WHATSAPP",
            erro,
            codigo="FALHA_ADICIONAR_FILA",
        )
        finalizar_promocao(
            audit_id,
            "ERRO",
            etapa="FILA_WHATSAPP",
            codigo="FALHA_ADICIONAR_FILA",
            motivo=str(erro),
        )
        print(
            "\n⚠ Não foi possível adicionar a promoção "
            f"à fila do WhatsApp: {erro}\n"
        )
        return False


# ============================================================
# LISTENER PRINCIPAL
# ============================================================


@client.on(events.NewMessage)
async def nova_promocao(event: Any) -> None:
    """Recebe, valida, converte e encaminha uma promoção ao WhatsApp."""
    if event.chat_id not in CHANNELS:
        return

    texto = event.raw_text or ""
    canal = CHANNELS[event.chat_id]
    telegram_id = event.id
    inicio_total = perf_counter()

    audit_id = iniciar_auditoria_promocao(
        canal=canal,
        telegram_id=telegram_id,
        texto=texto,
        chat_id=event.chat_id,
    )

    # --------------------------------------------------------
    # 1. Filtro de promoção
    # --------------------------------------------------------

    if not e_promocao(texto):
        _ignorar_mensagem_que_nao_e_promocao(audit_id)
        return

    registrar_etapa(
        audit_id,
        "FILTRO",
        codigo="PROMOCAO_RECONHECIDA",
    )

    # --------------------------------------------------------
    # 2. Extração e seleção do link
    # --------------------------------------------------------

    links_encontrados = extrair_links_da_mensagem(event, texto)
    (
        link_original,
        link_processado,
        loja,
        motivo_ignorado,
    ) = escolher_link_da_promocao(links_encontrados)

    if motivo_ignorado == CODIGO_AMAZON_DESABILITADA:
        _ignorar_amazon(
            audit_id=audit_id,
            link_original=link_original,
            links_encontrados=links_encontrados,
        )
        return

    registrar_etapa(
        audit_id,
        "EXTRACAO_LINK",
        status="OK" if link_original else "ERRO",
        codigo=(
            "LINK_VALIDO_ENCONTRADO"
            if link_original
            else CODIGO_SEM_LINK_VALIDO
        ),
        loja=loja,
        links_encontrados=links_encontrados,
        link_original=link_original,
        link_processado=link_processado,
    )

    if not link_original:
        _ignorar_sem_link_valido(
            audit_id=audit_id,
            links_encontrados=links_encontrados,
        )
        return

    # --------------------------------------------------------
    # 3. Duplicidade antes da conversão
    # --------------------------------------------------------

    produto_id = ""

    if loja == LOJA_ATIVA:
        link_processado, produto_id = await preparar_identificador_duplicidade_ml(
            link_original=link_original,
            link_processado=link_processado,
            texto=texto,
        )

    if _promocao_ja_existe(
        link=link_processado or link_original,
        produto_id=produto_id,
        telegram_id=telegram_id,
        canal=canal,
        texto=texto,
    ):
        _finalizar_como_duplicada(
            audit_id=audit_id,
            etapa="DUPLICIDADE_ANTECIPADA",
            codigo="PROMOCAO_DUPLICADA_ANTES_DA_CONVERSAO",
            motivo=(
                "A promoção já estava registrada. Ela foi descartada antes "
                "da conversão do link de afiliado."
            ),
            loja=loja,
            produto_id=produto_id,
            link_original=link_original,
            link_processado=link_processado,
        )
        return

    registrar_etapa(
        audit_id,
        "DUPLICIDADE_ANTECIPADA",
        codigo="PROMOCAO_NOVA",
        loja=loja,
        produto_id=produto_id,
        link_original=link_original,
        link_processado=link_processado,
    )

    # --------------------------------------------------------
    # 4. Conversão do link de afiliado
    # --------------------------------------------------------

    link_afiliado = await _converter_link_mercado_livre(
        audit_id=audit_id,
        loja=loja,
        link_original=link_original,
        link_processado=link_processado,
    )
    conversao_confirmada = bool(link_afiliado)

    if loja == LOJA_ATIVA and not conversao_confirmada:
        motivo = (
            "O gerador de afiliados não devolveu um link. A promoção não será "
            "enviada para evitar publicar um link inválido."
        )
        mostrar_promocao_cancelada_mercado_livre(
            link_original,
            motivo,
        )
        finalizar_promocao(
            audit_id,
            "CANCELADA",
            etapa="CONVERSAO_AFILIADO",
            codigo="ML_LINK_AFILIADO_NAO_GERADO",
            motivo=motivo,
            loja=loja,
            link_original=link_original,
        )
        return

    link_final = link_afiliado or link_original

    # --------------------------------------------------------
    # 5. Segunda proteção contra duplicidade
    # --------------------------------------------------------

    if _promocao_ja_existe(
        link=link_final,
        produto_id=produto_id,
        telegram_id=telegram_id,
        canal=canal,
        texto=texto,
    ):
        _finalizar_como_duplicada(
            audit_id=audit_id,
            etapa="DUPLICIDADE",
            codigo="PROMOCAO_DUPLICADA",
            motivo="A promoção já estava registrada no banco.",
            loja=loja,
            produto_id=produto_id,
            link_original=link_original,
            link_final=link_final,
        )
        return

    # --------------------------------------------------------
    # 6. Extração de dados
    # --------------------------------------------------------

    preco = extrair_preco(texto)
    cupom = extrair_cupom(texto)

    registrar_etapa(
        audit_id,
        "EXTRACAO_DADOS",
        codigo="DADOS_EXTRAIDOS",
        preco=preco,
        cupom=cupom,
        loja=loja,
    )

    if not preco:
        registrar_alerta(
            audit_id,
            "MENSAGEM_SEM_PRECO",
            "Nenhum preço foi extraído.",
        )

    # --------------------------------------------------------
    # 7. IA e imagem
    # --------------------------------------------------------

    texto_reformulado = await _reformular_texto(
        audit_id=audit_id,
        texto=texto,
        loja=loja,
        preco=preco,
        cupom=cupom,
    )

    imagem = await _baixar_imagem_com_seguranca(
        audit_id=audit_id,
        event=event,
    )

    # --------------------------------------------------------
    # 8. Montagem e validação da mensagem
    # --------------------------------------------------------

    mensagem_final = montar_mensagem_final(
        texto_original=texto,
        texto_reformulado=texto_reformulado,
        preco=preco,
        cupom=cupom,
        link_afiliado=link_final,
    )

    registrar_etapa(
        audit_id,
        "MONTAGEM_MENSAGEM",
        codigo="MENSAGEM_MONTADA",
        mensagem_final=mensagem_final,
        tamanho=len(mensagem_final or ""),
    )

    _registrar_validacoes_mensagem(
        audit_id=audit_id,
        mensagem_final=mensagem_final,
        link_final=link_final,
        link_afiliado=link_afiliado,
        link_original=link_original,
        loja=loja,
        preco=preco,
    )

    # --------------------------------------------------------
    # 9. Banco, diagnóstico e fila do WhatsApp
    # --------------------------------------------------------

    _salvar_promocao_com_seguranca(
        audit_id=audit_id,
        telegram_id=telegram_id,
        canal=canal,
        texto=texto,
        link_final=link_final,
        preco=preco,
        cupom=cupom,
        loja=loja,
        imagem=imagem,
        produto_id=produto_id,
    )

    if EXIBIR_DIAGNOSTICO_TERMINAL:
        # Importações feitas somente quando o modo detalhado está habilitado.
        from dashboard.painel import mostrar_painel
        from diagnostics.diagnostic import mostrar_diagnostico

        mostrar_painel()
        mostrar_diagnostico(
            canal=canal,
            telegram_id=telegram_id,
            texto=texto,
            texto_reformulado=texto_reformulado,
            mensagem_final=mensagem_final,
            preco=preco,
            cupom=cupom,
            loja=loja,
            link_original=link_original,
            link_afiliado=link_afiliado,
            imagem=imagem,
            possui_conversao=True,
            conversao_confirmada=conversao_confirmada,
        )

    await _adicionar_na_fila_whatsapp(
        audit_id=audit_id,
        inicio_total=inicio_total,
        mensagem_final=mensagem_final,
        imagem=imagem,
        canal=canal,
        telegram_id=telegram_id,
    )

    if EXIBIR_HISTORICO_TERMINAL:
        from reports.history import mostrar_historico

        mostrar_historico()
    elif not EXIBIR_DIAGNOSTICO_TERMINAL:
        _mostrar_resumo_producao(
            canal=canal,
            telegram_id=telegram_id,
            loja=loja,
            preco=preco,
            cupom=cupom,
            link_afiliado=link_afiliado,
            imagem=imagem,
        )
