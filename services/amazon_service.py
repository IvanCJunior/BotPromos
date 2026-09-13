from playwright.async_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from browser.browser_manager import browser_manager


class AmazonService:
    async def gerar_link_curto(self, link_produto: str) -> str:
        if not link_produto:
            return ""

        pagina: Page = await browser_manager.nova_pagina()

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