import asyncio

from browser.browser_manager import browser_manager
from services.mercadolivre_service import (
    MercadoLivreService,
)


LINK_PRODUTO = "https://meli.la/1WEdtwq"


async def main() -> None:
    servico = MercadoLivreService()

    try:
        resultado = await servico.gerar_link_afiliado(
            LINK_PRODUTO
        )

        print()
        print("=" * 70)
        print("RESULTADO DO TESTE DO MERCADO LIVRE")
        print("=" * 70)
        print("Link recebido :", LINK_PRODUTO)
        print("Seu novo link :", resultado)
        print("=" * 70)

        input(
            "\nPressione ENTER para finalizar o teste..."
        )

    finally:
        await browser_manager.desconectar()


if __name__ == "__main__":
    asyncio.run(main())