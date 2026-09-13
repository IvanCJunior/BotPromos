from __future__ import annotations

from time import perf_counter

from affiliate.mercadolivre import converter_mercadolivre
from diagnostics.audit import registrar_erro, registrar_etapa


async def gerar_link_afiliado(
    loja: str,
    link: str,
    audit_id: str = "",
) -> str:
    """Gera links somente para as lojas atualmente habilitadas."""

    inicio = perf_counter()
    loja = (loja or "").strip()
    link = (link or "").strip()

    if not link:
        if audit_id:
            registrar_etapa(
                audit_id,
                "GERENCIADOR_AFILIADO",
                status="ERRO",
                codigo="LINK_RECEBIDO_VAZIO",
                loja=loja,
            )
        return ""

    if audit_id:
        registrar_etapa(
            audit_id,
            "GERENCIADOR_AFILIADO",
            codigo="CONVERSOR_SELECIONADO",
            loja=loja,
            link_recebido=link,
        )

    try:
        if loja == "Mercado Livre":
            resultado = await converter_mercadolivre(link, audit_id=audit_id)
        else:
            if audit_id:
                registrar_etapa(
                    audit_id,
                    "GERENCIADOR_AFILIADO",
                    status="IGNORADA",
                    codigo="LOJA_NAO_HABILITADA",
                    loja=loja,
                    duracao_ms=(perf_counter() - inicio) * 1000,
                )
            return ""

        if audit_id:
            registrar_etapa(
                audit_id,
                "GERENCIADOR_AFILIADO",
                status="OK" if resultado else "ERRO",
                codigo=(
                    "CONVERSOR_RETORNOU_LINK"
                    if resultado
                    else "CONVERSOR_RETORNOU_VAZIO"
                ),
                loja=loja,
                link_convertido=resultado,
                duracao_ms=(perf_counter() - inicio) * 1000,
            )
        return resultado or ""

    except Exception as erro:
        if audit_id:
            registrar_erro(
                audit_id,
                "GERENCIADOR_AFILIADO",
                erro,
                codigo="FALHA_NO_CONVERSOR",
                loja=loja,
                link_recebido=link,
                duracao_ms=(perf_counter() - inicio) * 1000,
            )
        raise
