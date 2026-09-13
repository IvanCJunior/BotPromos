# AC1 — Projeto de Software

## Projeto
**BotPromos — Sistema automatizado de captura e distribuição de promoções**

## Problema
Encontrar promoções em canais do Telegram, tratar as informações e distribuí-las de forma automatizada exige várias etapas manuais e pode gerar perda de tempo e informações inconsistentes.

## Solução
O BotPromos monitora canais do Telegram, identifica promoções, extrai dados relevantes, processa links de afiliado, registra os dados em banco de dados e encaminha as promoções para o WhatsApp.

## Arquitetura em 3 camadas
- **Front-end:** dashboard web responsivo (`dashboard/static/index.html`).
- **Back-end:** aplicação Python e API HTTP do dashboard, além dos módulos de captura e processamento.
- **Banco de dados:** SQLite (`promocoes.db`).

## Funcionalidade apresentada na AC1
**Dashboard de acompanhamento das promoções**, permitindo:
1. visualizar o total de promoções cadastradas;
2. visualizar a quantidade de promoções com cupom;
3. consultar as últimas promoções;
4. pesquisar por produto, canal, loja ou cupom;
5. abrir o link da promoção.

## Como executar o dashboard
Na raiz do projeto:

```bash
python -m dashboard.web
```

Depois acessar:

`http://127.0.0.1:8000`

O dashboard consulta diretamente o banco `promocoes.db` utilizado pelo projeto.
