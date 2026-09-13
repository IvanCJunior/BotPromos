PALAVRAS_PROIBIDAS = [

    "bom dia",

    "boa noite",

    "boa tarde",

    "live",

    "youtube",

    "vídeo"

]


def e_promocao(texto):

    texto = texto.lower()

    for palavra in PALAVRAS_PROIBIDAS:

        if palavra in texto:

            return False

    return True