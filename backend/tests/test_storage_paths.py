import uuid

import pytest

from app.core.errors import AppError
from app.services.storage import build_object_path


def test_object_path_stays_inside_the_organization():
    organization_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    document_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    path = build_object_path(organization_id, document_id, r"..\..\secret.txt")
    assert path == f"{organization_id}/{document_id}/secret.txt"
    assert ".." not in path


def test_blank_filename_is_rejected():
    with pytest.raises(AppError):
        build_object_path(uuid.uuid4(), uuid.uuid4(), "..")
