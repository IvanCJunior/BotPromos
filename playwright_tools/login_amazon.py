from playwright.sync_api import sync_playwright
import os


def salvar_login():

    os.makedirs("playwright_tools/session", exist_ok=True)

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False
        )

        context = browser.new_context()

        page = context.new_page()

        print()
        print("=" * 60)
        print("ABRINDO AMAZON")
        print("=" * 60)
        print()
        print("1 - Faça login normalmente")
        print("2 - Verifique se a SiteStripe aparece")
        print("3 - NÃO FECHE O NAVEGADOR")
        print("4 - Quando terminar, volte ao terminal")
        print()

        page.goto("https://www.amazon.com.br", wait_until="networkidle")

        input("Pressione ENTER quando estiver totalmente logado...")

        context.storage_state(
            path="playwright_tools/session/amazon.json"
        )

        print()
        print("✅ Login salvo com sucesso!")

        browser.close()


if __name__ == "__main__":
    salvar_login()