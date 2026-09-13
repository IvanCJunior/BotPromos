from services.amazon_service import AmazonService


amazon_service = AmazonService()


async def converter_amazon(link: str) -> str:
    try:
        novo_link = await amazon_service.gerar_link_curto(link)

        if novo_link:
            return novo_link

    except Exception as erro:
        print(f"Erro Amazon: {erro}")

    return link