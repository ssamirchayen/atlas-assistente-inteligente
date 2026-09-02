from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import requests

from atlas.core.config import (
    OLLAMA_URL,
    VISION_MODEL,
    VISION_TIMEOUT,
)
from atlas.vision.models import (
    VisionAnalysis,
    VisionBoundingBox,
    VisionUIElement,
)


class VisionAnalysisError(RuntimeError):
    """Falha controlada ao interpretar uma imagem."""


class OllamaVisionAnalyzer:
    """Interpretação visual local usando um modelo multimodal do Ollama."""

    def __init__(
        self,
        *,
        model: str = VISION_MODEL,
        url: str = OLLAMA_URL,
        timeout: float = VISION_TIMEOUT,
        post=None,
    ) -> None:
        self.model = model.strip()
        self.url = url.strip()
        self.timeout = timeout
        self._post = post or requests.post

    def analyze(
        self,
        image_path: Path,
        *,
        question: str = "Descreva o que está visível na tela.",
    ) -> VisionAnalysis:
        path = Path(image_path)

        if not path.is_file():
            raise VisionAnalysisError(
                f"Imagem não encontrada: {path}"
            )

        content = self._request(
            path,
            self._build_prompt(question),
        )
        return self._parse_content(content)

    def locate_target(
        self,
        image_path: Path,
        *,
        target: str,
    ) -> VisionUIElement | None:
        """Grounding focado aceitando bbox OU ponto central."""

        path = Path(image_path)

        if not path.is_file():
            raise VisionAnalysisError(
                f"Imagem não encontrada: {path}"
            )

        prompt = (
            "Observe a imagem inteira e localize SOMENTE o alvo pedido.\n"
            f"ALVO: {target.strip()}\n\n"
            "Retorne APENAS um objeto JSON. "
            "Se o alvo estiver visível, informe preferencialmente bbox "
            "e também o ponto central. Exemplo:\n"
            "{"
            '"found":true,'
            '"label":"Enviar",'
            '"kind":"button",'
            '"bbox":[900,850,980,930],'
            '"point":[940,890],'
            '"confidence":0.95'
            "}\n"
            "As coordenadas bbox e point usam escala normalizada 0..1000 "
            "considerando a imagem inteira, da esquerda para a direita e "
            "de cima para baixo.\n"
            "Se não conseguir bbox mas conseguir identificar o centro, "
            "retorne bbox null e point [x,y].\n"
            "Se não encontrar o alvo, retorne "
            '{"found":false,"label":"","bbox":null,"point":null,'
            '"confidence":0.0}.'
        )

        content = self._request(path, prompt)
        payload = self._extract_json_object(content)

        if payload.get("found") is False:
            return None

        element = self._parse_ui_element(payload)

        if element.bbox is not None:
            return element

        point = self._parse_point(
            payload.get("point")
            or payload.get("center")
            or payload.get("centro")
        )

        if point is None:
            # Alguns modelos devolvem x/y diretamente.
            if "x" in payload and "y" in payload:
                point = self._parse_point(
                    [payload["x"], payload["y"]]
                )

        if point is None:
            return None

        x, y = point

        # Caixa pequena apenas para representar o centro fornecido pelo modelo.
        # Não é usada para clicar nesta etapa.
        half_w = 25
        half_h = 20
        x1 = max(0, x - half_w)
        y1 = max(0, y - half_h)
        x2 = min(1000, x + half_w)
        y2 = min(1000, y + half_h)

        if x2 <= x1 or y2 <= y1:
            return None

        return VisionUIElement(
            label=str(
                payload.get("label", target)
            ).strip() or target,
            kind=str(
                payload.get("kind", "unknown")
            ).strip() or "unknown",
            description=str(
                payload.get("description", "")
            ).strip(),
            bbox=VisionBoundingBox(
                x1,
                y1,
                x2,
                y2,
            ),
            confidence=self._confidence(
                payload.get("confidence")
            ),
        )

    def _request(
        self,
        image_path: Path,
        prompt: str,
    ) -> str:
        image_b64 = base64.b64encode(
            image_path.read_bytes()
        ).decode("ascii")

        try:
            response = self._post(
                self.url,
                json={
                    "model": self.model,
                    "stream": False,
                    "format": "json",
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [image_b64],
                        }
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
            return str(
                body["message"]["content"]
            )

        except requests.ConnectionError as error:
            raise VisionAnalysisError(
                "Não consegui conectar ao Ollama."
            ) from error

        except requests.Timeout as error:
            raise VisionAnalysisError(
                "O modelo visual demorou mais do que o esperado."
            ) from error

        except requests.HTTPError as error:
            details = self._http_error_details(error)
            raise VisionAnalysisError(
                f"O Ollama recusou a análise visual: {details}"
            ) from error

        except (
            requests.RequestException,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise VisionAnalysisError(
                "O Ollama retornou uma resposta visual inválida."
            ) from error

    def _build_prompt(self, question: str) -> str:
        return (
            "Você é o módulo visual do Atlas. "
            "Analise somente o que pode ser observado na imagem. "
            "Não invente elementos invisíveis. "
            "Não execute ações no computador.\n\n"
            f"Pergunta do usuário: {question.strip()}\n\n"
            "Retorne APENAS JSON válido neste formato:\n"
            "{"
            '"summary":"descrição objetiva da tela",'
            '"visible_text":["textos relevantes visíveis"],'
            '"applications":["programas ou janelas reconhecíveis"],'
            '"errors":["erros ou alertas claramente visíveis"],'
            '"ui_elements":['
            '{"label":"nome",'
            '"kind":"button|field|menu|window|other",'
            '"description":"descrição curta",'
            '"bbox":[x1,y1,x2,y2],'
            '"confidence":0.0}'
            "],"
            '"confidence":0.0'
            "}\n"
            "bbox usa coordenadas normalizadas de 0 a 1000. "
            "Se a posição não for confiável, use bbox null."
        )

    @staticmethod
    def _extract_json_object(
        content: str,
    ) -> dict[str, Any]:
        raw = str(content).strip()

        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

        fenced = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if fenced:
            try:
                payload = json.loads(
                    fenced.group(1)
                )
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                pass

        start = raw.find("{")
        if start == -1:
            raise VisionAnalysisError(
                "O modelo visual não retornou JSON válido."
            )

        depth = 0
        in_string = False
        escaped = False

        for index in range(start, len(raw)):
            char = raw[index]

            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw[start:index + 1]
                    try:
                        payload = json.loads(candidate)
                    except json.JSONDecodeError:
                        break
                    if isinstance(payload, dict):
                        return payload
                    break

        raise VisionAnalysisError(
            "O modelo visual não retornou JSON válido."
        )

    def _parse_content(
        self,
        content: Any,
    ) -> VisionAnalysis:
        if not isinstance(content, str) or not content.strip():
            raise VisionAnalysisError(
                "O modelo visual retornou conteúdo vazio."
            )

        raw = content.strip()
        payload = self._extract_json_object(raw)

        summary = str(
            payload.get("summary", "")
        ).strip()

        if not summary:
            raise VisionAnalysisError(
                "O resultado visual não contém um resumo."
            )

        return VisionAnalysis(
            summary=summary,
            visible_text=self._string_tuple(
                payload.get("visible_text")
            ),
            applications=self._string_tuple(
                payload.get("applications")
            ),
            errors=self._string_tuple(
                payload.get("errors")
            ),
            ui_elements=tuple(
                self._parse_ui_element(item)
                for item in self._as_list(
                    payload.get("ui_elements")
                )
                if isinstance(item, dict)
            ),
            confidence=self._confidence(
                payload.get("confidence")
            ),
            model=self.model,
            raw_response=raw,
        )

    @staticmethod
    def _as_list(
        value: Any,
    ) -> list[Any]:
        return value if isinstance(value, list) else []

    @classmethod
    def _string_tuple(
        cls,
        value: Any,
    ) -> tuple[str, ...]:
        return tuple(
            text
            for item in cls._as_list(value)
            if (text := str(item).strip())
        )

    @classmethod
    def _parse_ui_element(
        cls,
        item: dict[str, Any],
    ) -> VisionUIElement:
        return VisionUIElement(
            label=str(
                item.get("label", "")
            ).strip(),
            kind=str(
                item.get("kind", "unknown")
            ).strip() or "unknown",
            description=str(
                item.get("description", "")
            ).strip(),
            bbox=cls._parse_bbox(
                item.get("bbox")
            ),
            confidence=cls._confidence(
                item.get("confidence")
            ),
        )

    @classmethod
    def _parse_point(
        cls,
        value: Any,
    ) -> tuple[int, int] | None:
        if value is None:
            return None

        raw = value

        if isinstance(raw, dict):
            if "x" in raw and "y" in raw:
                raw = [raw["x"], raw["y"]]
            else:
                return None

        if isinstance(raw, str):
            stripped = raw.strip().strip("[]()")
            parts = [
                part.strip()
                for part in stripped.split(",")
                if part.strip()
            ]
            if len(parts) == 2:
                raw = parts

        if not isinstance(raw, list) or len(raw) != 2:
            return None

        try:
            values = [
                float(item)
                for item in raw
            ]
        except (
            TypeError,
            ValueError,
        ):
            return None

        max_value = max(values)

        if max_value <= 1.0:
            values = [
                item * 1000
                for item in values
            ]
        elif max_value <= 100.0:
            values = [
                item * 10
                for item in values
            ]

        x, y = (
            int(round(item))
            for item in values
        )

        if not (
            0 <= x <= 1000
            and 0 <= y <= 1000
        ):
            return None

        return x, y

    @staticmethod
    def _parse_bbox(
        value: Any,
    ) -> VisionBoundingBox | None:
        if value is None:
            return None

        raw = value

        if isinstance(raw, dict):
            if all(
                key in raw
                for key in (
                    "x1",
                    "y1",
                    "x2",
                    "y2",
                )
            ):
                raw = [
                    raw["x1"],
                    raw["y1"],
                    raw["x2"],
                    raw["y2"],
                ]
            elif all(
                key in raw
                for key in (
                    "x",
                    "y",
                    "w",
                    "h",
                )
            ):
                try:
                    x = float(raw["x"])
                    y = float(raw["y"])
                    w = float(raw["w"])
                    h = float(raw["h"])
                except (
                    TypeError,
                    ValueError,
                ):
                    return None

                raw = [
                    x,
                    y,
                    x + w,
                    y + h,
                ]

        if isinstance(raw, str):
            stripped = raw.strip().strip(
                "[]()"
            )
            parts = [
                part.strip()
                for part in stripped.split(",")
                if part.strip()
            ]
            if len(parts) == 4:
                raw = parts

        if not isinstance(raw, list) or len(raw) != 4:
            return None

        try:
            values = [
                float(item)
                for item in raw
            ]
        except (
            TypeError,
            ValueError,
        ):
            return None

        max_value = max(values)

        if max_value <= 1.0:
            values = [
                item * 1000
                for item in values
            ]
        elif max_value <= 100.0:
            values = [
                item * 10
                for item in values
            ]

        try:
            x1, y1, x2, y2 = (
                int(round(item))
                for item in values
            )
            return VisionBoundingBox(
                x1,
                y1,
                x2,
                y2,
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _confidence(
        value: Any,
    ) -> float:
        try:
            confidence = float(value)
        except (
            TypeError,
            ValueError,
        ):
            return 0.0

        return max(
            0.0,
            min(confidence, 1.0),
        )

    @staticmethod
    def _http_error_details(
        error: requests.HTTPError,
    ) -> str:
        response = error.response

        if response is None:
            return str(error)

        try:
            payload = response.json()
        except ValueError:
            return (
                response.text.strip()
                or str(error)
            )

        if isinstance(payload, dict):
            return str(
                payload.get("error")
                or payload
            )

        return str(payload)
