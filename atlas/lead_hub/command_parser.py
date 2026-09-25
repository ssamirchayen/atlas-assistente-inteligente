from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeadHubCommand:
    is_lead_hub_command: bool
    source: str = "internet"
    channel: str = "web"
    auto_triage: bool = True
    prepare_contact: bool = True
    confirm_contact: bool = False
    limit: int = 10


_SOURCE_WORDS = {
    "instagram": ("instagram", "insta"),
    "facebook": ("facebook", "face", "meta"),
    "whatsapp": ("whatsapp", "zap", "wpp"),
    "sunchat": ("sunchat", "sun chat"),
    "site": ("site", "formulario", "formulário", "landing page"),
    "internet": ("internet", "redes", "rede social", "online"),
}


def parse_lead_hub_command(text: str) -> LeadHubCommand:
    normalized = _normalize(text)
    lead_terms = ("lead", "leads", "contato", "contatos", "cliente", "clientes")
    action_terms = (
        "puxe",
        "puxar",
        "captar",
        "capture",
        "capturar",
        "buscar",
        "importe",
        "importar",
        "jogue",
        "jogar",
        "organize",
        "organizar",
    )

    if not any(term in normalized for term in lead_terms):
        return LeadHubCommand(False)
    if not any(term in normalized for term in action_terms):
        return LeadHubCommand(False)

    source = "internet"
    channel = "web"
    for candidate, words in _SOURCE_WORDS.items():
        if any(word in normalized for word in words):
            source = candidate
            channel = candidate if candidate not in {"internet"} else "web"
            break

    confirm_contact = any(
        term in normalized
        for term in (
            "pode enviar",
            "envie agora",
            "enviar agora",
            "entra em contato agora",
            "contato agora",
            "confirmado",
            "confirmo",
        )
    )

    prepare_contact = any(
        term in normalized
        for term in (
            "contato",
            "mensagem",
            "responder",
            "resposta",
            "atendimento",
            "whatsapp",
            "sunchat",
            "zap",
        )
    )

    limit = _extract_limit(normalized) or 10

    return LeadHubCommand(
        is_lead_hub_command=True,
        source=source,
        channel=channel,
        auto_triage=True,
        prepare_contact=prepare_contact,
        confirm_contact=confirm_contact,
        limit=limit,
    )


def _normalize(text: str) -> str:
    lowered = text.strip().lower()
    replacements = {
        "á": "a",
        "à": "a",
        "ã": "a",
        "â": "a",
        "é": "e",
        "ê": "e",
        "í": "i",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
        "ç": "c",
    }
    for old, new in replacements.items():
        lowered = lowered.replace(old, new)
    return lowered


def _extract_limit(text: str) -> int | None:
    tokens = text.replace(",", " ").replace(".", " ").split()
    for index, token in enumerate(tokens):
        if token.isdigit():
            value = int(token)
            if 1 <= value <= 100:
                return value
        if token in {"primeiros", "primeiras", "ultimos", "ultimas"} and index + 1 < len(tokens):
            nxt = tokens[index + 1]
            if nxt.isdigit():
                value = int(nxt)
                if 1 <= value <= 100:
                    return value
    return None
