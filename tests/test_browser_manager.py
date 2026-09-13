import asyncio

from browser.browser_manager import browser_manager


async def main():
    contexto = await browser_manager.conectar()

    print(f"Conectado! Existem {len(contexto.pages)} abas abertas.")

    pagina = await browser_manager.nova_pagina()

    await pagina.goto(
        "https://www.google.com",
        wait_until="domcontentloaded"
    )

    print("Google aberto com sucesso!")

    input("ENTER para finalizar...")

    await pagina.close()

    await browser_manager.desconectar()


if __name__ == "__main__":
    asyncio.run(main())