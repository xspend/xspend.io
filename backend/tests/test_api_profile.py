"""API tests for GET/POST /profile — confirms these read/write the split-out
UserProfile table (see app/models/models.py) rather than columns on User.
"""


def test_get_profile_returns_defaults_for_new_user(client, make_user):
    _user_id, headers = make_user(email="profile1@test.com", name="Profile One")
    r = client.get("/profile", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["exists"] is True
    assert body["full_name"] == "Profile One"
    assert body["email"] == "profile1@test.com"
    assert body["monthly_budget"] == 0
    assert body["currency_code"] == "USD"
    assert body["income_frequency"] == "monthly"


def test_post_profile_updates_are_reflected_in_get(client, make_user):
    _user_id, headers = make_user(email="profile2@test.com")

    r = client.post(
        "/profile",
        headers=headers,
        json={
            "income_amount": 6000,
            "income_frequency": "biweekly",
            "currency_code": "EUR",
            "payday_day": "1",
            "selected_goals": "travel",
            "other_goals": "emergency fund",
            "savings_goal_monthly": 500,
            "savings_goal_weekly": 125,
            "debt_payoff_goal": 10000,
            "monthly_budget": 3000,
        },
    )
    assert r.status_code == 200
    assert r.json() == {"success": True}

    got = client.get("/profile", headers=headers).json()
    assert got["income_amount"] == 6000
    assert got["income_frequency"] == "biweekly"
    assert got["currency_code"] == "EUR"
    assert got["payday_day"] == "1"
    assert got["selected_goals"] == "travel"
    assert got["other_goals"] == "emergency fund"
    assert got["savings_goal_monthly"] == 500
    assert got["savings_goal_weekly"] == 125
    assert got["debt_payoff_goal"] == 10000
    assert got["monthly_budget"] == 3000


def test_post_profile_full_name_still_lands_on_user(client, db, make_user):
    from app.models import User

    user_id, headers = make_user(email="profile3@test.com", name="Old Name")
    r = client.post("/profile", headers=headers, json={"full_name": "New Name"})
    assert r.status_code == 200

    user = db.query(User).filter(User.id == user_id).first()
    assert user.full_name == "New Name"


def test_post_profile_legacy_aliases_still_work(client, make_user):
    _user_id, headers = make_user(email="profile4@test.com")

    r = client.post(
        "/profile",
        headers=headers,
        json={
            "monthly_income": 4500,
            "preferred_currency": "GBP",
            "monthly_savings_goal": 300,
            "weekly_savings_goal": 75,
        },
    )
    assert r.status_code == 200

    got = client.get("/profile", headers=headers).json()
    assert got["income_amount"] == 4500
    assert got["currency_code"] == "GBP"
    assert got["savings_goal_monthly"] == 300
    assert got["savings_goal_weekly"] == 75


def test_profile_data_isolated_per_user(client, make_user):
    _user_a, headers_a = make_user(email="profilea@test.com")
    _user_b, headers_b = make_user(email="profileb@test.com")

    client.post("/profile", headers=headers_a, json={"monthly_budget": 1000})
    client.post("/profile", headers=headers_b, json={"monthly_budget": 2000})

    assert client.get("/profile", headers=headers_a).json()["monthly_budget"] == 1000
    assert client.get("/profile", headers=headers_b).json()["monthly_budget"] == 2000


def test_get_profile_requires_auth(client):
    assert client.get("/profile").status_code == 401


def test_post_profile_requires_auth(client):
    assert client.post("/profile", json={"monthly_budget": 500}).status_code == 401
