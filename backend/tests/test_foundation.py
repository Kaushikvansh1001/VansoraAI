import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models.enums import DocumentStatus
from app.models.knowledge import Document

pytestmark = pytest.mark.db


def register_and_verify(client, email: str, name: str = "Ava Shah") -> dict:
    created = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "full_name": name},
    )
    assert created.status_code == 201, created.text
    token = created.json()["dev_verification_token"]
    verified = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verified.status_code == 200, verified.text
    return verified.json()


def auth_header(access_token: str, organization_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {access_token}"}
    if organization_id:
        headers["X-Organization-Id"] = organization_id
    return headers


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["auth_mode"] == "local"


def test_login_requires_verification_and_then_succeeds(client):
    created = client.post(
        "/api/v1/auth/register",
        json={"email": "ava@example.com", "password": "password123", "full_name": "Ava Shah"},
    )
    assert created.status_code == 201
    blocked = client.post("/api/v1/auth/login", json={"email": "ava@example.com", "password": "password123"})
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "email_not_verified"

    verified = client.post("/api/v1/auth/verify-email", json={"token": created.json()["dev_verification_token"]})
    assert verified.status_code == 200
    me = client.get("/api/v1/auth/me", headers=auth_header(verified.json()["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "ava@example.com"
    assert me.json()["email_verified"] is True


def test_duplicate_email_and_bad_password(client):
    register_and_verify(client, "ava@example.com")
    again = client.post(
        "/api/v1/auth/register",
        json={"email": "ava@example.com", "password": "password123", "full_name": "Ava Shah"},
    )
    assert again.status_code == 409
    wrong = client.post("/api/v1/auth/login", json={"email": "ava@example.com", "password": "wrong-password"})
    assert wrong.status_code == 401


def test_password_reset(client):
    register_and_verify(client, "ava@example.com")
    forgot = client.post("/api/v1/auth/forgot-password", json={"email": "ava@example.com"})
    assert forgot.status_code == 200
    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": forgot.json()["dev_token"], "password": "new-password-1"},
    )
    assert reset.status_code == 200
    login = client.post("/api/v1/auth/login", json={"email": "ava@example.com", "password": "new-password-1"})
    assert login.status_code == 200
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "missing@example.com"})
    assert unknown.status_code == 200
    assert unknown.json()["dev_token"] is None


def test_organizations_are_isolated(client):
    ava = register_and_verify(client, "ava@example.com", "Ava Shah")
    ben = register_and_verify(client, "ben@example.com", "Ben Rao")

    ava_org = client.post(
        "/api/v1/organizations",
        headers=auth_header(ava["access_token"]),
        json={"name": "Northwind"},
    )
    assert ava_org.status_code == 201, ava_org.text
    org_id = ava_org.json()["id"]
    assert ava_org.json()["role"] == "org_admin"

    foreign = client.get(f"/api/v1/organizations/{org_id}", headers=auth_header(ben["access_token"]))
    assert foreign.status_code == 403

    dashboard = client.get("/api/v1/dashboard", headers=auth_header(ben["access_token"], org_id))
    assert dashboard.status_code == 403

    own = client.get("/api/v1/dashboard", headers=auth_header(ava["access_token"], org_id))
    assert own.status_code == 200
    assert own.json()["documents"] == 0
    assert own.json()["queries"] == 0
    assert own.json()["estimated_cost_usd"] == "0.000000"


def test_member_cannot_rename_organization_and_last_admin_stays(client):
    admin = register_and_verify(client, "admin@example.com", "Admin User")
    member = register_and_verify(client, "member@example.com", "Member User")
    created = client.post(
        "/api/v1/organizations",
        headers=auth_header(admin["access_token"]),
        json={"name": "Contoso"},
    )
    org_id = created.json()["id"]

    added = client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=auth_header(admin["access_token"]),
        json={"email": "member@example.com", "role": "member"},
    )
    assert added.status_code == 201, added.text

    rename = client.patch(
        f"/api/v1/organizations/{org_id}",
        headers=auth_header(member["access_token"]),
        json={"name": "Taken"},
    )
    assert rename.status_code == 403

    members = client.get(
        f"/api/v1/organizations/{org_id}/members",
        headers=auth_header(admin["access_token"]),
    )
    admin_member = next(row for row in members.json() if row["email"] == "admin@example.com")
    remove_admin = client.delete(
        f"/api/v1/organizations/{org_id}/members/{admin_member['id']}",
        headers=auth_header(admin["access_token"]),
    )
    assert remove_admin.status_code == 409
    assert remove_admin.json()["error"]["code"] == "last_admin"


def test_dashboard_counts_come_from_the_database(client):
    ava = register_and_verify(client, "ava@example.com")
    created = client.post(
        "/api/v1/organizations",
        headers=auth_header(ava["access_token"]),
        json={"name": "Northwind"},
    )
    org_id = uuid.UUID(created.json()["id"])
    user_id = uuid.UUID(ava["user"]["id"])

    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        session.add(
            Document(
                organization_id=org_id,
                uploaded_by=user_id,
                filename="handbook.pdf",
                storage_path="northwind/handbook.pdf",
                mime_type="application/pdf",
                size_bytes=1200,
                status=DocumentStatus.ready,
                page_count=3,
            )
        )
        session.commit()
    engine.dispose()

    dashboard = client.get("/api/v1/dashboard", headers=auth_header(ava["access_token"], str(org_id)))
    assert dashboard.status_code == 200, dashboard.text
    body = dashboard.json()
    assert body["documents"] == 1
    assert body["document_status"]["ready"] == 1
    assert body["document_status"]["pending"] == 0
    assert body["recent_activity"][0]["action"] == "organization.create"

    ben = register_and_verify(client, "ben@example.com", "Ben Rao")
    other = client.post(
        "/api/v1/organizations",
        headers=auth_header(ben["access_token"]),
        json={"name": "Fabrikam"},
    )
    other_dashboard = client.get(
        "/api/v1/dashboard",
        headers=auth_header(ben["access_token"], other.json()["id"]),
    )
    assert other_dashboard.json()["documents"] == 0


def test_row_level_security_is_enabled():
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT relname FROM pg_class WHERE relrowsecurity AND relkind = 'r'")
        ).scalars()
        protected = set(rows)
    engine.dispose()
    assert {"documents", "organizations", "profiles", "ai_usage_logs"} <= protected
