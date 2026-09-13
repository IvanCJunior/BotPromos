from datetime import datetime


def mostrar_diagnostico(
    canal,
    telegram_id,
    texto,
    texto_reformulado,
    mensagem_final,
    preco,
    cupom,
    loja,
    link_original,
    link_afiliado,
    imagem,
    possui_conversao,
    conversao_confirmada,
):
    data_atual = datetime.now().strftime(
        "%d/%m/%Y %H:%M:%S"
    )

    print("=" * 70)
    print("DIAGNÓSTICO DA PROMOÇÃO")
    print("=" * 70)
    print()

    print(
        f"Canal............... "
        f"{'✅' if canal else '❌'} "
        f"{canal or 'Não identificado'}"
    )
    print(f"ID.................. {telegram_id}")
    print(f"Data e horário...... {data_atual}")

    print()
    print("-" * 70)
    print("CONTEÚDO CAPTURADO")
    print("-" * 70)
    print()

    if texto:
        print("Texto capturado..... ✅ SIM")
        print()
        print("Texto original:")
        print(texto)
    else:
        print("Texto capturado..... ❌ NÃO")

    print()
    print("-" * 70)
    print("TEXTO CRIADO PELA IA")
    print("-" * 70)
    print()

    if texto_reformulado:
        print("Reformulação........ ✅ REALIZADA")
        print()
        print(texto_reformulado)
    else:
        print("Reformulação........ ⚠ NÃO REALIZADA")
        print("O bot usará o texto original na mensagem final.")

    print()

    if preco:
        print(f"Preço capturado..... ✅ SIM — {preco}")
    else:
        print("Preço capturado..... ❌ NÃO")

    if cupom:
        print(f"Cupom capturado..... ✅ SIM — {cupom}")
    else:
        print("Cupom capturado..... ❌ NÃO")

    if loja:
        print(f"Loja identificada... ✅ SIM — {loja}")
    else:
        print("Loja identificada... ❌ NÃO")

    print()
    print("-" * 70)
    print("CONFERÊNCIA DOS LINKS")
    print("-" * 70)
    print()

    if link_original:
        print("Link recebido........ ✅")
        print(link_original)
    else:
        print("Link recebido........ ❌ NÃO ENCONTRADO")

    print()

    if possui_conversao:
        if link_afiliado:
            print("Meu link convertido.. ✅")
            print(link_afiliado)
        else:
            print("Meu link convertido.. ❌ NÃO GERADO")

        print()

        if conversao_confirmada:
            print(
                "Conversão............ ✅ "
                "LINK CONVERTIDO COM SUCESSO"
            )
        else:
            print(
                "Conversão............ ⚠ "
                "NÃO FOI POSSÍVEL CONFIRMAR A CONVERSÃO"
            )
    else:
        print("Meu link convertido.. — NÃO CONFIGURADO")
        print("Conversão............ — NÃO REALIZADA")

    print()
    print("-" * 70)
    print("IMAGEM")
    print("-" * 70)
    print()

    if imagem:
        print("Download da imagem... ✅ REALIZADO")
        print(f"Arquivo.............. {imagem}")
    else:
        print("Download da imagem... ❌ NÃO REALIZADO")

    print()
    print("-" * 70)
    print("MENSAGEM COMPLETA PARA O WHATSAPP")
    print("-" * 70)
    print()

    if mensagem_final:
        print(mensagem_final)
    else:
        print("⚠ Não foi possível montar a mensagem final.")

    print()
    print("=" * 70)
