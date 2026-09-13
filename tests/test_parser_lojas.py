import sys
from pathlib import Path

# Adiciona a raiz do projeto ao PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram_bot.parser import (
    descobrir_loja,
    extrair_cupom,
    extrair_links,
    extrair_preco,
)


CASOS = [
    {
        "nome": "Mercado Livre: preço antigo e preço promocional",
        "texto": """
Produto em promoção!
De R$ 159 por R$ 59 no Pix
Cupom: VARDOMELI
https://produto.mercadolivre.com.br/MLB-123456789
""",
        "preco_esperado": "R$ 59",
        "cupom_esperado": "VARDOMELI",
        "loja_esperada": "Mercado Livre",
    },
    {
        "nome": "Amazon: valor decimal sem R$",
        "texto": """
Oferta por 132,39 em até quatro vezes
https://www.amazon.com.br/dp/ABC123
""",
        "preco_esperado": "R$ 132,39",
        "cupom_esperado": "",
        "loja_esperada": "Amazon",
    },
    {
        "nome": "Cupom inválido",
        "texto": """
Cupom de 15% OFF
Produto por R$ 89,90
https://mercadolivre.com.br/produto
""",
        "preco_esperado": "R$ 89,90",
        "cupom_esperado": "",
        "loja_esperada": "Mercado Livre",
    },
    {
        "nome": "Shopee deve ser ignorada",
        "texto": """
Produto por R$ 49,90
https://shopee.com.br/produto
""",
        "preco_esperado": "R$ 49,90",
        "cupom_esperado": "",
        "loja_esperada": "Desconhecida",
    },
]


def testar_caso(caso: dict) -> bool:
    texto = caso["texto"]

    links = extrair_links(texto)
    link = links[0] if links else ""

    preco = extrair_preco(texto)
    cupom = extrair_cupom(texto)
    loja = descobrir_loja(link)

    correto = (
        preco == caso["preco_esperado"]
        and cupom == caso["cupom_esperado"]
        and loja == caso["loja_esperada"]
    )

    print("=" * 70)
    print(caso["nome"])
    print("-" * 70)
    print(f"Preço esperado...... {caso['preco_esperado'] or 'Nenhum'}")
    print(f"Preço obtido........ {preco or 'Nenhum'}")
    print(f"Cupom esperado...... {caso['cupom_esperado'] or 'Nenhum'}")
    print(f"Cupom obtido........ {cupom or 'Nenhum'}")
    print(f"Loja esperada....... {caso['loja_esperada']}")
    print(f"Loja obtida......... {loja}")
    print(f"Resultado........... {'✅ CORRETO' if correto else '❌ ERRO'}")

    return correto


def main() -> None:
    resultados = [testar_caso(caso) for caso in CASOS]

    print()
    print("=" * 70)
    print("RESULTADO FINAL")
    print("=" * 70)
    print(f"Testes corretos..... {sum(resultados)} de {len(resultados)}")

    if all(resultados):
        print("Parser............... ✅ APROVADO")
    else:
        print("Parser............... ❌ NECESSITA CORREÇÃO")


if __name__ == "__main__":
    main()