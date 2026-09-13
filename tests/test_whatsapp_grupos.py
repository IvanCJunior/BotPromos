# tests/test_whatsapp_grupos.py

import asyncio

from whatsapp.config import GRUPOS_WHATSAPP
from whatsapp.service import WhatsAppService


MENSAGEM_TESTE = "mensagem automática teste 1"


async def main() -> None:
    print("=" * 70)
    print("TESTE DE ENVIO DE TEXTO NO WHATSAPP")
    print("=" * 70)

    service = WhatsAppService()

    try:
        await service.conectar()

        print("Chrome conectado........ ✅ SIM")
        print("WhatsApp aberto......... ✅ SIM")
        print("WhatsApp conectado...... ✅ SIM")

        print()
        print("ENVIO DA MENSAGEM")
        print("-" * 70)

        for indice, nome_grupo in enumerate(
            GRUPOS_WHATSAPP,
            start=1,
        ):
            try:
                await service.abrir_grupo(nome_grupo)

                caixa_mensagem = await service.obter_caixa_mensagem(
                    nome_grupo
                )

                await caixa_mensagem.click()
                await caixa_mensagem.fill(MENSAGEM_TESTE)

                await service.pagina.keyboard.press("Enter")

                print(
                    f"{indice}. {nome_grupo} — ✅ MENSAGEM ENVIADA"
                )

            except Exception as erro:
                print(
                    f"{indice}. {nome_grupo} — ⚠ ERRO: {erro}"
                )

        print()
        print("-" * 70)
        print(f'Mensagem usada: "{MENSAGEM_TESTE}"')

    except Exception as erro:
        print(f"Erro de conexão.......... ❌ {erro}")

    finally:
        await service.fechar()

    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())