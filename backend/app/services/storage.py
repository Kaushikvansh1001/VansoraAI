import uuid
from pathlib import PurePath
from urllib.parse import quote

import httpx

from app.core.config import get_settings
from app.core.errors import AppError


def build_object_path(organization_id: uuid.UUID, document_id: uuid.UUID, filename: str) -> str:
    """Storage key owned by Supabase. The filename cannot carry a directory or a drive."""
    name = PurePath(filename.replace("\\", "/")).name
    if name in {"", ".", ".."}:
        raise AppError("invalid_filename", "The file name is not valid.", 400)
    return f"{organization_id}/{document_id}/{name}"


class SupabaseStorage:
    """Server-side access to a private Storage bucket. The browser never receives the service role key."""

    def upload(self, object_path: str, content: bytes, content_type: str) -> str:
        settings = get_settings()
        response = httpx.post(
            self._object_url(object_path),
            content=content,
            headers={
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "apikey": settings.supabase_service_role_key,
                "Content-Type": content_type,
                "x-upsert": "true",
            },
            timeout=60,
        )
        if response.status_code >= 400:
            raise AppError("storage_failed", "The file could not be stored.", 502)
        return object_path

    def signed_url(self, object_path: str, expires_in: int = 120) -> str:
        settings = get_settings()
        bucket = settings.supabase_storage_bucket
        quoted = quote(object_path, safe="/")
        url = f"{settings.supabase_url.rstrip('/')}/storage/v1/object/sign/{bucket}/{quoted}"
        response = httpx.post(
            url,
            json={"expiresIn": expires_in},
            headers={
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "apikey": settings.supabase_service_role_key,
            },
            timeout=30,
        )
        if response.status_code >= 400:
            raise AppError("storage_failed", "The file link could not be created.", 502)
        signed = response.json().get("signedURL") or response.json().get("signedUrl")
        if not signed:
            raise AppError("storage_failed", "The file link could not be created.", 502)
        if signed.startswith("http"):
            return signed
        return f"{settings.supabase_url.rstrip('/')}/storage/v1{signed}"

    def download(self, object_path: str) -> bytes:
        response = httpx.get(self._object_url(object_path), headers=self._auth_headers(), timeout=60)
        if response.status_code >= 400:
            raise AppError("storage_failed", "The file could not be read.", 502)
        return response.content

    def delete(self, object_path: str) -> None:
        response = httpx.delete(self._object_url(object_path), headers=self._auth_headers(), timeout=30)
        if response.status_code not in {200, 204, 404}:
            raise AppError("storage_failed", "The file could not be removed.", 502)

    def _object_url(self, object_path: str) -> str:
        settings = get_settings()
        quoted = quote(object_path, safe="/")
        bucket = settings.supabase_storage_bucket
        return f"{settings.supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{quoted}"

    def _auth_headers(self) -> dict[str, str]:
        settings = get_settings()
        return {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
        }
