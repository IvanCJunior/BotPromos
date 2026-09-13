from playwright.sync_api import sync_playwright


with sync_playwright() as p:

    browser = p.chromium.launch_persistent_context(

        user_data_dir="playwright_tools/profile_ml",

        headless=False,

        viewport={"width": 1600, "height": 900}

    )

    page = browser.new_page()

    page.goto("https://www.mercadolivre.com.br/")

    print()
    print("=" * 60)
    print("FAÇA LOGIN NO MERCADO LIVRE")
    print("=" * 60)
    print()
    print("Depois pressione ENTER")

    input()

    browser.close()

print()
print("Perfil salvo com sucesso.")