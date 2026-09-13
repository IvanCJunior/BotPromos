from dataclasses import dataclass


@dataclass
class Promocao:

    telegram_id: int

    canal: str

    mensagem: str

    link: str

    preco: str

    cupom: str

    loja: str

    imagem: str
