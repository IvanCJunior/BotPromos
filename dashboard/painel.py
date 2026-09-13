import os
import sqlite3
from datetime import datetime


inicio = datetime.now()


def limpar():
    os.system("cls" if os.name == "nt" else "clear")


def obter_total():
    conn = sqlite3.connect("promocoes.db")
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM promocoes")
    total = cursor.fetchone()[0]

    conn.close()

    return total


def mostrar_painel():
    limpar()

    tempo_online = datetime.now() - inicio

    print("=" * 70)
    print("BOT DE PROMOÇÕES")
    print("=" * 70)
    print()

    print("Status............. ONLINE")
    print(f"Tempo online....... {tempo_online}")
    print(f"Promoções.......... {obter_total()}")

    print()