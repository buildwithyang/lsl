from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from lsl.core.config import Settings
from lsl.core.db import Base
from lsl.core.session import CookieSessionMiddleware
from lsl.modules.auth.api import require_auth_user
from lsl.modules.auth.repo import UserRepository
from lsl.modules.auth.schema import AuthUser
from lsl.modules.auth.service import AuthService


class _AuthServiceStub:
    def __init__(self, user: AuthUser | None) -> None:
        self._user = user

    def get_current_user(self, session: dict[str, Any]) -> AuthUser | None:
        return self._user


def _build_repository() -> UserRepository:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=OrmSession)
    return UserRepository(factory)


def test_auth_service_builds_authorization_url_with_state_and_pkce() -> None:
    service = AuthService(
        settings=Settings(
            CASDOOR_ENDPOINT="http://localhost:18000",
            CASDOOR_CLIENT_ID="client-id",
            CASDOOR_CLIENT_SECRET="client-secret",
            CASDOOR_REDIRECT_URI="http://localhost:8000/auth/callback",
        ),
        repository=None,
    )
    session: dict = {}

    url = service.build_authorization_url(session)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.geturl().startswith("http://localhost:18000/login/oauth/authorize")
    assert query["client_id"] == ["client-id"]
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == ["http://localhost:8000/auth/callback"]
    assert query["scope"] == ["openid profile email"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"] == [session[AuthService.STATE_KEY]]
    assert session[AuthService.NONCE_KEY]
    assert session[AuthService.CODE_VERIFIER_KEY]


def test_user_repository_upserts_oauth_user() -> None:
    repository = _build_repository()

    first = repository.upsert_oauth_user(
        provider="casdoor",
        provider_subject="lsl/user-1",
        username="user-1",
        display_name="User One",
        email="one@example.com",
        avatar_url=None,
    )
    second = repository.upsert_oauth_user(
        provider="casdoor",
        provider_subject="lsl/user-1",
        username="user-1",
        display_name="Updated User",
        email="updated@example.com",
        avatar_url="https://example.com/avatar.png",
    )

    assert second.user_id == first.user_id
    assert second.display_name == "Updated User"
    assert second.email == "updated@example.com"
    assert second.avatar_url == "https://example.com/avatar.png"


def test_require_auth_user_rejects_missing_user() -> None:
    app = FastAPI()
    app.state.auth_service = _AuthServiceStub(None)
    app.add_middleware(CookieSessionMiddleware, secret_key="test-secret")

    @app.get("/protected")
    def protected(_user: AuthUser = Depends(require_auth_user)):
        return {"ok": True}

    response = TestClient(app).get("/protected")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_require_auth_user_allows_current_user() -> None:
    now = datetime.now(timezone.utc)
    user = AuthUser(
        user_id="user-1",
        provider="casdoor",
        provider_subject="lsl/user-1",
        username="user-1",
        display_name="User One",
        email="one@example.com",
        avatar_url=None,
        created_at=now,
        updated_at=now,
    )
    app = FastAPI()
    app.state.auth_service = _AuthServiceStub(user)
    app.add_middleware(CookieSessionMiddleware, secret_key="test-secret")

    @app.get("/protected")
    def protected(current_user: AuthUser = Depends(require_auth_user)):
        return {"user_id": current_user.user_id}

    response = TestClient(app).get("/protected")

    assert response.status_code == 200
    assert response.json() == {"user_id": "user-1"}
