"""API tests for the authentication flow."""


def test_signup_returns_token(client):
    r = client.post("/auth/signup", json={"email": "new@test.com", "password": "password123", "name": "New"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token"]
    assert body["user"]["email"] == "new@test.com"


def test_signup_rejects_short_password(client):
    r = client.post("/auth/signup", json={"email": "x@test.com", "password": "short"})
    assert r.status_code == 400


def test_signup_rejects_duplicate_email(client):
    client.post("/auth/signup", json={"email": "dup@test.com", "password": "password123"})
    r = client.post("/auth/signup", json={"email": "dup@test.com", "password": "password123"})
    assert r.status_code == 400


def test_login_success_and_wrong_password(client):
    client.post("/auth/signup", json={"email": "log@test.com", "password": "password123"})
    ok = client.post("/auth/login", json={"email": "log@test.com", "password": "password123"})
    assert ok.status_code == 200 and ok.json()["token"]
    bad = client.post("/auth/login", json={"email": "log@test.com", "password": "nope"})
    assert bad.status_code == 401


def test_me_requires_valid_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_protected_endpoint_requires_auth(client):
    # /transactions must never serve data without a valid bearer token.
    assert client.get("/transactions").status_code == 401
