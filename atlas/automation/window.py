from __future__ import annotations

import ctypes
import time

import pyautogui


class WindowAutomation:
    """
    Controla a janela ativa do Windows usando atalhos
    de teclado e comandos nativos do sistema.
    """

    def minimize(self) -> str:
        """
        Minimiza a janela ativa.
        """

        pyautogui.hotkey("win", "down")
        time.sleep(0.2)

        return "Janela minimizada."

    def maximize(self) -> str:
        """
        Maximiza a janela ativa.
        """

        pyautogui.hotkey("win", "up")
        time.sleep(0.2)

        return "Janela maximizada."

    def restore(self) -> str:
        """
        Restaura a janela ativa para o tamanho anterior.
        """

        hwnd = self._get_active_window()

        if not hwnd:
            return "Nenhuma janela ativa foi encontrada."

        SW_RESTORE = 9

        ctypes.windll.user32.ShowWindow(
            hwnd,
            SW_RESTORE,
        )

        time.sleep(0.2)

        return "Janela restaurada."

    def close(self) -> str:
        """
        Fecha a janela ativa.
        """

        pyautogui.hotkey("alt", "f4")
        time.sleep(0.2)

        return "Comando para fechar a janela enviado."

    def next(self) -> str:
        """
        Alterna para a próxima janela aberta.
        """

        pyautogui.hotkey("alt", "tab")
        time.sleep(0.3)

        return "Alternando para a próxima janela."

    def previous(self) -> str:
        """
        Alterna para a janela anterior.
        """

        pyautogui.hotkey(
            "alt",
            "shift",
            "tab",
        )

        time.sleep(0.3)

        return "Alternando para a janela anterior."

    def show_desktop(self) -> str:
        """
        Mostra ou restaura a área de trabalho.
        """

        pyautogui.hotkey("win", "d")
        time.sleep(0.3)

        return "Área de trabalho exibida."

    def focus_by_title(
        self,
        title: str,
    ) -> str:
        """
        Procura uma janela aberta pelo título e coloca
        essa janela em primeiro plano.
        """

        clean_title = title.strip()

        if not clean_title:
            return "O título da janela está vazio."

        matching_windows = pyautogui.getWindowsWithTitle(
            clean_title
        )

        if not matching_windows:
            return (
                f"Não encontrei uma janela com o título "
                f"{clean_title}."
            )

        window = matching_windows[0]

        try:
            if window.isMinimized:
                window.restore()
                time.sleep(0.2)

            window.activate()
            time.sleep(0.3)

            return (
                f"Janela com o título "
                f"{clean_title} ativada."
            )

        except Exception as error:
            return (
                "Não consegui ativar a janela. "
                f"Erro: {error}"
            )

    def minimize_by_title(
        self,
        title: str,
    ) -> str:
        """
        Minimiza uma janela procurando pelo título.
        """

        window = self._find_window(title)

        if window is None:
            return (
                f"Não encontrei uma janela com o título "
                f"{title}."
            )

        try:
            window.minimize()
            time.sleep(0.2)

            return (
                f"Janela {title} minimizada."
            )

        except Exception as error:
            return (
                "Não consegui minimizar a janela. "
                f"Erro: {error}"
            )

    def maximize_by_title(
        self,
        title: str,
    ) -> str:
        """
        Maximiza uma janela procurando pelo título.
        """

        window = self._find_window(title)

        if window is None:
            return (
                f"Não encontrei uma janela com o título "
                f"{title}."
            )

        try:
            window.maximize()
            time.sleep(0.2)

            return (
                f"Janela {title} maximizada."
            )

        except Exception as error:
            return (
                "Não consegui maximizar a janela. "
                f"Erro: {error}"
            )

    def close_by_title(
        self,
        title: str,
    ) -> str:
        """
        Fecha uma janela procurando pelo título.
        """

        window = self._find_window(title)

        if window is None:
            return (
                f"Não encontrei uma janela com o título "
                f"{title}."
            )

        try:
            window.close()
            time.sleep(0.2)

            return (
                f"Comando para fechar a janela "
                f"{title} enviado."
            )

        except Exception as error:
            return (
                "Não consegui fechar a janela. "
                f"Erro: {error}"
            )

    @staticmethod
    def _get_active_window() -> int:
        """
        Retorna o identificador da janela ativa.
        """

        return ctypes.windll.user32.GetForegroundWindow()

    @staticmethod
    def _find_window(title: str):
        """
        Retorna a primeira janela que combine com o título.
        """

        clean_title = title.strip()

        if not clean_title:
            return None

        matching_windows = pyautogui.getWindowsWithTitle(
            clean_title
        )

        if not matching_windows:
            return None

        return matching_windows[0]