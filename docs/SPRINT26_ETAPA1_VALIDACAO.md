# Validação — Sprint 26 Etapa 1

## Automática

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

## Visual

```powershell
.\.venv\Scripts\python.exe gui_main.py
```

Validar:

1. apenas uma instância do Atlas abre;
2. sidebar aparece sem cortes;
3. cabeçalho mostra usuário e status;
4. conversa ocupa a maior área da janela;
5. painel direito mostra workflow, interação, CPU e memória;
6. Histórico abre normalmente;
7. Admin Console abre normalmente;
8. Retomar pendência continua respeitando o estado da sessão;
9. enviar mensagem funciona;
10. microfone e escuta contínua continuam funcionando;
11. cancelamento de execução permanece disponível;
12. redimensionamento até 1120x720 não sobrepõe controles.

## Critério de aceite

A etapa é concluída quando os testes passam e todos os itens visuais acima são
validados sem regressão funcional.
