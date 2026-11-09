"""Cria o primeiro administrador do dashboard BotPromos."""
import getpass
from dashboard.auth_store import criar_admin


def main():
    print("=== Configuração inicial do administrador BotPromos ===")
    usuario = input("Usuário: ").strip()
    nome = input("Nome: ").strip()
    senha = getpass.getpass("Senha (4 dígitos): ")
    confirmar = getpass.getpass("Confirme a senha: ")
    if senha != confirmar:
        print("As senhas não conferem.")
        return
    try:
        criar_admin(usuario, nome, senha)
        print("Administrador criado com sucesso. Inicie o painel com: python -m dashboard.web")
    except Exception as erro:
        print(f"Não foi possível criar o administrador: {erro}")


if __name__ == "__main__":
    main()
