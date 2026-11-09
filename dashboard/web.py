import json
import sqlite3
import secrets
import time
from http.cookies import SimpleCookie
from threading import RLock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dashboard import auth_store

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
                     data_inicio="", data_fim="",
                     preco_min="", preco_max=""):
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

    # Converte preços brasileiros em números para permitir comparações.
    # Ex.: "R$ 1.234,56" passa a ser 1234.56.
    preco_sql = (
        "CAST(REPLACE(REPLACE(REPLACE(REPLACE("
        "preco, 'R$', ''), '.', ''), ',', '.'), ' ', '') AS REAL)"
    )

    if preco_min:
        consulta += f" AND {preco_sql} >= ?"
        parametros.append(float(preco_min))

    if preco_max:
        consulta += f" AND {preco_sql} <= ?"
        parametros.append(float(preco_max))

    consulta += " ORDER BY id DESC LIMIT 200"

    resultados = conexao.execute(consulta, parametros).fetchall()
    conexao.close()

    return [dict(item) for item in resultados]


def buscar_promocao_detalhe(promocao_id):
    conexao = abrir_banco()
    try:
        item = conexao.execute(
            "SELECT * FROM promocoes WHERE id = ?",
            (promocao_id,)
        ).fetchone()
        return dict(item) if item else None
    finally:
        conexao.close()


# Sessões locais: identificadores aleatórios mantidos apenas em memória.
_SESSOES = {}
_SESSOES_LOCK = RLock()
_TENTATIVAS_LOGIN = {}
_TENTATIVAS_LOCK = RLock()
_TEMPO_SESSAO = 30 * 60


def _cookie_valor(cabecalho, nome):
    cookie = SimpleCookie()
    try:
        cookie.load(cabecalho or "")
        return cookie[nome].value if nome in cookie else ""
    except Exception:
        return ""


