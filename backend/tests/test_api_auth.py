"""API tests for the authentication flow: signup/verify/login+OTP/refresh/logout."""
import re

from app.models import EmailVerificationToken


def _verification_token(db, user_id):
    row = (
        db.query(EmailVerificationToken)
        .filter(EmailVerificationToken.user_id == user_id)
        .order_by(EmailVerificationToken.id.desc())
        .first()
    )
    return row.token


def _otp_from_console(capsys, email):
    """SMTP is disabled in tests (see conftest.py), so send_login_otp_email
    prints the code to stdout instead of sending it — grab it from there."""
    printed = capsys.readouterr().out
    match = re.search(rf"login OTP for {re.escape(email)}: (\d{{6}})", printed)
    assert match, f"expected the console-fallback OTP line in stdout, got: {printed!r}"
    return match.group(1)


def _login_with_otp(client, capsys, email, password):
    """Drives both steps of login and returns the final LoginResponse body."""
    step1 = client.post("/auth/login", json={"email": email, "password": password})
    assert step1.status_code == 200, step1.text
    login_token = step1.json()["login_token"]
    otp = _otp_from_console(capsys, email)
    step2 = client.post("/auth/verify-otp", json={"login_token": login_token, "otp": otp})
    assert step2.status_code == 200, step2.text
    return step2.json()


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


def test_login_blocked_until_email_verified(client, db, capsys):
    r = client.post("/auth/signup", json={"email": "unverified@test.com", "password": "password123"})
    user_id = r.json()["user"]["id"]
    r = client.post("/auth/login", json={"email": "unverified@test.com", "password": "password123"})
    assert r.status_code == 403

    token = _verification_token(db, user_id)
    verified = client.post("/auth/verify-email", json={"token": token})
    assert verified.status_code == 200

    body = _login_with_otp(client, capsys, "unverified@test.com", "password123")
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["email_verified"] is True


def test_login_wrong_password(client, db):
    r = client.post("/auth/signup", json={"email": "log@test.com", "password": "password123"})
    token = _verification_token(db, r.json()["user"]["id"])
    client.post("/auth/verify-email", json={"token": token})

    bad = client.post("/auth/login", json={"email": "log@test.com", "password": "nope"})
    assert bad.status_code == 401


def test_login_step1_returns_no_tokens(client, db, capsys):
    r = client.post("/auth/signup", json={"email": "otp1@test.com", "password": "password123"})
    token = _verification_token(db, r.json()["user"]["id"])
    client.post("/auth/verify-email", json={"token": token})

    step1 = client.post("/auth/login", json={"email": "otp1@test.com", "password": "password123"})
    assert step1.status_code == 200
    body = step1.json()
    assert "login_token" in body
    assert "access_token" not in body
    assert "refresh_token" not in body
    # drain the printed OTP so it doesn't leak into a later capsys read in this test
    _otp_from_console(capsys, "otp1@test.com")


def test_verify_otp_wrong_code_rejected(client, db, capsys):
    r = client.post("/auth/signup", json={"email": "otp2@test.com", "password": "password123"})
    token = _verification_token(db, r.json()["user"]["id"])
    client.post("/auth/verify-email", json={"token": token})

    step1 = client.post("/auth/login", json={"email": "otp2@test.com", "password": "password123"})
    login_token = step1.json()["login_token"]
    _otp_from_console(capsys, "otp2@test.com")

    wrong = client.post("/auth/verify-otp", json={"login_token": login_token, "otp": "000000"})
    assert wrong.status_code == 401


def test_verify_otp_bogus_login_token_rejected(client):
    r = client.post("/auth/verify-otp", json={"login_token": "not-a-real-token", "otp": "123456"})
    assert r.status_code == 401


def test_verify_otp_cannot_be_reused(client, db, capsys):
    r = client.post("/auth/signup", json={"email": "otp3@test.com", "password": "password123"})
    token = _verification_token(db, r.json()["user"]["id"])
    client.post("/auth/verify-email", json={"token": token})

    step1 = client.post("/auth/login", json={"email": "otp3@test.com", "password": "password123"})
    login_token = step1.json()["login_token"]
    otp = _otp_from_console(capsys, "otp3@test.com")

    first = client.post("/auth/verify-otp", json={"login_token": login_token, "otp": otp})
    assert first.status_code == 200

    # replaying the same (login_token, otp) pair after it's already succeeded must fail
    second = client.post("/auth/verify-otp", json={"login_token": login_token, "otp": otp})
    assert second.status_code == 401


