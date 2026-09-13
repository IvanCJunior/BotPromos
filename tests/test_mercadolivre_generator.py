import asyncio
import re

from playwright.async_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)


CHROME_EXECUTABLE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_USER_DATA = r"C:\Users\ivan1\AppData\Local\Google\Chrome\User Data"
CHROME_PROFILE = "Default"

# Cole aqui a URL exata da página do Gerador de Links.
GERADOR_URL = "https://www.mercadolivre.com.br/afiliados/linkbuilder#hub"

# Use um link real de produto para o teste.
PRODUTO_URL = "https://www.mercadolivre.com.br/creatina-monohidratada-em-pote-150g-100-pura-dark-lab/p/MLB19506693#polycard_client=recommendations_home_top-sales-highlights-recommendations&reco_backend=top_sales_highlights&wid=MLB3788290343&reco_client=home_top-sales-highlights-recommendations&reco_item_pos=0&reco_backend_type=function&reco_id=c7c7630b-760f-4990-a438-e5d52308e2fe&sid=recos&c_id=/home/top-sales-first-recommendations/element&c_uid=800f9c41-437a-46c4-8e45-e0c54462e415"


async def localizar_campo_url(page: Page):
    """Tenta localizar o campo do link usando textos comuns da interface."""
    candidatos = [
        page.get_by_placeholder(re.compile(r"insira.*url", re.IGNORECASE)),
        page.get_by_placeholder(re.compile(r"cole.*link", re.IGNORECASE)),
        page.get_by_role(
            "textbox",
            name=re.compile(r"url|link|produto", re.IGNORECASE),
        ),
        page.locator("textarea").first,
        page.locator("input[type='url']").first,
    ]

    for campo in candidatos:
        try:
            if await campo.count() and await campo.first.is_visible():
                return campo.first
        except Exception:
            continue

    raise RuntimeError("Não encontrei o campo para inserir a URL.")


async def localizar_botao_gerar(page: Page):
    candidatos = [
        page.get_by_role(
            "button",
            name=re.compile(r"^gerar|gerar link", re.IGNORECASE),
        ),
        page.locator("button").filter(
            has_text=re.compile(r"gerar", re.IGNORECASE)
        ),
    ]

    for botao in candidatos:
        try:
            if await botao.count() and await botao.first.is_visible():
                return botao.first
        except Exception:
            continue

    raise RuntimeError("Não encontrei o botão Gerar.")


async def abrir_chrome() -> BrowserContext:
    playwright = await async_playwright().start()

    try:
        contexto = await playwright.chromium.launch_persistent_context(
            user_data_dir=CHROME_USER_DATA,
            executable_path=CHROME_EXECUTABLE,
            headless=False,
            viewport={"width": 1500, "height": 900},
            args=[f"--profile-directory={CHROME_PROFILE}"],
        )
    except Exception:
        await playwright.stop()
        raise

    # Guarda a instância para poder encerrá-la no final.
    contexto._botpromos_playwright = playwright  # type: ignore[attr-defined]
    return contexto


async def main() -> None:
    if GERADOR_URL.startswith("COLE_"):
        raise ValueError("Preencha GERADOR_URL no início do arquivo.")

    if PRODUTO_URL.startswith("COLE_"):
        raise ValueError("Preencha PRODUTO_URL no início do arquivo.")

    contexto = await abrir_chrome()
    pagina = contexto.pages[0] if contexto.pages else await contexto.new_page()

    try:
        print("Abrindo o gerador do Mercado Livre...")

        await pagina.goto(
            GERADOR_URL,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        await pagina.wait_for_timeout(3_000)

        print("Página aberta em:", pagina.url)

        campo = await localizar_campo_url(pagina)
        await campo.fill(PRODUTO_URL)

        print("Link do produto inserido.")

        botao = await localizar_botao_gerar(pagina)
        await botao.click()

        print("Botão Gerar acionado.")
        print("Aguardando o resultado...")

        await pagina.wait_for_timeout(5_000)

        # Salva evidências para conseguirmos ajustar o seletor do resultado.
        await pagina.screenshot(
            path="tests/resultado_mercadolivre.png",
            full_page=True,
        )

        conteudo = await pagina.locator("body").inner_text()

        print("\n" + "=" * 60)
        print("TEXTO DA PÁGINA APÓS GERAR")
        print("=" * 60)
        print(conteudo[-4_000:])
        print("=" * 60)

        print(
            "\nCaptura salva em: "
            "tests/resultado_mercadolivre.png"
        )

        input("\nPressione ENTER para fechar o Chrome...")

    except PlaywrightTimeoutError as erro:
        print("A página demorou demais para responder:", erro)

    except Exception as erro:
        print("Falha no teste:", erro)

        await pagina.screenshot(
            path="tests/erro_mercadolivre.png",
            full_page=True,
        )

        print("Captura do erro salva em tests/erro_mercadolivre.png")

        input("\nPressione ENTER para fechar o Chrome...")

    finally:
        await contexto.close()

        playwright = getattr(
            contexto,
            "_botpromos_playwright",
            None,
        )

        if playwright is not None:
            await playwright.stop()


if __name__ == "__main__":
    asyncio.run(main())