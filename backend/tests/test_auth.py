from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.main import app
from app.models import AuthSession, User
from app.services.auth import COOKIE_NAME, is_valid_email, normalize_email
from app.services.passwords import (
    burn_time_like_a_login,
    hash_password,
    verify_password,
)
from app.services.ratelimit import RateLimiter, limiters

GOOD = {"email": "Ana@Example.com", "password": "correct horse battery", "display_name": " Ana "}


class TestPasswords:
    def test_round_trip(self) -> None:
        stored = hash_password("correct horse battery")
        assert verify_password("correct horse battery", stored)
        assert not verify_password("correct horse batterY", stored)
        assert not verify_password("", stored)

    def test_hashes_are_salted_and_self_describing(self) -> None:
        a, b = hash_password("same password"), hash_password("same password")
        assert a != b  # different salts
        assert a.startswith("scrypt$32768$8$1$") and "same password" not in a
        assert verify_password("same password", a) and verify_password("same password", b)

    def test_unicode_passwords(self) -> None:
        assert verify_password("pässwörd-密码-🔑", hash_password("pässwörd-密码-🔑"))

    @pytest.mark.parametrize("junk", ["", "x", "scrypt$1$2", "md5$a$b$c$d$e", "scrypt$a$b$c$d$e", "scrypt$32768$8$1$!!!$!!!"])
    def test_malformed_stored_hashes_never_verify_or_crash(self, junk: str) -> None:
        assert verify_password("anything", junk) is False

    def test_timing_decoy_runs(self) -> None:
        burn_time_like_a_login()  # must not raise


class TestRateLimiter:
    def make(self, max_events: int = 3, window: float = 60):
        now = {"t": 1000.0}
        return RateLimiter(max_events, window, clock=lambda: now["t"]), now

    def test_blocks_after_the_limit_and_recovers_when_the_window_passes(self) -> None:
        limiter, now = self.make()
        for _ in range(3):
            assert not limiter.blocked("k")
            limiter.hit("k")
        assert limiter.blocked("k") and limiter.retry_after("k") == 61
        now["t"] += 61
        assert not limiter.blocked("k") and limiter.retry_after("k") == 0

    def test_keys_are_independent_and_reset_works(self) -> None:
        limiter, _ = self.make(max_events=1)
        limiter.hit("a")
        assert limiter.blocked("a") and not limiter.blocked("b")
        limiter.reset("a")
        assert not limiter.blocked("a")

    def test_old_events_slide_out_one_by_one(self) -> None:
        limiter, now = self.make(max_events=2, window=10)
        limiter.hit("k"); now["t"] += 6; limiter.hit("k")
        assert limiter.blocked("k")
        now["t"] += 5  # the first hit is now 11s old
        assert not limiter.blocked("k")


def test_email_helpers() -> None:
    assert normalize_email("  Ana@Example.COM ") == "ana@example.com"
    assert is_valid_email("a@b.co") and not is_valid_email("nope") and not is_valid_email("a@b")
    assert not is_valid_email("a b@c.de") and not is_valid_email("x" * 250 + "@a.de")


class TestRegister:
    async def test_creates_an_account_and_signs_in(self, anon_client: AsyncClient, session: AsyncSession) -> None:
        response = await anon_client.post("/api/auth/register", json=GOOD)
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "ana@example.com" and body["display_name"] == "Ana"  # normalised
        assert "password" not in response.text and "hash" not in response.text

        cookie = response.headers["set-cookie"]
        assert cookie.startswith(f"{COOKIE_NAME}=") and "HttpOnly" in cookie and "SameSite=lax" in cookie
        assert (await anon_client.get("/api/auth/me")).json()["email"] == "ana@example.com"

        stored = (await session.execute(select(User).where(User.email == "ana@example.com"))).scalar_one()
        assert stored.password_hash.startswith("scrypt$") and "correct horse" not in stored.password_hash

    async def test_the_session_cookie_is_not_stored_in_the_clear(self, anon_client: AsyncClient, session: AsyncSession) -> None:
        await anon_client.post("/api/auth/register", json=GOOD)
        token = anon_client.cookies[COOKIE_NAME]
        hashes = (await session.execute(select(AuthSession.token_hash))).scalars().all()
        assert token not in hashes and all(len(h) == 64 for h in hashes)

    async def test_duplicate_email_is_rejected_ignoring_case(self, anon_client: AsyncClient) -> None:
        await anon_client.post("/api/auth/register", json=GOOD)
        again = await anon_client.post("/api/auth/register", json={**GOOD, "email": "ANA@example.COM"})
        assert again.status_code == 409 and "already exists" in again.json()["detail"]

    @pytest.mark.parametrize(
        ("changes", "message"),
        [
            ({"password": "short"}, "at least 10"),
            ({"password": "x" * 129}, "at most 128"),
            ({"email": "not-an-email"}, "valid email"),
            ({"email": "ana@example.com", "password": "ana@example.com"}, "can't be your email"),
            ({"email": ""}, "email"),
        ],
    )
    async def test_invalid_details(self, anon_client: AsyncClient, changes: dict, message: str) -> None:
        response = await anon_client.post("/api/auth/register", json={**GOOD, **changes})
        assert response.status_code == 422 and message in response.text

    async def test_sign_ups_can_be_closed(self, anon_client: AsyncClient) -> None:
        app.dependency_overrides[get_settings] = lambda: Settings(allow_registration=False)
        try:
            response = await anon_client.post("/api/auth/register", json=GOOD)
        finally:
            app.dependency_overrides.pop(get_settings, None)
        assert response.status_code == 403 and "closed" in response.json()["detail"]

    async def test_too_many_sign_ups_from_one_address_are_throttled(self, anon_client: AsyncClient) -> None:
        for i in range(limiters.register_by_ip.max_events):
            ok = await anon_client.post("/api/auth/register", json={**GOOD, "email": f"user{i}@example.com"})
            assert ok.status_code == 201
        blocked = await anon_client.post("/api/auth/register", json={**GOOD, "email": "one-more@example.com"})
        assert blocked.status_code == 429 and "Retry-After" in blocked.headers


