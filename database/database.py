# database/database.py

from __future__ import annotations

import hashlib
import re
import sqlite3
import unicodedata
from threading import RLock
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


conn = sqlite3.connect(
    "promocoes.db",
    check_same_thread=False,
    timeout=30,
)
conn.row_factory = sqlite3.Row
_lock_banco = RLock()


def _sem_acentos(texto: str) -> str:
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texto or "")
        if not unicodedata.combining(caractere)
    )


def normalizar_link_banco(link: str) -> str:
    link = (link or "").strip()
    if not link:
        return ""

    try:
        partes = urlsplit(link)
        esquema = (partes.scheme or "https").lower()
        host = partes.netloc.lower().removeprefix("www.")
        caminho = partes.path.rstrip("/")

        parametros_ignorados = {
            "matt_tool", "matt_word", "matt_source", "matt_campaign",
            "matt_ad_group", "matt_match_type", "matt_network",
            "matt_device", "matt_creative", "utm_source", "utm_medium",
            "utm_campaign", "utm_content", "utm_term", "tracking_id",
            "affiliate_id", "forceinapp",
        }

        query = [
            (chave, valor)
            for chave, valor in parse_qsl(partes.query, keep_blank_values=True)
            if chave.lower() not in parametros_ignorados
        ]

        return urlunsplit(
            (esquema, host, caminho, urlencode(sorted(query)), "")
        )
    except Exception:
        return link.rstrip("/")


def extrair_identificador_produto_ml(*valores: str) -> str:
    for valor in valores:
        texto = str(valor or "")
        correspondencia = re.search(
            r"(?i)\bMLB[\s\-_]?(\d{6,})\b",
            texto,
        )
        if correspondencia:
            return f"MLB{correspondencia.group(1)}"
    return ""