def test_login_twice_issues_independent_otp_challenges(client, db, capsys):
    r = client.post("/auth/signup", json={"email": "otp5@test.com", "password": "password123"})
    token = _verification_token(db, r.json()["user"]["id"])
    client.post("/auth/verify-email", json={"token": token})

    first = _login_with_otp(client, capsys, "otp5@test.com", "password123")
    second = _login_with_otp(client, capsys, "otp5@test.com", "password123")
    assert first["access_token"] != second["access_token"]


def test_verify_otp_too_many_wrong_attempts_locks_out(client, db, capsys):
    r = client.post("/auth/signup", json={"email": "otp4@test.com", "password": "password123"})
    token = _verification_token(db, r.json()["user"]["id"])
    client.post("/auth/verify-email", json={"token": token})

    step1 = client.post("/auth/login", json={"email": "otp4@test.com", "password": "password123"})
    login_token = step1.json()["login_token"]
    otp = _otp_from_console(capsys, "otp4@test.com")

    # the first 4 wrong guesses are just "incorrect code"
    for _ in range(4):
        r = client.post("/auth/verify-otp", json={"login_token": login_token, "otp": "000000"})
        assert r.status_code == 401

    # the 5th wrong guess crosses the attempt cap and locks the challenge
    fifth = client.post("/auth/verify-otp", json={"login_token": login_token, "otp": "000000"})
    assert fifth.status_code == 429

    # even the CORRECT code is now rejected — the lock applies regardless of the guess
    r = client.post("/auth/verify-otp", json={"login_token": login_token, "otp": otp})
    assert r.status_code == 429


def test_login_refused_while_otp_is_locked_out(client, db, capsys):
    r = client.post("/auth/signup", json={"email": "otp6@test.com", "password": "password123"})
    token = _verification_token(db, r.json()["user"]["id"])
    client.post("/auth/verify-email", json={"token": token})

    step1 = client.post("/auth/login", json={"email": "otp6@test.com", "password": "password123"})
    login_token = step1.json()["login_token"]
    _otp_from_console(capsys, "otp6@test.com")

    for _ in range(5):
        client.post("/auth/verify-otp", json={"login_token": login_token, "otp": "000000"})

    # can't just call /auth/login again to sidestep the lock and reset attempts
    locked_login = client.post("/auth/login", json={"email": "otp6@test.com", "password": "password123"})
    assert locked_login.status_code == 429


def test_login_works_again_once_the_lockout_expires(client, db, capsys):
    from datetime import datetime, timedelta
    from app.models import LoginOtp

    r = client.post("/auth/signup", json={"email": "otp7@test.com", "password": "password123"})
    token = _verification_token(db, r.json()["user"]["id"])
    client.post("/auth/verify-email", json={"token": token})

    step1 = client.post("/auth/login", json={"email": "otp7@test.com", "password": "password123"})
    login_token = step1.json()["login_token"]
    _otp_from_console(capsys, "otp7@test.com")
    for _ in range(5):
        client.post("/auth/verify-otp", json={"login_token": login_token, "otp": "000000"})

    assert client.post(
        "/auth/login", json={"email": "otp7@test.com", "password": "password123"}
    ).status_code == 429

    # fast-forward past the lockout window directly in the DB (no real 10-minute wait)
    row = db.query(LoginOtp).filter(LoginOtp.login_token == login_token).first()
    row.locked_until = datetime.utcnow() - timedelta(seconds=1)
    db.commit()

    reattempt = client.post("/auth/login", json={"email": "otp7@test.com", "password": "password123"})
    assert reattempt.status_code == 200


def test_login_otps_keeps_a_single_row_per_user(client, db, capsys):
    r = client.post("/auth/signup", json={"email": "otp8@test.com", "password": "password123"})
    user_id = r.json()["user"]["id"]
    token = _verification_token(db, user_id)
    client.post("/auth/verify-email", json={"token": token})

    from app.models import LoginOtp

    for _ in range(3):
        client.post("/auth/login", json={"email": "otp8@test.com", "password": "password123"})
        _otp_from_console(capsys, "otp8@test.com")
        assert db.query(LoginOtp).filter(LoginOtp.user_id == user_id).count() == 1


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


def test_refresh_rotates_token_and_revokes_the_old_one(client, make_user, capsys):
    _user_id, headers = make_user(email="refresh@test.com")
    access_token = headers["Authorization"].split(" ")[1]

    login = _login_with_otp(client, capsys, "refresh@test.com", "password123")
    refresh_token = login["refresh_token"]

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


def test_logout_blacklists_the_access_token_and_revokes_refresh(client, make_user, capsys):
    _user_id, headers = make_user(email="logout@test.com")

    login = _login_with_otp(client, capsys, "logout@test.com", "password123")
    access_token = login["access_token"]
    refresh_token = login["refresh_token"]
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
