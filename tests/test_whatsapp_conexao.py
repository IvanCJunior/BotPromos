import asyncio

from playwright.async_api import async_playwright


WHATSAPP_CDP_URL = "http://127.0.0.1:9223"


async def encontrar_pagina_whatsapp(contextos):
    for contexto in contextos:
        for pagina in contexto.pages:
            if "web.whatsapp.com" in pagina.url:
                return pagina

    return None


async def verificar_whatsapp():
    playwright = await async_playwright().start()

    try:
        print()
        print("=" * 70)
        print("TESTE DE CONEXÃO COM O WHATSAPP")
        print("=" * 70)

        navegador = await playwright.chromium.connect_over_cdp(
            WHATSAPP_CDP_URL
        )

        print("Chrome conectado........ ✅ SIM")

        pagina = await encontrar_pagina_whatsapp(
            navegador.contexts
        )

        if pagina is None:
            print("WhatsApp aberto......... ❌ NÃO")
            print()
            print(
                "Abra https://web.whatsapp.com no Chrome "
                "da porta 9223."
            )
            return

        print("WhatsApp aberto......... ✅ SIM")
        print(f"Página atual............ {pagina.url}")

        await pagina.bring_to_front()

        try:
            await pagina.wait_for_load_state(
                "domcontentloaded",
                timeout=15000,
            )
        except Exception:
            pass

        # Se o QR Code estiver visível, a sessão não está conectada.
        qr_code = pagina.locator(
            'canvas[aria-label*="Scan"], '
            'canvas[aria-label*="QR"], '
            'div[data-ref]'
        )

        if await qr_code.count() > 0:
            print("WhatsApp conectado...... ❌ NÃO")
            print("Motivo.................. QR Code detectado")
            return

        # Elementos normalmente disponíveis quando o WhatsApp está logado.
        painel_conversas = pagina.locator(
            '#pane-side, '
            'div[aria-label="Lista de conversas"], '
            'div[aria-label="Chat list"]'
        )

        caixa_pesquisa = pagina.locator(
            'div[contenteditable="true"][data-tab="3"], '
            'div[contenteditable="true"][aria-label*="Pesquisar"], '
            'div[contenteditable="true"][aria-label*="Search"]'
        )

        conectado = (
            await painel_conversas.count() > 0
            or await caixa_pesquisa.count() > 0
        )

        if conectado:
            print("WhatsApp conectado...... ✅ SIM")
            print("Pronto para procurar grupo: ✅ SIM")
        else:
            print("WhatsApp conectado...... ⚠ NÃO CONFIRMADO")
            print(
                "A página foi localizada, mas os elementos "
                "da lista de conversas não foram encontrados."
            )

        print()
        print("Nenhuma mensagem foi enviada.")

    except Exception as erro:
        print()
        print("Chrome conectado........ ❌ NÃO")
        print(f"Erro.................... {erro}")
        print()
        print(
            "Confirme se o Chrome do WhatsApp foi aberto "
            "com --remote-debugging-port=9223."
        )

    finally:
        await playwright.stop()

        print()
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(verificar_whatsapp())