def _normalizar_linha(texto: str) -> str:
    texto = _sem_acentos(texto).lower()
    texto = re.sub(r"https?://\S+", " ", texto)
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def gerar_assinatura_mensagem(mensagem: str) -> str:
    """
    Assinatura exata da parte textual da promoção.

    URLs e diferenças de pontuação não alteram a assinatura.
    """
    texto = _sem_acentos(mensagem or "").lower()
    texto = re.sub(r"https?://\S+", " ", texto)
    texto = re.sub(r"\b(?:r\$)?\s*\d[\d.,]*\b", " <valor> ", texto)
    texto = re.sub(r"[^a-z0-9<>]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()

    if not texto:
        return ""

    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def gerar_chave_produto_texto(mensagem: str) -> str:
    """
    Extrai uma chave conservadora usando a linha que mais parece ser o nome
    do produto. Ela permite reconhecer o mesmo produto mesmo que o gancho,
    preço, cupom ou link tenham mudado.
    """
    linhas = [
        linha.strip()
        for linha in (mensagem or "").splitlines()
        if linha.strip()
    ]

    palavras_descartar = {
        "cupom", "use o cupom", "por r", "de r", "frete gratis",
        "oferta", "promocao", "precinho", "preco", "corre", "aproveita",
        "clique", "link", "mercado livre", "vendido por", "menor valor",
        "no pix", "parcelado", "desconto",
    }

    candidatos: list[tuple[int, str]] = []

    for linha in linhas:
        normalizada = _normalizar_linha(linha)
        if len(normalizada) < 10:
            continue
        if "http" in linha.lower():
            continue
        if re.search(r"\br\$\s*\d|\b\d+[.,]\d{2}\b", linha, re.I):
            continue
        if any(termo in normalizada for termo in palavras_descartar):
            continue

        quantidade_letras = len(re.findall(r"[a-z]", normalizada))
        quantidade_palavras = len(normalizada.split())
        if quantidade_letras < 8 or quantidade_palavras < 2:
            continue

        # Nomes de produtos normalmente são linhas descritivas de tamanho médio.
        pontuacao = quantidade_letras
        if 3 <= quantidade_palavras <= 14:
            pontuacao += 30
        if len(normalizada) > 140:
            pontuacao -= 40

        candidatos.append((pontuacao, normalizada))

    if not candidatos:
        return ""

    _, melhor = max(candidatos, key=lambda item: item[0])
    return hashlib.sha256(melhor.encode("utf-8")).hexdigest()


def _colunas_promocoes() -> set[str]:
    return {
        str(linha["name"])
        for linha in conn.execute("PRAGMA table_info(promocoes)").fetchall()
    }


def _migrar_registros_antigos() -> None:
    linhas = conn.execute(
        """
        SELECT id, link, mensagem, produto_id, assinatura_mensagem,
               chave_produto_texto
        FROM promocoes
        """
    ).fetchall()

    for linha in linhas:
        produto_id = (
            linha["produto_id"]
            or extrair_identificador_produto_ml(
                linha["link"],
                linha["mensagem"],
            )
        )
        assinatura = (
            linha["assinatura_mensagem"]
            or gerar_assinatura_mensagem(linha["mensagem"])
        )
        chave_texto = (
            linha["chave_produto_texto"]
            or gerar_chave_produto_texto(linha["mensagem"])
        )

        conn.execute(
            """
            UPDATE promocoes
            SET produto_id=?,
                assinatura_mensagem=?,
                chave_produto_texto=?
            WHERE id=?
            """,
            (produto_id, assinatura, chave_texto, linha["id"]),
        )


def _inicializar_banco() -> None:
    with _lock_banco:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS promocoes(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                canal TEXT,
                data TEXT,
                mensagem TEXT,
                link TEXT UNIQUE,
                preco TEXT,
                cupom TEXT,
                loja TEXT,
                imagem TEXT,
                produto_id TEXT,
                assinatura_mensagem TEXT,
                chave_produto_texto TEXT
            )
            """
        )

        colunas = _colunas_promocoes()
        for nome in (
            "produto_id",
            "assinatura_mensagem",
            "chave_produto_texto",
        ):
            if nome not in colunas:
                conn.execute(
                    f"ALTER TABLE promocoes ADD COLUMN {nome} TEXT"
                )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_promocoes_produto_id "
            "ON promocoes(produto_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_promocoes_assinatura "
            "ON promocoes(assinatura_mensagem)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_promocoes_chave_texto "
            "ON promocoes(chave_produto_texto)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_promocoes_telegram "
            "ON promocoes(canal, telegram_id)"
        )

        _migrar_registros_antigos()
        conn.commit()


_inicializar_banco()


def promocao_existe(
    link: str = "",
    produto_id: str = "",
    telegram_id: int | None = None,
    canal: str = "",
    mensagem: str = "",
) -> bool:
    produto_id = produto_id or extrair_identificador_produto_ml(
        link,
        mensagem,
    )
    assinatura = gerar_assinatura_mensagem(mensagem)
    chave_texto = gerar_chave_produto_texto(mensagem)
    link = (link or "").strip()
    link_normalizado = normalizar_link_banco(link)

    with _lock_banco:
        verificacoes = []

        if produto_id:
            verificacoes.append(
                ("produto_id=?", (produto_id,))
            )

        if assinatura:
            verificacoes.append(
                ("assinatura_mensagem=?", (assinatura,))
            )

        if chave_texto:
            verificacoes.append(
                ("chave_produto_texto=?", (chave_texto,))
            )

        if telegram_id is not None and canal:
            verificacoes.append(
                ("telegram_id=? AND canal=?", (telegram_id, canal))
            )

        if link:
            verificacoes.append(("link=?", (link,)))

        for condicao, parametros in verificacoes:
            encontrado = conn.execute(
                f"SELECT id FROM promocoes WHERE {condicao} LIMIT 1",
                parametros,
            ).fetchone()
            if encontrado is not None:
                return True

        if link_normalizado:
            links = conn.execute(
                """
                SELECT link FROM promocoes
                WHERE link IS NOT NULL AND TRIM(link) <> ''
                """
            ).fetchall()
            for linha in links:
                if normalizar_link_banco(linha["link"]) == link_normalizado:
                    return True

    return False


def salvar_promocao(
    telegram_id,
    canal,
    data,
    mensagem,
    link,
    preco,
    cupom,
    loja,
    imagem,
    produto_id: str = "",
):
    produto_id = produto_id or extrair_identificador_produto_ml(
        link,
        mensagem,
    )
    assinatura = gerar_assinatura_mensagem(mensagem)
    chave_texto = gerar_chave_produto_texto(mensagem)

    with _lock_banco:
        conn.execute(
            """
            INSERT INTO promocoes(
                telegram_id, canal, data, mensagem, link,
                preco, cupom, loja, imagem, produto_id,
                assinatura_mensagem, chave_produto_texto
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                telegram_id, canal, data, mensagem, link,
                preco, cupom, loja, imagem, produto_id,
                assinatura, chave_texto,
            ),
        )
        conn.commit()
