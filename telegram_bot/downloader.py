import os

os.makedirs("downloads", exist_ok=True)


async def baixar_imagem(event):

    if event.photo:

        caminho = await event.download_media(
            "downloads/"
        )

        return caminho

    return ""