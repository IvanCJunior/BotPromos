# Relatório de classificação para lançamento

## A — Obrigatórios em execução

- `main.py`
- `affiliate/manager.py` e `affiliate/mercadolivre.py`
- `ai/`
- `browser/browser_manager.py`
- `config/`
- `dashboard/painel.py`
- `database/`
- `diagnostics/audit.py`, `diagnostic.py` e `events.py`
- `reports/history.py`
- `services/mercadolivre_service.py`
- `telegram_bot/`
- `utils/file_cleanup.py`, `link_resolver.py` e `message_builder.py`
- `whatsapp/`
- `chrome_bot_profile/` e `whatsapp_profile/` na máquina já autenticada
- `.env`, sessão Telegram e banco de dados

## B — Desenvolvimento / não incluir em pacote limpo

- `.venv/`
- `tests/`
- todos os `__pycache__/`
- screenshots e HTML antigos de diagnóstico
- logs históricos antigos

## C — Legado preservado, mas fora do fluxo ativo

- `affiliate/amazon.py`
- `services/amazon_service.py`
- `playwright_tools/amazon_service.py`
- `playwright_tools/login_amazon.py`
- `playwright_tools/session/amazon.json`

Esses arquivos não são importados pelo fluxo de produção após esta atualização.

## D — Candidatos à remoção após confirmação

- `browser_profile/`
- `playwright_tools/profile_ml/`
- arquivos vazios `None` e `bool`
- `utils/hash.py`
- módulos antigos em `diagnostics/` sem referência direta aparente

Nenhum item do grupo D foi removido nesta versão.
