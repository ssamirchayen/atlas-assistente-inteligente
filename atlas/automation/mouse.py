from __future__ import annotations

import pyautogui


class MouseAutomation:
    @staticmethod
    def click(
        x: int | None = None,
        y: int | None = None,
        button: str = "left",
    ) -> str:

        if x is None or y is None:
            pyautogui.click(button=button)
            return "Clique executado."

        pyautogui.click(
            x=x,
            y=y,
            button=button,
        )

        return f"Clique em ({x}, {y})."

    @staticmethod
    def double_click(
        x: int | None = None,
        y: int | None = None,
    ) -> str:

        pyautogui.doubleClick(
            x=x,
            y=y,
        )

        return "Clique duplo executado."

    @staticmethod
    def right_click(
        x: int | None = None,
        y: int | None = None,
    ) -> str:

        pyautogui.rightClick(
            x=x,
            y=y,
        )

        return "Clique direito executado."

    @staticmethod
    def move_to(
        x: int,
        y: int,
        duration: float = 0.30,
    ) -> str:

        pyautogui.moveTo(
            x=x,
            y=y,
            duration=duration,
        )

        return f"Mouse movido para ({x}, {y})."

    @staticmethod
    def drag_to(
        x: int,
        y: int,
        duration: float = 0.50,
    ) -> str:

        pyautogui.dragTo(
            x=x,
            y=y,
            duration=duration,
        )

        return f"Mouse arrastado para ({x}, {y})."

    @staticmethod
    def scroll(amount: int) -> str:

        pyautogui.scroll(amount)

        return "Rolagem executada."

    @staticmethod
    def position() -> tuple[int, int]:

        position = pyautogui.position()

        return position.x, position.y