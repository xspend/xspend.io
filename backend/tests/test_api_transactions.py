"""API tests for transactions: CRUD, response shape, and multi-user isolation."""


def _manual(client, headers, description="Coffee Shop", amount=-4.50, category="Food & Dining"):
    r = client.post("/transactions/manual", headers=headers, json={
        "transaction_date": "2026-03-15",
        "description": description,
        "amount": amount,
        "currency": "USD",
        "category": category,
        "transaction_type": "expense",
        "bank_source": "Manual Entry",
    })
    assert r.status_code == 200, r.text
    return r.json()["transaction"]


def test_manual_create_then_list(client, make_user):
    _uid, headers = make_user()
    tx = _manual(client, headers, description="Whole Foods")
    assert tx["description"] == "Whole Foods"

    listed = client.get("/transactions", headers=headers).json()
    assert any(t["id"] == tx["id"] for t in listed)


def test_response_shape_stable_after_column_dedup(client, make_user):
    # These keys are what the frontend consumes; they must survive the schema dedup
    # even though several are now derived rather than stored.
    _uid, headers = make_user()
    tx = _manual(client, headers)
    for key in ("id", "description", "original_description", "currency",
                "category", "review_status", "is_edited", "classification_confidence"):
        assert key in tx
    assert tx["review_status"] in {"reviewed", "needs_review"}


def test_patch_updates_transaction(client, make_user):
    _uid, headers = make_user()
    tx = _manual(client, headers, category="Food & Dining")
    r = client.patch(f"/transactions/{tx['id']}", headers=headers, json={"category": "Groceries"})
    assert r.status_code == 200, r.text
    assert r.json()["transaction"]["category"] == "Groceries"
    assert r.json()["transaction"]["is_edited"] is True


def test_delete_transaction(client, make_user):
    _uid, headers = make_user()
    tx = _manual(client, headers)
    assert client.delete(f"/transactions/{tx['id']}", headers=headers).status_code == 200
    listed = client.get("/transactions", headers=headers).json()
    assert not any(t["id"] == tx["id"] for t in listed)


# ── Multi-user isolation — the #1 invariant ──

def test_list_is_scoped_to_user(client, make_user):
    _a, a_headers = make_user(email="a@test.com")
    _b, b_headers = make_user(email="b@test.com")
    _manual(client, a_headers, description="A-private")
    _manual(client, b_headers, description="B-private")

    a_list = client.get("/transactions", headers=a_headers).json()
    descs = {t["description"] for t in a_list}
    assert "A-private" in descs
    assert "B-private" not in descs        # A must never see B's rows


def test_cannot_patch_another_users_transaction(client, make_user):
    _a, a_headers = make_user(email="a@test.com")
    _b, b_headers = make_user(email="b@test.com")
    b_tx = _manual(client, b_headers, description="B-only")
    # A tries to edit B's transaction.
    r = client.patch(f"/transactions/{b_tx['id']}", headers=a_headers, json={"category": "Groceries"})
    assert r.status_code == 403


def test_cannot_delete_another_users_transaction(client, make_user):
    _a, a_headers = make_user(email="a@test.com")
    _b, b_headers = make_user(email="b@test.com")
    b_tx = _manual(client, b_headers, description="B-only")
    r = client.delete(f"/transactions/{b_tx['id']}", headers=a_headers)
    assert r.status_code in (403, 404)     # must not succeed
    # And B's transaction still exists.
    assert any(t["id"] == b_tx["id"] for t in client.get("/transactions", headers=b_headers).json())
