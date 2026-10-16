from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings, get_settings
from app.main import app
from tests.helpers import make_docx


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(max_upload_bytes=100_000)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_extract_txt(client: AsyncClient) -> None:
    response = await client.post("/api/files/extract", files={"file": ("a.txt", b"hello world")})
    assert response.status_code == 200
    assert response.json() == {"filename": "a.txt", "text": "hello world", "char_count": 11}


async def test_extract_docx(client: AsyncClient) -> None:
    data = make_docx(["Write an essay"])
    response = await client.post("/api/files/extract", files={"file": ("a.docx", data)})
    assert response.status_code == 200
    assert response.json()["text"] == "Write an essay"


async def test_unsupported_type_is_415(client: AsyncClient) -> None:
    response = await client.post("/api/files/extract", files={"file": ("a.png", b"x")})
    assert response.status_code == 415


async def test_empty_file_is_422(client: AsyncClient) -> None:
    response = await client.post("/api/files/extract", files={"file": ("a.txt", b"")})
    assert response.status_code == 422


async def test_oversized_upload_is_413(client: AsyncClient) -> None:
    response = await client.post("/api/files/extract", files={"file": ("a.txt", b"x" * 100_001)})
    assert response.status_code == 413
