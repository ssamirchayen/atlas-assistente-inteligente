from __future__ import annotations

import time

import pyautogui


class KeyboardAutomation:
    @staticmethod
    def write(
        text: str,
        interval: float = 0.03,
        delay_before: float = 1.0,
    ) -> str:
        text = str(text).strip()

        if not text:
            return "Não há texto para digitar."

        time.sleep(delay_before)

        pyautogui.write(
            text,
            interval=interval,
        )

        return "Texto digitado com sucesso."

    @staticmethod
    def press(key: str) -> str:
        key = key.strip().lower()

        if not key:
            return "Você precisa informar uma tecla."

        pyautogui.press(key)

        return f"Tecla '{key}' pressionada."

    @staticmethod
    def hotkey(*keys: str) -> str:
        normalized_keys = [
            key.strip().lower()
            for key in keys
            if key and key.strip()
        ]

        if not normalized_keys:
            return "Nenhuma combinação foi informada."

        pyautogui.hotkey(*normalized_keys)

        return (
            "Atalho executado: "
            + " + ".join(normalized_keys)
        )

    @staticmethod
    def enter() -> str:
        pyautogui.press("enter")
        return "Enter pressionado."

    @staticmethod
    def backspace() -> str:
        pyautogui.press("backspace")
        return "Backspace pressionado."

    @staticmethod
    def delete() -> str:
        pyautogui.press("delete")
        return "Delete pressionado."