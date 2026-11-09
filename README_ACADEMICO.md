# BotPromos — Projeto de Software

Projeto acadêmico desenvolvido para a disciplina **Projeto de Software**.

### Equipe
- Aluno 1: Ivan Augusto Covelli Junior
- Aluno 2:
- Aluno 3:
- Aluno 4:
- Aluno 5:
- Aluno 6:
- Aluno 7:

### Entregas
- **AC1:** dashboard de acompanhamento das promoções.
- **AC2:** filtros avançados, detalhes, gráficos e estatísticas.
- **AC3:** autenticação, perfis de acesso e administração de usuários e canais Telegram.

### Links
- Board: https://github.com/users/IvanCJunior/projects/1/views/1
- GitHub: https://github.com/IvanCJunior/BotPromos
- Vídeo AC1: https://www.youtube.com/watch?v=AsgcomiXX0s

### Execução
```bash
python -m dashboard.web
```

Acesse `http://127.0.0.1:8000`.


## AC3 — Controle de acesso e administração local

O dashboard agora possui autenticação, perfis de administrador e funcionário, gerenciamento de funcionários e gerenciamento de canais Telegram. As contas e canais são armazenados no SQLite (`promocoes.db`). Senhas são armazenadas com hash scrypt.

### Primeira execução

1. No terminal, na pasta raiz do projeto, execute `python -m dashboard.criar_admin`.
2. Informe usuário, nome e uma senha numérica de exatamente 4 dígitos (conforme requisito definido para esta demonstração acadêmica).
3. Inicie o painel com `python -m dashboard.web`.
4. Acesse `http://127.0.0.1:8000` e entre com a conta de administrador.
5. No botão **Administração**, cadastre funcionários e gerencie os canais monitorados.

As senhas de administrador e funcionário devem ter exatamente 4 dígitos nesta versão.

O painel foi configurado para apresentação local. As sessões ficam em memória e expiram após 30 minutos de inatividade; reiniciar o servidor encerra todas as sessões. O listener do Telegram consulta os canais ativos no banco. A conta conectada ao Telegram precisa ter acesso aos canais cadastrados.
