import asyncio

from playwright.async_api import async_playwright


async def main() -> None:
    async with async_playwright() as playwright:
        print("Conectando ao Chrome já aberto...")

        browser = await playwright.chromium.connect_over_cdp(
            "http://127.0.0.1:9222"
        )

        if not browser.contexts:
            raise RuntimeError("Nenhum contexto do Chrome foi encontrado.")

        contexto = browser.contexts[0]

        pagina = (
            contexto.pages[0]
            if contexto.pages
            else await contexto.new_page()
        )

        print("Página atual:", pagina.url)

        await pagina.goto(
            "https://www.mercadolivre.com.br/",
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        print("Mercado Livre aberto:", pagina.url)

        input("Pressione ENTER para encerrar o teste...")


if __name__ == "__main__":
    asyncio.run(main())