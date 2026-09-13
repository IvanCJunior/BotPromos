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
