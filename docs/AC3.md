# AC3 — Autenticação, permissões e administração

## Objetivo
Adicionar controle de acesso ao dashboard do BotPromos, preservando as funcionalidades desenvolvidas na AC1 e AC2. A aplicação foi preparada para demonstração local ao professor.

## Perfis de acesso
- **Administrador:** consulta o dashboard e administra funcionários e canais Telegram.
- **Funcionário:** consulta promoções, filtros, detalhes e estatísticas. Não acessa as rotas de administração.

## Funcionalidades
1. Login e logout.
2. Senhas protegidas com hash scrypt.
3. Sessões com expiração após 30 minutos de inatividade.
4. Limitação temporária após cinco tentativas de login malsucedidas em dez minutos por endereço local.
5. Token anti-CSRF nas operações de alteração.
6. Cadastro e ativação/desativação de funcionários.
7. Cadastro, ativação/desativação e remoção de canais Telegram.
8. Persistência de usuários e canais no banco SQLite.
9. Listener do Telegram consulta os canais ativos cadastrados no banco.

## Preparação para demonstração
Na pasta raiz do projeto, execute:

```powershell
python -m dashboard.criar_admin
python -m dashboard.web
```

O primeiro comando solicita usuário, nome e senha do administrador. Nesta versão acadêmica, a senha deve conter exatamente quatro dígitos numéricos, conforme requisito definido para a demonstração. O segundo inicia o painel em `http://127.0.0.1:8000`.

Entre com o administrador, abra **Administração**, cadastre um funcionário e faça os testes de acesso. O funcionário deve conseguir consultar o dashboard, mas não abrir a administração.

## Observações técnicas
- Usuários e canais são guardados nas tabelas `usuarios` e `canais_telegram` do arquivo `promocoes.db`.
- As sessões são mantidas em memória; reiniciar o servidor encerra as sessões ativas.
- O painel permanece vinculado a `127.0.0.1`, adequado para a apresentação local definida para esta entrega.
- Para monitorar um canal, a conta Telegram utilizada pelo Telethon precisa ter acesso a ele.
- O pacote de entrega não deve conter `.env`, perfis de navegador, cookies ou arquivos de sessão de serviços externos.


## Roteiro de validação realizado
- [x] Criação do administrador.
- [x] Login de administrador e funcionário.
- [x] Bloqueio de login para conta desativada e retorno do acesso após reativação.
- [x] Cadastro, ativação, desativação e remoção de canais pela administração.
- [x] Persistência de usuários e canais após reiniciar o servidor.
- [x] Bloqueio de acesso do funcionário à página e às rotas administrativas.
- [x] Preservação do dashboard AC2 (filtros, detalhes, gráficos e estatísticas).
- [x] Verificação estática da integração do listener com a lista de canais ativos no SQLite.
- [ ] Teste em execução do listener com uma conta Telegram conectada: não realizado nesta entrega, pois o bot permaneceu desligado durante a validação do painel.

## Limites e segurança da demonstração
- A senha de quatro dígitos é uma concessão de usabilidade solicitada para a apresentação; não é adequada para exposição pública ou uso em ambiente de produção.
- O servidor escuta somente em `127.0.0.1`; não publicar diretamente na internet.
- A proteção contra tentativas de login e as sessões são mantidas em memória e reiniciam junto com o processo.
