"""Persistência de usuários e canais do painel AC3 (SQLite + stdlib)."""
from __future__ import annotations
import hashlib
import hmac
import os
import secrets
import sqlite3
from pathlib import Path
from threading import RLock

BASE_DIR = Path(__file__).resolve().parent.parent
BANCO = BASE_DIR / "promocoes.db"
_LOCK = RLock()


def conectar():
    con = sqlite3.connect(BANCO, timeout=20)
    con.row_factory = sqlite3.Row
    return con


def hash_senha(senha: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derivada = hashlib.scrypt(senha.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${derivada.hex()}"


def verificar_senha(senha: str, armazenada: str) -> bool:
    try:
        algoritmo, salt_hex, hash_hex = armazenada.split("$", 2)
        if algoritmo != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        esperado = bytes.fromhex(hash_hex)
        atual = hashlib.scrypt(senha.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(atual, esperado)
    except (ValueError, TypeError):
        return False


def inicializar():
    with _LOCK, conectar() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL COLLATE NOCASE UNIQUE,
            nome TEXT NOT NULL,
            senha_hash TEXT NOT NULL,
            papel TEXT NOT NULL CHECK(papel IN ('admin','funcionario')),
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS canais_telegram (
            chat_id INTEGER PRIMARY KEY,
            nome TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        # Migra a lista fixa existente apenas na primeira inicialização da tabela.
        total = con.execute("SELECT COUNT(*) FROM canais_telegram").fetchone()[0]
        if total == 0:
            try:
                from config.channels import CHANNELS
                for chat_id, nome in CHANNELS.items():
                    con.execute("INSERT OR IGNORE INTO canais_telegram(chat_id,nome,ativo) VALUES(?,?,1)", (int(chat_id), str(nome)))
            except Exception:
                pass


def criar_admin(usuario: str, nome: str, senha: str):
    usuario, nome = usuario.strip(), nome.strip()
    if len(usuario) < 3 or not (senha.isdigit() and len(senha) == 4) or not nome:
        raise ValueError("Informe usuário com ao menos 3 caracteres, nome e senha numérica de exatamente 4 dígitos.")
    with _LOCK, conectar() as con:
        existe = con.execute("SELECT 1 FROM usuarios WHERE papel='admin' LIMIT 1").fetchone()
        if existe:
            raise ValueError("Já existe um administrador cadastrado.")
        con.execute("INSERT INTO usuarios(usuario,nome,senha_hash,papel,ativo) VALUES(?,?,?,'admin',1)", (usuario, nome, hash_senha(senha)))


def autenticar(usuario: str, senha: str):
    with conectar() as con:
        row = con.execute("SELECT id,usuario,nome,senha_hash,papel,ativo FROM usuarios WHERE usuario=? COLLATE NOCASE", (usuario.strip(),)).fetchone()
    if not row or not row['ativo'] or not verificar_senha(senha, row['senha_hash']):
        return None
    return {"id": row['id'], "usuario": row['usuario'], "nome": row['nome'], "papel": row['papel']}


def listar_usuarios():
    with conectar() as con:
        rows = con.execute("SELECT id,usuario,nome,papel,ativo,criado_em FROM usuarios ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def criar_funcionario(usuario, nome, senha):
    usuario, nome = usuario.strip(), nome.strip()
    if len(usuario) < 3 or not (senha.isdigit() and len(senha) == 4) or not nome:
        raise ValueError("Usuário deve ter ao menos 3 caracteres, nome obrigatório e senha numérica de exatamente 4 dígitos.")
    with _LOCK, conectar() as con:
        con.execute("INSERT INTO usuarios(usuario,nome,senha_hash,papel,ativo) VALUES(?,?,?,'funcionario',1)", (usuario, nome, hash_senha(senha)))


def alterar_usuario(usuario_id: int, ativo: bool):
    with _LOCK, conectar() as con:
        row = con.execute("SELECT papel,ativo FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
        if not row:
            raise ValueError("Funcionário não encontrado.")
        if row['papel'] == 'admin':
            raise ValueError("A conta de administrador não pode ser alterada por esta tela.")
        con.execute("UPDATE usuarios SET ativo=? WHERE id=?", (1 if ativo else 0, usuario_id))


def listar_canais(apenas_ativos=False):
    with conectar() as con:
        sql = "SELECT chat_id,nome,ativo,criado_em FROM canais_telegram"
        if apenas_ativos:
            sql += " WHERE ativo=1"
        sql += " ORDER BY nome COLLATE NOCASE"
        return [dict(r) for r in con.execute(sql).fetchall()]


def salvar_canal(chat_id: int, nome: str):
    nome = nome.strip()
    if not nome or not str(chat_id).lstrip('-').isdigit():
        raise ValueError("Informe um ID numérico de canal e um nome.")
    with _LOCK, conectar() as con:
        con.execute("INSERT INTO canais_telegram(chat_id,nome,ativo) VALUES(?,?,1) ON CONFLICT(chat_id) DO UPDATE SET nome=excluded.nome,ativo=1", (int(chat_id), nome))


def alterar_canal(chat_id: int, ativo: bool):
    with _LOCK, conectar() as con:
        cur = con.execute("UPDATE canais_telegram SET ativo=? WHERE chat_id=?", (1 if ativo else 0, int(chat_id)))
        if not cur.rowcount:
            raise ValueError("Canal não encontrado.")


def remover_canal(chat_id: int):
    with _LOCK, conectar() as con:
        cur = con.execute("DELETE FROM canais_telegram WHERE chat_id=?", (int(chat_id),))
        if not cur.rowcount:
            raise ValueError("Canal não encontrado.")


inicializar()
