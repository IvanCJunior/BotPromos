from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)


CDP_URL = "http://127.0.0.1:9222"


class BrowserManager:
    def __init__(self) -> None:
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.contexto: BrowserContext | None = None

    async def conectar(self) -> BrowserContext:
        if self.contexto is not None:
            return self.contexto

        self.playwright = await async_playwright().start()

        try:
            self.browser = await self.playwright.chromium.connect_over_cdp(
                CDP_URL
            )
        except Exception:
            await self.playwright.stop()
            self.playwright = None

            raise RuntimeError(
                "Não foi possível conectar ao Chrome na porta 9222. "
                "Abra primeiro o Chrome permanente."
            )

        if not self.browser.contexts:
            await self.playwright.stop()

            self.playwright = None
            self.browser = None

            raise RuntimeError(
                "O Chrome foi encontrado, mas nenhum contexto está disponível."
            )

        self.contexto = self.browser.contexts[0]

        print("BrowserManager conectado ao Chrome permanente.")

        return self.contexto

    async def nova_pagina(self) -> Page:
        contexto = await self.conectar()
        return await contexto.new_page()

    async def localizar_pagina(self, trecho_url: str) -> Page | None:
        contexto = await self.conectar()

        for pagina in contexto.pages:
            if trecho_url in pagina.url:
                return pagina

        return None

    async def obter_ou_abrir_pagina(
        self,
        trecho_url: str,
        url: str,
    ) -> Page:
        pagina = await self.localizar_pagina(trecho_url)

        if pagina is not None:
            await pagina.bring_to_front()
            return pagina

        pagina = await self.nova_pagina()

        await pagina.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        return pagina

    async def desconectar(self) -> None:
        """
        Encerra somente a conexão do Playwright.
        Não fecha o Chrome permanente.
        """

        self.contexto = None
        self.browser = None

        if self.playwright is not None:
            await self.playwright.stop()
            self.playwright = None


browser_manager = BrowserManager()