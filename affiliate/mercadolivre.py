from services.mercadolivre_service import MercadoLivreService


mercadolivre_service = MercadoLivreService()


async def converter_mercadolivre(link: str, audit_id: str = "") -> str:
    """Gera o link de afiliado e preserva o diagnóstico detalhado da falha."""
    if not link:
        return ""

    try:
        return (
            await mercadolivre_service.gerar_link_afiliado(link, audit_id=audit_id)
            or ""
        ).strip()
    except Exception as erro:
        print(f"Erro no conversor do Mercado Livre: {erro}")
        return ""
