from utils.message_builder import montar_mensagem_final


def testar_mensagem():
    mensagem = montar_mensagem_final(
        texto_original=(
            "Headset gamer com som potente "
            "por R$ 299."
        ),
        texto_reformulado=(
            "🎧 Um áudio melhor pode mudar "
            "completamente a sua partida."
        ),
        preco="299",
        cupom="SOM10",
        link_afiliado="https://exemplo.com/link-afiliado",
    )

    print()
    print("=" * 70)
    print("TESTE DA MENSAGEM FINAL")
    print("=" * 70)
    print()
    print(mensagem)
    print()
    print("=" * 70)


if __name__ == "__main__":
    testar_mensagem()