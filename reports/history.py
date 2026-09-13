import sqlite3


def mostrar_historico():

    conn = sqlite3.connect("promocoes.db")
    cursor = conn.cursor()

    print()
    print("=" * 60)
    print("HISTÓRICO DE PROMOÇÕES")
    print("=" * 60)

    cursor.execute("SELECT COUNT(*) FROM promocoes")
    total = cursor.fetchone()[0]

    print(f"Total de promoções: {total}")

    print()

    cursor.execute("""
        SELECT loja, COUNT(*)
        FROM promocoes
        GROUP BY loja
        ORDER BY COUNT(*) DESC
    """)

    print("Promoções por loja:")

    resultados = cursor.fetchall()

    if resultados:
        for loja, quantidade in resultados:
            print(f"  {loja}: {quantidade}")
    else:
        print("  Nenhuma promoção cadastrada.")

    print()

    cursor.execute("""
        SELECT canal, COUNT(*)
        FROM promocoes
        GROUP BY canal
        ORDER BY COUNT(*) DESC
    """)

    print("Promoções por canal:")

    resultados = cursor.fetchall()

    if resultados:
        for canal, quantidade in resultados:
            print(f"  {canal}: {quantidade}")
    else:
        print("  Nenhuma promoção cadastrada.")

    print("=" * 60)

    conn.close()