class Servidor(BaseHTTPRequestHandler):
    def _sessao(self):
        token = _cookie_valor(self.headers.get("Cookie"), "botpromos_session")
        agora = time.time()
        with _SESSOES_LOCK:
            sessao = _SESSOES.get(token)
            if not sessao:
                return None, ""
            if sessao["expira"] < agora:
                _SESSOES.pop(token, None)
                return None, ""
            sessao["expira"] = agora + _TEMPO_SESSAO
            return sessao, token

    def _usuario(self):
        sessao, _ = self._sessao()
        return (sessao.get("usuario") if sessao else None), sessao

    def _json_body(self):
        try:
            tamanho = int(self.headers.get("Content-Length", "0"))
            if tamanho > 64 * 1024:
                raise ValueError("Requisição muito grande.")
            bruto = self.rfile.read(tamanho) if tamanho else b"{}"
            dados = json.loads(bruto.decode("utf-8"))
            return dados if isinstance(dados, dict) else {}
        except Exception:
            raise ValueError("Corpo JSON inválido.")

    def _csrf_valido(self, sessao):
        return bool(sessao and secrets.compare_digest(
            str(self.headers.get("X-CSRF-Token", "")), str(sessao.get("csrf", ""))
        ))

    def responder_json(self, dados, status=200, headers=None):
        conteudo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(conteudo)))
        self.send_header("Cache-Control", "no-store")
        for chave, valor in (headers or {}).items():
            self.send_header(chave, valor)
        self.end_headers()
        self.wfile.write(conteudo)

    def _servir_arquivo(self, arquivo, tipo=None):
        if not arquivo.exists() or not arquivo.is_file():
            self.responder_json({"erro": "Página não encontrada."}, 404)
            return
        conteudo = arquivo.read_bytes()
        tipo = tipo or ("text/html; charset=utf-8" if arquivo.suffix == ".html" else "text/plain; charset=utf-8")
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(conteudo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(conteudo)

    def _redirecionar(self, destino):
        self.send_response(303)
        self.send_header("Location", destino)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self):
        pagina = urlparse(self.path)
        usuario, sessao = self._usuario()

        if pagina.path == "/login":
            if usuario:
                self._redirecionar("/")
            else:
                self._servir_arquivo(PASTA_SITE / "login.html")
            return

        if pagina.path == "/api/me":
            if not usuario:
                self.responder_json({"autenticado": False}, 401)
            else:
                self.responder_json({"autenticado": True, "usuario": usuario, "csrf": sessao["csrf"]})
            return

        if not usuario:
            if pagina.path.startswith("/api/"):
                self.responder_json({"erro": "Não autenticado."}, 401)
            else:
                self._redirecionar("/login")
            return

        if pagina.path in ("/admin", "/admin.html"):
            if usuario["papel"] != "admin":
                self.responder_json({"erro": "Acesso permitido somente ao administrador."}, 403)
                return
            self._servir_arquivo(PASTA_SITE / "admin.html")
            return

        if pagina.path == "/api/admin/usuarios":
            if usuario["papel"] != "admin":
                self.responder_json({"erro": "Acesso negado."}, 403)
            else:
                self.responder_json({"items": auth_store.listar_usuarios()})
            return

        if pagina.path == "/api/admin/canais":
            if usuario["papel"] != "admin":
                self.responder_json({"erro": "Acesso negado."}, 403)
            else:
                self.responder_json({"items": auth_store.listar_canais()})
            return

        if pagina.path == "/api/estatisticas":
            self.responder_json(buscar_estatisticas())
            return
        if pagina.path == "/api/resumo":
            self.responder_json(buscar_resumo())
            return
        if pagina.path.startswith("/api/promocoes/"):
            identificador = pagina.path.removeprefix("/api/promocoes/").strip("/")
            try:
                if not identificador.isdigit():
                    raise ValueError()
                promocao = buscar_promocao_detalhe(int(identificador))
            except ValueError:
                self.responder_json({"erro": "ID de promoção inválido."}, 400)
                return
            if promocao is None:
                self.responder_json({"erro": "Promoção não encontrada."}, 404)
                return
            self.responder_json({"item": promocao})
            return
        if pagina.path == "/api/promocoes":
            filtros = parse_qs(pagina.query)
            busca = filtros.get("busca", [""])[0].strip()
            loja = filtros.get("loja", [""])[0].strip()
            cupom = filtros.get("cupom", ["todos"])[0].strip()
            data_inicio = filtros.get("data_inicio", [""])[0].strip()
            data_fim = filtros.get("data_fim", [""])[0].strip()
            preco_min = filtros.get("preco_min", [""])[0].strip()
            preco_max = filtros.get("preco_max", [""])[0].strip()
            try:
                if preco_min and float(preco_min) < 0: raise ValueError()
                if preco_max and float(preco_max) < 0: raise ValueError()
                if preco_min and preco_max and float(preco_min) > float(preco_max): raise ValueError()
            except ValueError:
                self.responder_json({"erro": "Informe uma faixa de preço válida."}, 400)
                return
            self.responder_json({"items": buscar_promocoes(busca, loja, cupom, data_inicio, data_fim, preco_min, preco_max)})
            return
        if pagina.path == "/":
            self._servir_arquivo(PASTA_SITE / "index.html")
            return
        candidato = (PASTA_SITE / pagina.path.lstrip("/")).resolve()
        if not candidato.is_relative_to(PASTA_SITE.resolve()):
            self.responder_json({"erro": "Página não encontrada."}, 404)
            return
        self._servir_arquivo(candidato)

    def do_POST(self):
        pagina = urlparse(self.path)
        try:
            dados = self._json_body()
        except ValueError as erro:
            self.responder_json({"erro": str(erro)}, 400)
            return

        if pagina.path == "/api/login":
            ip = self.client_address[0]
            agora = time.time()
            with _TENTATIVAS_LOCK:
                tentativas = [t for t in _TENTATIVAS_LOGIN.get(ip, []) if agora - t < 600]
                _TENTATIVAS_LOGIN[ip] = tentativas
                if len(tentativas) >= 5:
                    self.responder_json({"erro": "Muitas tentativas. Aguarde 10 minutos."}, 429)
                    return
            usuario = auth_store.autenticar(str(dados.get("usuario", "")), str(dados.get("senha", "")))
            if not usuario:
                with _TENTATIVAS_LOCK:
                    _TENTATIVAS_LOGIN.setdefault(ip, []).append(agora)
                self.responder_json({"erro": "Usuário ou senha inválidos, ou conta desativada."}, 401)
                return
            with _TENTATIVAS_LOCK:
                _TENTATIVAS_LOGIN.pop(ip, None)
            token = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(32)
            with _SESSOES_LOCK:
                _SESSOES[token] = {"usuario": usuario, "csrf": csrf, "expira": agora + _TEMPO_SESSAO}
            self.responder_json({"ok": True, "usuario": usuario}, headers={"Set-Cookie": f"botpromos_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={_TEMPO_SESSAO}"})
            return

        sessao, token = self._sessao()
        if not sessao:
            self.responder_json({"erro": "Sessão expirada. Entre novamente."}, 401)
            return
        if not self._csrf_valido(sessao):
            self.responder_json({"erro": "Token de segurança inválido. Atualize a página."}, 403)
            return
        usuario = sessao["usuario"]
        if pagina.path == "/api/logout":
            with _SESSOES_LOCK:
                _SESSOES.pop(token, None)
            self.responder_json({"ok": True}, headers={"Set-Cookie": "botpromos_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"})
            return
        if usuario["papel"] != "admin":
            self.responder_json({"erro": "Acesso permitido somente ao administrador."}, 403)
            return
        try:
            if pagina.path == "/api/admin/usuarios":
                auth_store.criar_funcionario(str(dados.get("usuario", "")), str(dados.get("nome", "")), str(dados.get("senha", "")))
                self.responder_json({"ok": True}, 201)
                return
            if pagina.path == "/api/admin/canais":
                auth_store.salvar_canal(int(dados.get("chat_id")), str(dados.get("nome", "")))
                self.responder_json({"ok": True}, 201)
                return
            if pagina.path.startswith("/api/admin/usuarios/") and pagina.path.endswith("/status"):
                uid = int(pagina.path.split("/")[4])
                auth_store.alterar_usuario(uid, bool(dados.get("ativo")))
                self.responder_json({"ok": True})
                return
            if pagina.path.startswith("/api/admin/canais/") and pagina.path.endswith("/status"):
                cid = int(pagina.path.split("/")[4])
                auth_store.alterar_canal(cid, bool(dados.get("ativo")))
                self.responder_json({"ok": True})
                return
        except (ValueError, TypeError) as erro:
            self.responder_json({"erro": str(erro)}, 400)
            return
        except sqlite3.IntegrityError:
            self.responder_json({"erro": "Já existe um usuário com esse login."}, 409)
            return
        self.responder_json({"erro": "Rota não encontrada."}, 404)

    def do_DELETE(self):
        pagina = urlparse(self.path)
        sessao, _ = self._sessao()
        if not sessao:
            self.responder_json({"erro": "Não autenticado."}, 401)
            return
        if not self._csrf_valido(sessao):
            self.responder_json({"erro": "Token de segurança inválido."}, 403)
            return
        if sessao["usuario"]["papel"] != "admin":
            self.responder_json({"erro": "Acesso negado."}, 403)
            return
        try:
            if pagina.path.startswith("/api/admin/canais/"):
                auth_store.remover_canal(int(pagina.path.rsplit("/", 1)[1]))
                self.responder_json({"ok": True})
                return
        except (ValueError, TypeError) as erro:
            self.responder_json({"erro": str(erro)}, 400)
            return
        self.responder_json({"erro": "Rota não encontrada."}, 404)

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

