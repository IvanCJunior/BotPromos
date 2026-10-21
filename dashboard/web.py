import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
BANCO = BASE_DIR / "promocoes.db"
PASTA_SITE = Path(__file__).resolve().parent / "static"


def abrir_banco():
    conexao = sqlite3.connect(BANCO)
    conexao.row_factory = sqlite3.Row
    return conexao


def buscar_resumo():
    conexao = abrir_banco()

    total = conexao.execute(
        "SELECT COUNT(*) FROM promocoes"
    ).fetchone()[0]

    cupons = conexao.execute(
        "SELECT COUNT(*) FROM promocoes "
        "WHERE cupom IS NOT NULL AND TRIM(cupom) <> ''"
    ).fetchone()[0]

    lojas = conexao.execute(
        "SELECT DISTINCT loja FROM promocoes "
        "WHERE loja IS NOT NULL AND TRIM(loja) <> '' "
        "ORDER BY loja"
    ).fetchall()

    conexao.close()

    return {
        "total": total,
        "cupons": cupons,
        "lojas": len(lojas),
        "opcoes_lojas": [item["loja"] for item in lojas],
    }


def buscar_promocoes(busca="", loja="", cupom="todos",
                     data_inicio="", data_fim=""):
    conexao = abrir_banco()

    consulta = """
        SELECT id, canal, data, mensagem, link, preco, cupom, loja
        FROM promocoes
        WHERE 1 = 1
    """
    parametros = []

    if busca:
        termo = f"%{busca}%"
        consulta += """
            AND (
                mensagem LIKE ?
                OR canal LIKE ?
                OR loja LIKE ?
                OR cupom LIKE ?
            )
        """
        parametros.extend([termo, termo, termo, termo])

    if loja:
        consulta += " AND loja = ?"
        parametros.append(loja)

    if cupom == "com":
        consulta += " AND cupom IS NOT NULL AND TRIM(cupom) <> ''"
    elif cupom == "sem":
        consulta += " AND (cupom IS NULL OR TRIM(cupom) = '')"

    data_sql = (
        "substr(data, 7, 4) || '-' || "
        "substr(data, 4, 2) || '-' || "
        "substr(data, 1, 2)"
    )

    if data_inicio:
        consulta += f" AND {data_sql} >= ?"
        parametros.append(data_inicio)

    if data_fim:
        consulta += f" AND {data_sql} <= ?"
        parametros.append(data_fim)

    consulta += " ORDER BY id DESC LIMIT 200"

    resultados = conexao.execute(consulta, parametros).fetchall()
    conexao.close()

    return [dict(item) for item in resultados]


class Servidor(BaseHTTPRequestHandler):
    def responder_json(self, dados, status=200):
        conteudo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(conteudo)))
        self.end_headers()
        self.wfile.write(conteudo)

    def do_GET(self):
        pagina = urlparse(self.path)

        if pagina.path == "/api/resumo":
            self.responder_json(buscar_resumo())
            return

        if pagina.path == "/api/promocoes":
            filtros = parse_qs(pagina.query)
            busca = filtros.get("busca", [""])[0].strip()
            loja = filtros.get("loja", [""])[0].strip()
            cupom = filtros.get("cupom", ["todos"])[0].strip()
            data_inicio = filtros.get("data_inicio", [""])[0].strip()
            data_fim = filtros.get("data_fim", [""])[0].strip()

            self.responder_json({
                "items": buscar_promocoes(
                    busca, loja, cupom, data_inicio, data_fim
                )
            })
            return

        if pagina.path == "/":
            arquivo = PASTA_SITE / "index.html"
        else:
            arquivo = PASTA_SITE / pagina.path.lstrip("/")

        if not arquivo.exists() or not arquivo.is_file():
            self.responder_json({"erro": "Página não encontrada"}, 404)
            return

        conteudo = arquivo.read_bytes()
        tipo = (
            "text/html; charset=utf-8"
            if arquivo.suffix == ".html"
            else "text/plain; charset=utf-8"
        )

        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(conteudo)))
        self.end_headers()
        self.wfile.write(conteudo)

    def log_message(self, formato, *args):
        return


def iniciar():
    servidor = ThreadingHTTPServer(("127.0.0.1", 8000), Servidor)
    print("Dashboard BotPromos: http://127.0.0.1:8000")
    print("Pressione CTRL+C para encerrar.")

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    iniciar()
