"""Autenticação local e autorização por escopos."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from secrets import compare_digest
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from atlas.core.config import API_ADMIN_KEY, API_READ_KEY

STATUS_READ = "status:read"
COMMANDS_EXECUTE = "commands:execute"
WORKFLOWS_READ = "workflows:read"
WORKFLOWS_CANCEL = "workflows:cancel"
AUDIT_READ = "audit:read"
SESSIONS_READ = "sessions:read"
WORKFLOWS_RESUME = "workflows:resume"

ADMIN_SCOPES = frozenset(
    {
        STATUS_READ,
        COMMANDS_EXECUTE,
        WORKFLOWS_READ,
        WORKFLOWS_CANCEL,
        AUDIT_READ,
        SESSIONS_READ,
        WORKFLOWS_RESUME,
    }
)
READ_SCOPES = frozenset({STATUS_READ})
MIN_API_KEY_LENGTH = 32

_API_KEY_HEADER = APIKeyHeader(
    name="X-API-Key",
    scheme_name="AtlasApiKey",
    description="Chave local configurada no arquivo .env do Atlas.",
    auto_error=False,
)


@dataclass(frozen=True, slots=True)
class ApiPrincipal:
    """Identidade associada a uma credencial válida."""

    principal_id: str
    role: str
    scopes: frozenset[str]

    def allows(self, scope: str) -> bool:
        return scope in self.scopes


@dataclass(frozen=True, slots=True, repr=False)
class ApiCredential:
    """Liga uma chave secreta a uma identidade e nunca exibe o segredo."""

    key: str
    principal: ApiPrincipal


class AuthenticationNotConfiguredError(RuntimeError):
    """Indica que nenhum segredo de API foi configurado."""


AuthenticationObserver = Callable[
    [str, str, ApiPrincipal | None, bool, int],
    None,
]


class ApiKeyAuthenticator:
    """Valida chaves em tempo constante e retorna identidades com escopos."""

    def __init__(self, credentials: Iterable[ApiCredential] = ()) -> None:
        self._credentials = tuple(credentials)
        self._validate_credentials()

    @classmethod
    def from_keys(
        cls,
        *,
        admin_key: str = "",
        read_key: str = "",
    ) -> ApiKeyAuthenticator:
        credentials: list[ApiCredential] = []

        if admin_key:
            credentials.append(
                ApiCredential(
                    key=admin_key,
                    principal=ApiPrincipal(
                        principal_id="local-admin",
                        role="admin",
                        scopes=ADMIN_SCOPES,
                    ),
                )
            )

        if read_key:
            credentials.append(
                ApiCredential(
                    key=read_key,
                    principal=ApiPrincipal(
                        principal_id="local-monitor",
                        role="monitor",
                        scopes=READ_SCOPES,
                    ),
                )
            )

        return cls(credentials)

    @classmethod
    def from_environment(cls) -> ApiKeyAuthenticator:
        return cls.from_keys(
            admin_key=API_ADMIN_KEY,
            read_key=API_READ_KEY,
        )

    @property
    def configured(self) -> bool:
        return bool(self._credentials)

    def authenticate(self, provided_key: str | None) -> ApiPrincipal | None:
        if not self.configured:
            raise AuthenticationNotConfiguredError

        if not provided_key:
            return None

        matched: ApiPrincipal | None = None

        for credential in self._credentials:
            if compare_digest(provided_key, credential.key):
                matched = credential.principal

        return matched

    def _validate_credentials(self) -> None:
        keys: set[str] = set()

        for credential in self._credentials:
            if len(credential.key) < MIN_API_KEY_LENGTH:
                raise ValueError(
                    "A chave da API deve possuir pelo menos "
                    f"{MIN_API_KEY_LENGTH} caracteres."
                )

            if credential.key in keys:
                raise ValueError("As chaves da API devem ser diferentes.")

            keys.add(credential.key)


AuthenticationDependency = Callable[..., ApiPrincipal]


def create_authentication_dependency(
    authenticator: ApiKeyAuthenticator,
    observer: AuthenticationObserver | None = None,
) -> AuthenticationDependency:
    """Cria uma dependência vinculada ao autenticador da aplicação."""

    def authenticate(
        request: Request,
        api_key: str | None = Security(_API_KEY_HEADER),
    ) -> ApiPrincipal:
        try:
            principal = authenticator.authenticate(api_key)
        except AuthenticationNotConfiguredError as error:
            if observer is not None:
                observer(
                    "authentication.unavailable",
                    request.url.path,
                    None,
                    bool(api_key),
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "A autenticação da API não foi configurada. "
                    "Defina ATLAS_API_KEY no arquivo .env."
                ),
            ) from error

        if principal is None:
            if observer is not None:
                observer(
                    "authentication.rejected",
                    request.url.path,
                    None,
                    bool(api_key),
                    status.HTTP_401_UNAUTHORIZED,
                )

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Chave da API ausente ou inválida.",
                headers={"WWW-Authenticate": "APIKey"},
            )

        if observer is not None:
            observer(
                "authentication.succeeded",
                request.url.path,
                principal,
                True,
                status.HTTP_200_OK,
            )

        return principal

    return authenticate


def create_scope_dependency(
    authenticate: AuthenticationDependency,
    required_scope: str,
) -> AuthenticationDependency:
    """Exige autenticação e uma permissão específica."""

    def require_scope(
        principal: ApiPrincipal = Depends(authenticate),
    ) -> ApiPrincipal:
        if not principal.allows(required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permissão necessária: {required_scope}.",
            )

        return principal

    return require_scope
