from atlas.session.manager import SessionManager


def main() -> None:
    session = SessionManager()

    session.save_project("Atlas")
    session.save_current_task("Testar o sistema de sessão")
    session.save_last_command("continuar o projeto")
    session.save_last_file("atlas/session/manager.py")
    session.save_active_window("Visual Studio Code")

    session.add_opened_file("atlas/planner/executor.py")
    session.add_opened_file("atlas/agents/browser_agent.py")

    session.add_browser_tab("Documentação do Python")
    session.add_browser_tab("GitHub do Atlas")

    session.add_note("Integrar a sessão ao cérebro do Atlas")
    session.add_note("Depois conectar ao Planner")

    print("\n=== RESUMO DA SESSÃO ===\n")
    print(session.get_summary())

    print("\n=== CONTEXTO PARA A IA ===\n")
    print(session.build_prompt_context())


if __name__ == "__main__":
    main()