from __future__ import annotations

import datetime
import os
import subprocess
import webbrowser
from urllib.parse import quote_plus


def open_chrome() -> str:
    """Tenta abrir o Google Chrome."""

    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]

    for chrome_path in chrome_paths:
        if os.path.exists(chrome_path):
            subprocess.Popen([chrome_path])
            return "Abrindo o Google Chrome."

    webbrowser.open("https://www.google.com")
    return "Não encontrei o Chrome instalado, então abri o navegador padrão."


def open_notepad() -> str:
    """Abre o Bloco de Notas do Windows."""

    subprocess.Popen(["notepad.exe"])
    return "Abrindo o Bloco de Notas."


def tell_time() -> str:
    """Retorna a hora atual."""

    now = datetime.datetime.now()
    return f"Agora são {now.hour} horas e {now.minute} minutos."


def tell_date() -> str:
    """Retorna a data atual."""

    now = datetime.datetime.now()

    weekdays = [
        "segunda-feira",
        "terça-feira",
        "quarta-feira",
        "quinta-feira",
        "sexta-feira",
        "sábado",
        "domingo",
    ]

    months = [
        "janeiro",
        "fevereiro",
        "março",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    ]

    weekday = weekdays[now.weekday()]
    month = months[now.month - 1]

    return (
        f"Hoje é {weekday}, dia {now.day} de {month} de {now.year}."
    )


def search_google(query: str) -> str:
    """Pesquisa alguma coisa no Google."""

    query = query.strip()

    if not query:
        return "Você precisa me dizer o que deseja pesquisar."

    encoded_query = quote_plus(query)
    url = f"https://www.google.com/search?q={encoded_query}"

    webbrowser.open(url)

    return f"Pesquisando por {query}."


def execute_command(command: str) -> tuple[bool, str]:
    """
    Analisa o comando informado pelo usuário.

    Retorna:
        tuple[bool, str]:
        - True quando o comando foi reconhecido.
        - False quando o comando não foi reconhecido.
        - A resposta que o Atlas deverá falar.
    """

    normalized_command = command.lower().strip()

    if not normalized_command:
        return False, "Eu não consegui entender o comando."

    if any(
        phrase in normalized_command
        for phrase in [
            "abra o chrome",
            "abrir o chrome",
            "abra o google chrome",
            "abrir google chrome",
        ]
    ):
        return True, open_chrome()

    if any(
        phrase in normalized_command
        for phrase in [
            "abra o bloco de notas",
            "abrir o bloco de notas",
            "abra o notepad",
            "abrir notepad",
        ]
    ):
        return True, open_notepad()

    if any(
        phrase in normalized_command
        for phrase in [
            "que horas são",
            "qual é a hora",
            "qual a hora",
            "me diga as horas",
            "horário agora",
        ]
    ):
        return True, tell_time()

    if any(
        phrase in normalized_command
        for phrase in [
            "que dia é hoje",
            "qual é a data",
            "qual a data",
            "data de hoje",
        ]
    ):
        return True, tell_date()

    search_commands = [
        "pesquise por ",
        "pesquisar por ",
        "procure por ",
        "buscar por ",
        "pesquise ",
        "procure ",
    ]

    for search_command in search_commands:
        if normalized_command.startswith(search_command):
            query = normalized_command.removeprefix(search_command).strip()
            return True, search_google(query)

    return False, "Este comando ainda não está disponível."