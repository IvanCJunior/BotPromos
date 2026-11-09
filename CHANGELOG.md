## 2.1.0-rc4

- Adicionada limpeza conservadora de caches antes da abertura dos navegadores.
- Perfis com Chrome já aberto são ignorados automaticamente.
- Cookies, IndexedDB, Local Storage, Session Storage, Network e Service Worker/CacheStorage são preservados.
- Nova configuração `LIMPAR_CACHE_NAVEGADORES`, habilitada por padrão em produção.

# Changelog

## 2.1.0-rc1 — Produção leve

- Removido o import ativo do conversor Amazon no gerenciador de afiliados.
- Mercado Livre permanece como única loja habilitada.
- Adicionado `BOT_MODE=production`.
- Monitor periódico dos perfis fica desativado por padrão.
- Screenshots, HTML e JSON pesados do Mercado Livre ficam desativados por padrão.
- A auditoria resumida, fila do WhatsApp, watchdog e limpeza de imagens permanecem ativos.
- Adicionado `.env.example` com as novas opções.

### Reativar diagnósticos temporariamente

```env
DIAGNOSTICOS_DETALHADOS=true
MONITORAR_PERFIS=true
```


## AC3 — autenticação e administração local
- Adiciona login e logout com sessões temporárias.
- Armazena senhas com hash scrypt, sem salvar senhas em texto puro.
- Implementa perfis de administrador e funcionário e proteção das rotas administrativas.
- Adiciona cadastro e ativação/desativação de funcionários.
- Adiciona cadastro, ativação/desativação e remoção de canais Telegram.
- Faz o listener consultar os canais ativos no SQLite, sem depender apenas da lista fixa.
- Mantém o dashboard AC2 e seus filtros, detalhes, gráficos e estatísticas.


## AC3 — fechamento da entrega
- Documentado o requisito de senha numérica de quatro dígitos.
- Incluído roteiro de validação e registro explícito dos testes não executados com o bot desligado.
- Registradas as limitações de uso local e da senha curta.
