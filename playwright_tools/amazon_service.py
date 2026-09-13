from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)


CDP_URL = "http://127.0.0.1:9222"


class AmazonService:
    def __init__(self) -> None:
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.contexto: BrowserContext | None = None

    async def conectar(self) -> None:
        if self.browser is not None:
            return

        self.playwright = await async_playwright().start()

        self.browser = await self.playwright.chromium.connect_over_cdp(
            CDP_URL
        )

        if not self.browser.contexts:
            raise RuntimeError(
                "Nenhum contexto foi encontrado no Chrome permanente."
            )

        self.contexto = self.browser.contexts[0]

        print("AmazonService conectado ao Chrome permanente.")

    async def gerar_link_curto(self, link_produto: str) -> str:
        if not link_produto:
            return ""

        await self.conectar()

        if self.contexto is None:
            return link_produto

        pagina: Page = await self.contexto.new_page()

        try:
            await pagina.goto(
                link_produto,
                wait_until="domcontentloaded",
                timeout=60_000,
            )

            await pagina.get_by_role(
                "button",
                name="Obter link",
            ).click(timeout=30_000)

            await pagina.get_by_role(
                "button",
                name="Copiar link de associado",
            ).click(timeout=30_000)

            await pagina.wait_for_timeout(1_000)

            link_curto = await pagina.evaluate(
                "navigator.clipboard.readText()"
            )

            if link_curto:
                print("Link Amazon gerado:", link_curto)
                return link_curto

            return link_produto

        except PlaywrightTimeoutError as erro:
            print("Tempo esgotado na Amazon:", erro)
            return link_produto

        except Exception as erro:
            print("Erro ao gerar link Amazon:", erro)
            return link_produto

        finally:
            await pagina.close()

    async def desconectar(self) -> None:
        """
        Desconecta o Playwright sem fechar o Chrome permanente.
        """

        self.contexto = None
        self.browser = None

        if self.playwright is not None:
            await self.playwright.stop()
            self.playwright = None