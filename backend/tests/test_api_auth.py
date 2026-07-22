"""API tests for the authentication flow: signup/verify/login/refresh/logout."""
from app.models import EmailVerificationToken


def _verification_token(db, user_id):
    row = (
        db.query(EmailVerificationToken)
        .filter(EmailVerificationToken.user_id == user_id)
        .order_by(EmailVerificationToken.id.desc())
        .first()
    )
    return row.token


def test_signup_creates_unverified_user_with_no_token(client):
    r = client.post("/auth/signup", json={"email": "new@test.com", "password": "password123", "name": "New"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert "token" not in body
    assert "access_token" not in body
    assert body["user"]["email"] == "new@test.com"
    assert body["user"]["email_verified"] is False


def test_signup_rejects_short_password(client):
    r = client.post("/auth/signup", json={"email": "x@test.com", "password": "short"})
    assert r.status_code == 422


def test_signup_rejects_duplicate_email(client):
    client.post("/auth/signup", json={"email": "dup@test.com", "password": "password123"})
    r = client.post("/auth/signup", json={"email": "dup@test.com", "password": "password123"})
    assert r.status_code == 400


def test_login_blocked_until_email_verified(client, db):
    r = client.post("/auth/signup", json={"email": "unverified@test.com", "password": "password123"})
    user_id = r.json()["user"]["id"]
    r = client.post("/auth/login", json={"email": "unverified@test.com", "password": "password123"})
    assert r.status_code == 403

    token = _verification_token(db, user_id)
    verified = client.post("/auth/verify-email", json={"token": token})
    assert verified.status_code == 200

    ok = client.post("/auth/login", json={"email": "unverified@test.com", "password": "password123"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["email_verified"] is True


def test_login_wrong_password(client, db):
    r = client.post("/auth/signup", json={"email": "log@test.com", "password": "password123"})
    token = _verification_token(db, r.json()["user"]["id"])
    client.post("/auth/verify-email", json={"token": token})

    bad = client.post("/auth/login", json={"email": "log@test.com", "password": "nope"})
    assert bad.status_code == 401


def test_verify_email_rejects_bad_or_reused_token(client, db):
    r = client.post("/auth/signup", json={"email": "verify@test.com", "password": "password123"})
    token = _verification_token(db, r.json()["user"]["id"])

    assert client.post("/auth/verify-email", json={"token": "not-a-real-token"}).status_code == 400
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 200
    # reusing the same token a second time must fail — it's already used
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 400


def test_verify_email_eid_is_optional_but_checked_if_present(client, db):
    from app.core.security import encode_id

    r = client.post("/auth/signup", json={"email": "verify-id@test.com", "password": "password123"})
    user_id = r.json()["user"]["id"]
    token = _verification_token(db, user_id)

    # a mismatched eid rejects even a real, unexpired token
    mismatched = client.post("/auth/verify-email", json={"token": token, "eid": encode_id(user_id + 999)})
    assert mismatched.status_code == 400

    # the matching eid (as the emailed link would send) verifies normally
    ok = client.post("/auth/verify-email", json={"token": token, "eid": encode_id(user_id)})
    assert ok.status_code == 200


def test_resend_verification_issues_a_new_token(client, db):
    r = client.post("/auth/signup", json={"email": "resend@test.com", "password": "password123"})
    user_id = r.json()["user"]["id"]
    first_token = _verification_token(db, user_id)

    resend = client.post("/auth/resend-verification", json={"email": "resend@test.com"})
    assert resend.status_code == 200
    second_token = _verification_token(db, user_id)
    assert second_token != first_token

    assert client.post("/auth/verify-email", json={"token": second_token}).status_code == 200


def test_resend_verification_unknown_email(client):
    r = client.post("/auth/resend-verification", json={"email": "nobody@test.com"})
    assert r.status_code == 404


def test_refresh_rotates_token_and_revokes_the_old_one(client, make_user):
    _user_id, headers = make_user(email="refresh@test.com")
    access_token = headers["Authorization"].split(" ")[1]

    login = client.post("/auth/login", json={"email": "refresh@test.com", "password": "password123"})
    refresh_token = login.json()["refresh_token"]

    refreshed = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 200
    new_pair = refreshed.json()
    assert new_pair["access_token"] != access_token
    assert new_pair["refresh_token"] != refresh_token

    # the old refresh token was revoked by the rotation — reusing it must fail
    reused = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert reused.status_code == 401


def test_refresh_rejects_an_access_token(client, make_user):
    _user_id, headers = make_user(email="wrongtype@test.com")
    access_token = headers["Authorization"].split(" ")[1]
    r = client.post("/auth/refresh", json={"refresh_token": access_token})
    assert r.status_code == 401


def test_logout_blacklists_the_access_token_and_revokes_refresh(client, make_user):
    _user_id, headers = make_user(email="logout@test.com")

    login = client.post("/auth/login", json={"email": "logout@test.com", "password": "password123"})
    access_token = login.json()["access_token"]
    refresh_token = login.json()["refresh_token"]
    auth_headers = {"Authorization": f"Bearer {access_token}"}

    assert client.get("/auth/me", headers=auth_headers).status_code == 200

    logout = client.post("/auth/logout", json={"refresh_token": refresh_token}, headers=auth_headers)
    assert logout.status_code == 200

    # the blacklisted access token must now be rejected everywhere
    assert client.get("/auth/me", headers=auth_headers).status_code == 401
    # and the refresh token it was paired with was revoked too
    assert client.post("/auth/refresh", json={"refresh_token": refresh_token}).status_code == 401


def test_me_requires_valid_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_me_returns_current_user(client, make_user):
    _user_id, headers = make_user(email="me@test.com", name="Me")
    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "me@test.com"


def test_protected_endpoint_requires_auth(client):
    # /transactions must never serve data without a valid bearer token.
    assert client.get("/transactions").status_code == 401
