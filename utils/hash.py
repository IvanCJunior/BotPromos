import hashlib


def gerar_hash(texto):

    texto = texto.lower()

    texto = texto.strip()

    return hashlib.sha256(

        texto.encode()

    ).hexdigest()