def buscar_estatisticas():
    conexao = abrir_banco()

    try:
        por_dia = conexao.execute("""
            SELECT
                substr(data, 7, 4) || '-' ||
                substr(data, 4, 2) || '-' ||
                substr(data, 1, 2) AS dia,
                COUNT(*) AS quantidade
            FROM promocoes
            WHERE data IS NOT NULL AND TRIM(data) <> ''
            GROUP BY dia
            ORDER BY dia DESC
            LIMIT 14
        """).fetchall()

        por_loja = conexao.execute("""
            SELECT
                COALESCE(NULLIF(TRIM(loja), ''), 'Desconhecida') AS nome,
                COUNT(*) AS quantidade
            FROM promocoes
            GROUP BY nome
            ORDER BY quantidade DESC, nome
            LIMIT 8
        """).fetchall()

        cupons = conexao.execute("""
            SELECT
                CASE
                    WHEN cupom IS NOT NULL AND TRIM(cupom) <> ''
                    THEN 'Com cupom'
                    ELSE 'Sem cupom'
                END AS categoria,
                COUNT(*) AS quantidade
            FROM promocoes
            GROUP BY categoria
        """).fetchall()

        return {
            "por_dia": [
                {"dia": item["dia"], "quantidade": item["quantidade"]}
                for item in reversed(por_dia)
            ],
            "por_loja": [
                {"loja": item["nome"], "quantidade": item["quantidade"]}
                for item in por_loja
            ],
            "cupons": [
                {"categoria": item["categoria"], "quantidade": item["quantidade"]}
                for item in cupons
            ],
        }
    finally:
        conexao.close()


if __name__ == "__main__":
    iniciar()

