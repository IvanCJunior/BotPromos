def preparar_envio_whatsapp(
    mensagem_final: str,
    imagem: str | None = None,
) -> dict:
    """
    Prepara os dados que futuramente serão enviados ao WhatsApp.

    Nesta etapa, nada é enviado.
    A função apenas organiza os dados e retorna um dicionário.
    """

    mensagem = (mensagem_final or "").strip()

    if not mensagem:
        raise ValueError(
            "A mensagem final está vazia."
        )

    imagem_valida = None

    if imagem:
        imagem_texto = str(imagem).strip()

        if imagem_texto:
            imagem_valida = imagem_texto

    return {
        "mensagem": mensagem,
        "imagem": imagem_valida,
    }


def simular_envio_whatsapp(
    mensagem_final: str,
    imagem: str | None = None,
) -> None:
    """
    Exibe no terminal o conteúdo que futuramente
    será enviado ao WhatsApp.

    Nenhuma mensagem real é enviada.
    """

    dados = preparar_envio_whatsapp(
        mensagem_final=mensagem_final,
        imagem=imagem,
    )

    print()
    print("=" * 70)
    print("SIMULAÇÃO DE ENVIO AO WHATSAPP")
    print("=" * 70)
    print()

    print(dados["mensagem"])

    print()
    print("-" * 70)

    if dados["imagem"]:
        print("Imagem.............. ✅ PRONTA PARA ENVIO")
        print(f"Arquivo............. {dados['imagem']}")
    else:
        print("Imagem.............. ❌ NÃO DISPONÍVEL")

    print()
    print("Status.............. 🧪 SOMENTE SIMULAÇÃO")
    print("Nenhuma mensagem foi enviada.")
    print()
    print("=" * 70)