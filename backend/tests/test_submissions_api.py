from httpx import AsyncClient

NEW = {"title": "Essay", "instructions_text": "Write.", "rubric_raw_text": "Thesis: 10"}


async def make_assignment(client: AsyncClient) -> int:
    return (await client.post("/api/assignments", json=NEW)).json()["id"]


async def test_versions_increment_per_assignment(client: AsyncClient) -> None:
    first, other = await make_assignment(client), await make_assignment(client)
    versions = []
    for assignment_id in (first, first, other, first):
        response = await client.post(f"/api/assignments/{assignment_id}/submissions", json={"draft_text": "My draft"})
        assert response.status_code == 201
        versions.append(response.json()["version_number"])
    assert versions == [1, 2, 1, 3]


async def test_draft_is_stored_verbatim_and_readable(client: AsyncClient) -> None:
    assignment_id = await make_assignment(client)
    draft = "  Line one\n\nLine   two  "
    created = (await client.post(f"/api/assignments/{assignment_id}/submissions", json={"draft_text": draft})).json()
    assert created["draft_text"] == draft  # offsets depend on the exact text
    fetched = (await client.get(f"/api/submissions/{created['id']}")).json()
    assert fetched["draft_text"] == draft


async def test_blank_and_oversized_drafts_are_rejected(client: AsyncClient) -> None:
    assignment_id = await make_assignment(client)
    url = f"/api/assignments/{assignment_id}/submissions"
    assert (await client.post(url, json={"draft_text": ""})).status_code == 422
    assert (await client.post(url, json={"draft_text": "   \n "})).status_code == 422
    assert (await client.post(url, json={"draft_text": "x" * 50_001})).status_code == 413
    assert (await client.post(url, json={"draft_text": "x" * 50_000})).status_code == 201


async def test_unknown_ids_are_404(client: AsyncClient) -> None:
    assert (await client.post("/api/assignments/999/submissions", json={"draft_text": "x"})).status_code == 404
    assert (await client.get("/api/submissions/999")).status_code == 404
    assert (await client.post("/api/submissions/999/grade")).status_code == 404
    assert (await client.get("/api/gradings/999")).status_code == 404
