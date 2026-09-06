from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..base import DriverKind, IntegrationDriver, IntegrationResult


class BusinessLabApiDriver(IntegrationDriver):
    kind = DriverKind.API
    priority = 10

    SUPPORTED_ACTIONS = {
        "health",
        "authenticate",
        "whoami",
        "dashboard",
        "list_leads",
        "get_lead",
        "update_lead_status",
        "list_interactions",
        "list_recent_interactions",
        "create_interaction",
        "list_followups",
        "list_all_followups",
        "create_followup",
        "complete_followup",
        "list_courses",
        "get_course",
        "list_offers",
        "list_enrollments",
        "get_enrollment",
        "create_enrollment",
        "update_enrollment",
        "get_reports",
    }

    def __init__(
        self,
        base_url: str,
        *,
        email: str | None = None,
        password: str | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.timeout_seconds = timeout_seconds
        self._token: str | None = None

    def supports(self, action: str) -> bool:
        return action in self.SUPPORTED_ACTIONS

    def is_available(self) -> bool:
        return self._health().ok

    def execute(
        self,
        action: str,
        **kwargs: Any,
    ) -> IntegrationResult:
        if action not in self.SUPPORTED_ACTIONS:
            return self._failure(
                action,
                "Ação não suportada pelo API Driver.",
            )

        if action == "health":
            return self._health()

        if action == "authenticate":
            return self._authenticate(
                email=kwargs.get("email"),
                password=kwargs.get("password"),
            )

        if action == "whoami":
            return self._protected_request(
                action,
                "GET",
                "/api/v1/auth/me",
            )

        if action == "dashboard":
            return self._protected_request(
                action,
                "GET",
                "/api/v1/dashboard",
            )

        if action == "list_leads":
            return self._protected_request(
                action,
                "GET",
                "/api/v1/leads",
                query={
                    "q": kwargs.get("query"),
                    "status": kwargs.get("status"),
                    "priority": kwargs.get("priority"),
                    "course_id": kwargs.get("course_id"),
                    "assigned_user_id": kwargs.get(
                        "assigned_user_id"
                    ),
                    "limit": kwargs.get("limit"),
                },
            )

        if action == "get_lead":
            code = self._required(
                kwargs,
                "code",
                action,
            )
            if isinstance(code, IntegrationResult):
                return code
            return self._protected_request(
                action,
                "GET",
                f"/api/v1/leads/{code}",
            )

        if action == "update_lead_status":
            code = self._required(
                kwargs,
                "code",
                action,
            )
            status = self._required(
                kwargs,
                "status",
                action,
            )
            if isinstance(code, IntegrationResult):
                return code
            if isinstance(status, IntegrationResult):
                return status
            return self._protected_request(
                action,
                "PATCH",
                f"/api/v1/leads/{code}/status",
                payload={"status": status},
            )

        if action == "list_interactions":
            code = self._required(
                kwargs,
                "code",
                action,
            )
            if isinstance(code, IntegrationResult):
                return code
            return self._protected_request(
                action,
                "GET",
                f"/api/v1/leads/{code}/atendimentos",
                query={"limit": kwargs.get("limit")},
            )

        if action == "list_recent_interactions":
            return self._protected_request(
                action,
                "GET",
                "/api/v1/atendimentos",
                query={"limit": kwargs.get("limit")},
            )

        if action == "create_interaction":
            code = self._required(
                kwargs,
                "code",
                action,
            )
            if isinstance(code, IntegrationResult):
                return code

            payload = {
                "channel": kwargs.get("channel"),
                "kind": kwargs.get("kind"),
                "direction": kwargs.get("direction"),
                "outcome": kwargs.get("outcome", ""),
                "content": kwargs.get("content"),
            }
            return self._protected_request(
                action,
                "POST",
                f"/api/v1/leads/{code}/atendimentos",
                payload=payload,
            )

        if action == "list_followups":
            code = self._required(
                kwargs,
                "code",
                action,
            )
            if isinstance(code, IntegrationResult):
                return code
            return self._protected_request(
                action,
                "GET",
                f"/api/v1/leads/{code}/retornos",
            )

        if action == "list_all_followups":
            return self._protected_request(
                action,
                "GET",
                "/api/v1/retornos",
                query={
                    "status": kwargs.get("status"),
                    "priority": kwargs.get("priority"),
                    "due_filter": kwargs.get("due_filter"),
                    "assigned_user_id": kwargs.get("assigned_user_id"),
                    "limit": kwargs.get("limit"),
                },
            )

        if action == "create_followup":
            code = self._required(
                kwargs,
                "code",
                action,
            )
            if isinstance(code, IntegrationResult):
                return code

            payload = {
                "title": kwargs.get("title"),
                "notes": kwargs.get("notes", ""),
                "priority": kwargs.get("priority"),
                "due_at": kwargs.get("due_at"),
            }
            return self._protected_request(
                action,
                "POST",
                f"/api/v1/leads/{code}/retornos",
                payload=payload,
            )

        if action == "complete_followup":
            followup_id = self._required(
                kwargs,
                "followup_id",
                action,
            )
            if isinstance(
                followup_id,
                IntegrationResult,
            ):
                return followup_id
            return self._protected_request(
                action,
                "POST",
                f"/api/v1/retornos/{followup_id}/concluir",
            )

        if action == "list_courses":
            return self._protected_request(
                action,
                "GET",
                "/api/v1/cursos",
            )

        if action == "get_course":
            course_id = self._required(
                kwargs,
                "course_id",
                action,
            )
            if isinstance(course_id, IntegrationResult):
                return course_id
            return self._protected_request(
                action,
                "GET",
                f"/api/v1/cursos/{course_id}",
            )

        if action == "list_offers":
            return self._protected_request(
                action,
                "GET",
                "/api/v1/ofertas",
                query={
                    "course_id": kwargs.get("course_id"),
                },
            )

        if action == "list_enrollments":
            return self._protected_request(
                action,
                "GET",
                "/api/v1/matriculas",
                query={
                    "status": kwargs.get("status"),
                    "payment_status": kwargs.get(
                        "payment_status"
                    ),
                    "course_id": kwargs.get("course_id"),
                    "limit": kwargs.get("limit"),
                },
            )

        if action == "get_enrollment":
            code = self._required(
                kwargs,
                "code",
                action,
            )
            if isinstance(code, IntegrationResult):
                return code
            return self._protected_request(
                action,
                "GET",
                f"/api/v1/matriculas/{code}",
            )

        if action == "create_enrollment":
            code = self._required(
                kwargs,
                "code",
                action,
            )
            if isinstance(code, IntegrationResult):
                return code
            return self._protected_request(
                action,
                "POST",
                f"/api/v1/leads/{code}/matricula",
            )

        if action == "update_enrollment":
            code = self._required(
                kwargs,
                "code",
                action,
            )
            if isinstance(code, IntegrationResult):
                return code

            return self._protected_request(
                action,
                "PATCH",
                f"/api/v1/matriculas/{code}",
                payload={
                    "status": kwargs.get("status"),
                    "payment_status": kwargs.get(
                        "payment_status"
                    ),
                },
            )

        return self._protected_request(
            action,
            "GET",
            "/api/v1/relatorios",
            query={
                "course_id": kwargs.get("course_id"),
            },
        )

    def _health(self) -> IntegrationResult:
        result = self._request(
            "health",
            "GET",
            "/health",
            authenticated=False,
        )
        if not result.ok:
            return result

        payload = result.data or {}
        if payload.get("status") != "ok":
            return self._failure(
                "health",
                "Health retornou status inválido.",
            )

        return result

    def _authenticate(
        self,
        *,
        email: Any = None,
        password: Any = None,
    ) -> IntegrationResult:
        selected_email = str(
            email or self.email or ""
        ).strip()
        selected_password = str(
            password or self.password or ""
        )

        if not selected_email or not selected_password:
            return self._failure(
                "authenticate",
                (
                    "Credenciais do Business Lab não configuradas. "
                    "Defina ATLAS_BUSINESS_LAB_EMAIL e "
                    "ATLAS_BUSINESS_LAB_PASSWORD."
                ),
            )

        result = self._request(
            "authenticate",
            "POST",
            "/api/v1/auth/login",
            payload={
                "email": selected_email,
                "password": selected_password,
            },
            authenticated=False,
        )

        if result.ok:
            data = result.data or {}
            token = data.get("token")
            if not isinstance(token, str) or not token:
                return self._failure(
                    "authenticate",
                    "A API não retornou um Bearer token.",
                )
            self._token = token

        return result

    def _protected_request(
        self,
        action: str,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> IntegrationResult:
        if self._token is None:
            auth = self._authenticate()
            if not auth.ok:
                return IntegrationResult(
                    ok=False,
                    action=action,
                    driver=self.kind,
                    error=auth.error,
                    metadata={
                        "authentication_failed": True,
                    },
                )

        result = self._request(
            action,
            method,
            path,
            payload=payload,
            query=query,
            authenticated=True,
        )

        if (
            not result.ok
            and result.metadata.get("http_status") == 401
        ):
            self._token = None
            auth = self._authenticate()
            if not auth.ok:
                return result

            result = self._request(
                action,
                method,
                path,
                payload=payload,
                query=query,
                authenticated=True,
            )

        return result

    def _request(
        self,
        action: str,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        authenticated: bool,
    ) -> IntegrationResult:
        url = f"{self.base_url}{path}"

        clean_query = {
            key: value
            for key, value in (query or {}).items()
            if value is not None and value != ""
        }
        if clean_query:
            url = f"{url}?{urlencode(clean_query)}"

        body = None
        headers = {
            "Accept": "application/json",
            "User-Agent": (
                "Atlas-Integration-Framework/1.0"
            ),
        }

        if payload is not None:
            body = json.dumps(
                payload,
                ensure_ascii=False,
            ).encode("utf-8")
            headers["Content-Type"] = "application/json"

        if authenticated and self._token:
            headers["Authorization"] = (
                f"Bearer {self._token}"
            )

        request = Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                raw = response.read().decode("utf-8")
                decoded = json.loads(raw)
        except HTTPError as error:
            return self._http_error(
                action,
                error,
            )
        except URLError as error:
            return self._failure(
                action,
                str(error.reason),
            )
        except (TimeoutError, json.JSONDecodeError) as error:
            return self._failure(
                action,
                str(error),
            )

        if path == "/health":
            return IntegrationResult(
                ok=True,
                action=action,
                driver=self.kind,
                data=decoded,
                metadata={
                    "method": method,
                    "url": url,
                },
            )

        if not decoded.get("ok"):
            error = decoded.get("error") or {}
            return self._failure(
                action,
                str(
                    error.get(
                        "message",
                        "A API retornou falha.",
                    )
                ),
                metadata={
                    "api_error_code": error.get("code"),
                    "method": method,
                    "url": url,
                },
            )

        return IntegrationResult(
            ok=True,
            action=action,
            driver=self.kind,
            data=decoded.get("data"),
            metadata={
                "api_meta": decoded.get("meta"),
                "method": method,
                "url": url,
            },
        )

    def _http_error(
        self,
        action: str,
        error: HTTPError,
    ) -> IntegrationResult:
        message = f"HTTP {error.code}"
        api_code = None

        try:
            payload = json.loads(
                error.read().decode("utf-8")
            )
            api_error = payload.get("error") or {}
            api_code = api_error.get("code")
            message = str(
                api_error.get("message") or message
            )
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass

        return self._failure(
            action,
            message,
            metadata={
                "http_status": error.code,
                "api_error_code": api_code,
            },
        )

    def _failure(
        self,
        action: str,
        error: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> IntegrationResult:
        return IntegrationResult(
            ok=False,
            action=action,
            driver=self.kind,
            error=error,
            metadata=metadata or {},
        )

    def _required(
        self,
        kwargs: dict[str, Any],
        key: str,
        action: str,
    ) -> Any | IntegrationResult:
        value = kwargs.get(key)
        if value is None:
            return self._failure(
                action,
                f"Argumento obrigatório ausente: {key}.",
            )
        if isinstance(value, str) and not value.strip():
            return self._failure(
                action,
                f"Argumento obrigatório vazio: {key}.",
            )
        return value
