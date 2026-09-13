from diagnostics.audit import audit
from diagnostics.events import StatusPromocao


def main() -> None:
    promocao_id = audit.iniciar_promocao(
        canal="CANAL DE TESTE",
        telegram_id=123456,
        texto="Produto de teste por R$ 99,90",
    )

    audit.etapa(
        promocao_id,
        etapa="EXTRACAO_LINK",
        codigo="LINK_ENCONTRADO",
        mensagem="Link de teste extraído.",
        link="https://exemplo.com/produto",
    )

    audit.atualizar(
        promocao_id,
        loja="Loja de teste",
        link_original="https://exemplo.com/produto",
        preco="R$ 99,90",
    )

    audit.alerta(
        promocao_id,
        etapa="DOWNLOAD_IMAGEM",
        codigo="IMAGEM_AUSENTE",
        mensagem="Teste de alerta sem interromper o processamento.",
    )

    audit.finalizar(
        promocao_id,
        status=StatusPromocao.ENVIADA.value,
        codigo="TESTE_CONCLUIDO",
        mensagem="Teste da Fase 1 concluído.",
    )

    print()
    print("✅ TESTE DO DIAGNÓSTICO CONCLUÍDO")
    print(f"Execução: {audit.execucao_id}")
    print("Verifique a pasta logs\\diagnostico.")


if __name__ == "__main__":
    main()
