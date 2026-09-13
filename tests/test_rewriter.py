import asyncio
import os
import sys


PASTA_PROJETO = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

if PASTA_PROJETO not in sys.path:
    sys.path.insert(
        0,
        PASTA_PROJETO,
    )


from ai.rewriter import reformular_promocao


async def testar() -> None:
    texto_original = """
JOGUEI FORA MEU FERRO DE PASSAR DEPOIS QUE COMPREI INSIDER

Tech Daily T-Shirt Insider (7 cores)

De R$ 159 por R$ 59 no Pix
Use o Cupom: CUPOMPRA

https://meli.la/link-de-outra-pessoa
""".strip()

    texto_reformulado = await reformular_promocao(
        texto_original=texto_original,
        loja="Mercado Livre",
        preco="R$ 59",
        cupom="CUPOMPRA",
    )

    print()
    print("=" * 70)
    print("TEXTO ORIGINAL")
    print("=" * 70)
    print()
    print(texto_original)

    print()
    print("=" * 70)
    print("TEXTO REFORMULADO")
    print("=" * 70)
    print()

    if texto_reformulado:
        print(texto_reformulado)
    else:
        print(
            "A IA não produziu um texto válido."
        )

    print()
    print("=" * 70)
    print("VERIFICAÇÕES")
    print("=" * 70)
    print()

    if not texto_reformulado:
        print("❌ Nenhum texto foi gerado.")
        return

    if (
        "http://" in texto_reformulado.lower()
        or "https://" in texto_reformulado.lower()
    ):
        print("❌ A resposta contém um link.")
    else:
        print("✅ A resposta não contém links.")

    linhas = [
        linha
        for linha in texto_reformulado.splitlines()
        if linha.strip()
    ]

    print(
        f"{'✅' if len(linhas) <= 3 else '❌'} "
        f"Quantidade de linhas: {len(linhas)}"
    )

    print(
        f"{'✅' if len(texto_reformulado) <= 220 else '❌'} "
        f"Quantidade de caracteres: "
        f"{len(texto_reformulado)}"
    )


if __name__ == "__main__":
    asyncio.run(testar())