class TestLogin:
    @pytest.fixture
    async def account(self, anon_client: AsyncClient) -> None:
        await anon_client.post("/api/auth/register", json=GOOD)
        await anon_client.post("/api/auth/logout")
        assert (await anon_client.get("/api/auth/me")).status_code == 401

    async def test_signs_in_with_the_right_password(self, anon_client: AsyncClient, account) -> None:
        response = await anon_client.post("/api/auth/login", json={"email": " ANA@example.com ", "password": GOOD["password"]})
        assert response.status_code == 200 and response.json()["email"] == "ana@example.com"
        assert (await anon_client.get("/api/auth/me")).status_code == 200

    async def test_wrong_password_and_unknown_email_look_identical(self, anon_client: AsyncClient, account) -> None:
        wrong = await anon_client.post("/api/auth/login", json={"email": "ana@example.com", "password": "not the password"})
        unknown = await anon_client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "not the password"})
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json() == {"detail": "Incorrect email or password."}
        assert COOKIE_NAME not in wrong.headers.get("set-cookie", "")

    async def test_repeated_failures_lock_the_account_for_a_while(self, anon_client: AsyncClient, account) -> None:
        for _ in range(limiters.login_by_email.max_events):
            assert (await anon_client.post("/api/auth/login", json={"email": "ana@example.com", "password": "nope nope nope"})).status_code == 401
        locked = await anon_client.post("/api/auth/login", json={"email": "ana@example.com", "password": GOOD["password"]})
        assert locked.status_code == 429 and int(locked.headers["Retry-After"]) > 0  # even the right password waits

    async def test_a_successful_sign_in_clears_the_failure_count(self, anon_client: AsyncClient, account) -> None:
        for _ in range(limiters.login_by_email.max_events - 1):
            await anon_client.post("/api/auth/login", json={"email": "ana@example.com", "password": "nope nope nope"})
        assert (await anon_client.post("/api/auth/login", json={"email": "ana@example.com", "password": GOOD["password"]})).status_code == 200
        await anon_client.post("/api/auth/logout")
        assert (await anon_client.post("/api/auth/login", json={"email": "ana@example.com", "password": "nope nope nope"})).status_code == 401

    async def test_login_does_not_reveal_the_password_rules(self, anon_client: AsyncClient) -> None:
        response = await anon_client.post("/api/auth/login", json={"email": "ana@example.com", "password": "x"})
        assert response.status_code == 401


class TestSessions:
    async def test_signing_out_ends_the_session_everywhere(self, anon_client: AsyncClient, session: AsyncSession) -> None:
        await anon_client.post("/api/auth/register", json=GOOD)
        token = anon_client.cookies[COOKIE_NAME]
        assert (await anon_client.post("/api/auth/logout")).status_code == 204
        assert (await anon_client.get("/api/auth/me")).status_code == 401
        # The old cookie, replayed by someone who copied it, no longer works.
        anon_client.cookies.set(COOKIE_NAME, token)
        assert (await anon_client.get("/api/auth/me")).status_code == 401

    async def test_expired_sessions_are_refused(self, anon_client: AsyncClient, session: AsyncSession) -> None:
        await anon_client.post("/api/auth/register", json=GOOD)
        await session.execute(update(AuthSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        await session.commit()
        assert (await anon_client.get("/api/auth/me")).status_code == 401

    @pytest.mark.parametrize("token", ["", "garbage", "a" * 43, "../../etc/passwd"])
    async def test_forged_cookies_are_refused(self, anon_client: AsyncClient, token: str) -> None:
        anon_client.cookies.set(COOKIE_NAME, token)
        assert (await anon_client.get("/api/auth/me")).status_code == 401

    async def test_the_cookie_is_marked_secure_when_configured(self, anon_client: AsyncClient) -> None:
        app.dependency_overrides[get_settings] = lambda: Settings(cookie_secure=True, session_days=7)
        try:
            response = await anon_client.post("/api/auth/register", json=GOOD)
        finally:
            app.dependency_overrides.pop(get_settings, None)
        cookie = response.headers["set-cookie"]
        assert "Secure" in cookie and f"Max-Age={7 * 24 * 3600}" in cookie

    async def test_logging_out_when_not_signed_in_is_harmless(self, anon_client: AsyncClient) -> None:
        assert (await anon_client.post("/api/auth/logout")).status_code == 204

    async def test_me_needs_an_account(self, anon_client: AsyncClient) -> None:
        response = await anon_client.get("/api/auth/me")
        assert response.status_code == 401 and "sign in" in response.json()["detail"].lower()

    async def test_an_account_works_end_to_end_with_the_cookie_it_was_given(self, anon_client: AsyncClient) -> None:
        await anon_client.post("/api/auth/register", json=GOOD)
        project = await anon_client.post("/api/assignments", json={"title": "Mine", "instructions_text": "i", "rubric_raw_text": "r"})
        assert project.status_code == 201
        assert [p["title"] for p in (await anon_client.get("/api/assignments")).json()] == ["Mine"]
