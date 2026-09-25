from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atlas.lead_hub.client import LeadHubClient
from atlas.lead_hub.command_parser import parse_lead_hub_command
from atlas.lead_hub.models import LeadCaptureRequest, LeadRecord


@dataclass(frozen=True)
class LeadHubRunResult:
    ok: bool
    message: str
    payload: dict[str, Any]


class LeadHubService:
    def __init__(self, client: LeadHubClient | None = None) -> None:
        self.client = client or LeadHubClient()

    def run_from_command(self, command_text: str, demo: bool = False) -> LeadHubRunResult:
        command = parse_lead_hub_command(command_text)
        if not command.is_lead_hub_command:
            return LeadHubRunResult(False, "Comando não reconhecido como captação de leads.", {})

        leads = tuple(_demo_leads(command.limit, command.source, command.channel)) if demo else ()
        request = LeadCaptureRequest(
            source=command.source,
            channel=command.channel,
            campaign="atlas_command",
            leads=leads,
            auto_triage=command.auto_triage,
            prepare_contact=command.prepare_contact,
            confirm_contact=command.confirm_contact,
        )

        response = self.client.pull(request)
        if not response.get("ok"):
            return LeadHubRunResult(
                False,
                "Não consegui conectar ao Nexyra Lead Hub. Verifique se o Business Lab está aberto.",
                response,
            )

        processed = response.get("processed_count", response.get("count", 0))
        ready = response.get("contact_ready_count", 0)
        return LeadHubRunResult(
            True,
            f"Leads captados e organizados: {processed}. Contatos preparados: {ready}.",
            response,
        )


def _demo_leads(limit: int, source: str, channel: str) -> list[LeadRecord]:
    seed = [
        ("Mariana Lopes", "92988001101", "mariana.leads@nexyra.demo", "Radiologia", "Quero saber turma e valor."),
        ("Rafael Costa", "92988001102", "rafael.leads@nexyra.demo", "Enfermagem", "Vi o anúncio e quero matrícula."),
        ("Ana Beatriz", "92988001103", "ana.leads@nexyra.demo", "Eletrotécnica", "Tenho interesse para começar esse mês."),
        ("Lucas Pereira", "92988001104", "lucas.leads@nexyra.demo", "Administração", "Quero valores e horários."),
        ("Bianca Souza", "92988001105", "bianca.leads@nexyra.demo", "Radiologia", "Preciso de informações pelo WhatsApp."),
    ]
    records = []
    for name, phone, email, interest, message in seed[: max(1, min(limit, len(seed)))]:
        records.append(
            LeadRecord(
                name=name,
                phone=phone,
                email=email,
                interest=interest,
                source=source,
                channel=channel,
                campaign="demo_atlas_lead_hub",
                message=message,
                consent=True,
                metadata={"demo": True, "captured_by": "atlas"},
            )
        )
    return records
