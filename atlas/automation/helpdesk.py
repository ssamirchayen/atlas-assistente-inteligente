from __future__ import annotations

from typing import Any


class HelpDeskAutomation:
    """Gera procedimentos seguros para a triagem de incidentes de TI."""

    _CHECKLISTS = {
        "network": (
            "Diagnóstico inicial de rede:\n"
            "1. Confirme se outros dispositivos também estão sem internet.\n"
            "2. Verifique o Wi-Fi, o modo avião ou o cabo de rede.\n"
            "3. Confira se o Windows recebeu um endereço de rede válido.\n"
            "4. Reinicie o adaptador e o roteador somente se autorizado.\n"
            "5. Registre a mensagem de erro e o horário da falha."
        ),
        "printer": (
            "Diagnóstico inicial da impressora:\n"
            "1. Verifique energia, cabo USB ou conexão de rede.\n"
            "2. Confirme se a impressora correta está definida como padrão.\n"
            "3. Consulte a fila e identifique documentos bloqueados.\n"
            "4. Confira papel, toner e mensagens no painel.\n"
            "5. Reinicie o serviço de impressão somente se autorizado."
        ),
        "audio": (
            "Diagnóstico inicial de áudio:\n"
            "1. Confirme o dispositivo de entrada ou saída selecionado.\n"
            "2. Verifique volume, mudo, cabos e conexões Bluetooth.\n"
            "3. Confira as permissões de microfone do Windows.\n"
            "4. Teste o dispositivo em outro aplicativo.\n"
            "5. Registre o modelo do dispositivo e o erro apresentado."
        ),
        "performance": (
            "Diagnóstico inicial de desempenho:\n"
            "1. Abra o Gerenciador de Tarefas e observe CPU, memória e disco.\n"
            "2. Confirme se há espaço livre na unidade do sistema.\n"
            "3. Identifique aplicativos de inicialização desnecessários.\n"
            "4. Verifique atualizações pendentes e reinicializações.\n"
            "5. Faça uma varredura de segurança conforme a política da empresa."
        ),
        "application": (
            "Diagnóstico inicial do aplicativo:\n"
            "1. Registre a mensagem de erro exatamente como apareceu.\n"
            "2. Confirme se o problema ocorre com outros usuários.\n"
            "3. Encerre o processo com segurança e tente abrir novamente.\n"
            "4. Verifique conexão, permissões e atualizações disponíveis.\n"
            "5. Não reinstale nem apague dados antes de criar um backup."
        ),
        "general": (
            "Triagem inicial de suporte:\n"
            "1. Registre usuário, equipamento e horário do incidente.\n"
            "2. Anote o comportamento esperado e o que realmente ocorreu.\n"
            "3. Confirme se o problema pode ser reproduzido.\n"
            "4. Avalie impacto, urgência e quantidade de usuários afetados.\n"
            "5. Evite alterações administrativas sem autorização."
        ),
    }

    def diagnose(self, parameters: dict[str, Any]) -> str:
        category = str(parameters.get("category", "")).strip().casefold()
        checklist = self._CHECKLISTS.get(category)

        if checklist is None:
            raise ValueError(
                f"Categoria de suporte não reconhecida: {category or 'vazia'}"
            )

        return checklist
