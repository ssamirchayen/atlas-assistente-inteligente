# Atlas Integration Framework — Business Lab API Driver

Conecta o primeiro sistema empresarial ao framework genérico do Atlas.

## Ações suportadas via API

- health
- authenticate
- whoami
- dashboard
- list_leads
- get_lead
- update_lead_status
- list_interactions
- create_interaction
- list_followups
- create_followup
- complete_followup
- list_courses
- get_course
- list_offers
- list_enrollments
- get_enrollment
- create_enrollment
- update_enrollment
- get_reports

Nenhuma ação de gabarito/cenário oficial é exposta no driver.

## Configuração no Atlas

Adicione ao `.env` PRIVADO do Atlas:

```env
ATLAS_BUSINESS_LAB_URL=http://127.0.0.1:5055
ATLAS_BUSINESS_LAB_EMAIL=consultor@nexyra.lab
ATLAS_BUSINESS_LAB_PASSWORD=Consultor123!
```

Não publique o `.env`.

## Testes unitários

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_business_lab_api_driver.py
.\.venv\Scripts\python.exe -m pytest -q tests\test_business_lab_connector.py
.\.venv\Scripts\python.exe -m ruff check .
```

## Primeiro teste real — LAB-001

Com o Business Lab rodando:

```powershell
.\.venv\Scripts\python.exe tools\run_business_lab_lab001.py
```

O script não contém o gabarito do cenário. Ele apenas pede ao
IntegrationManager:

`business_lab -> get_lead -> SIM-00001`

O resultado deve ser obtido pelo API Driver.
