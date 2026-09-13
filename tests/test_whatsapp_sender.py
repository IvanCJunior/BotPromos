from whatsapp.sender import simular_envio_whatsapp


def testar_simulacao():
    mensagem = (
        "🎧 Um áudio melhor pode mudar completamente a sua partida.\n\n"
        "💰 R$ 299\n\n"
        "🎟 Cupom: SOM10\n\n"
        "🔗 https://exemplo.com/link-afiliado"
    )

    simular_envio_whatsapp(
        mensagem_final=mensagem,
        imagem=None,
    )


if __name__ == "__main__":
    testar_simulacao()