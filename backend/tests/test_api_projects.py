"""API tests for /projects, including the transaction->project assignment
IDOR fix: PATCH /transactions/{tid}/project must verify the target project
belongs to the caller, not just the transaction.
"""


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


def _project(client, headers, name="Vacation Fund"):
    r = client.post("/projects", headers=headers, json={"name": name, "type": "savings"})
    assert r.status_code == 200, r.text
    return r.json()


def test_assign_own_transaction_to_own_project(client, make_user):
    _uid, headers = make_user()
    tx = _manual(client, headers)
    project = _project(client, headers)

    r = client.patch(f"/transactions/{tx['id']}/project", headers=headers,
                      json={"project_id": project["id"]})
    assert r.status_code == 200, r.text


def test_unassign_transaction_from_project(client, make_user):
    _uid, headers = make_user()
    tx = _manual(client, headers)
    project = _project(client, headers)
    client.patch(f"/transactions/{tx['id']}/project", headers=headers, json={"project_id": project["id"]})

    r = client.patch(f"/transactions/{tx['id']}/project", headers=headers, json={"project_id": None})
    assert r.status_code == 200, r.text


def test_cannot_assign_own_transaction_to_another_users_project(client, make_user):
    _a, a_headers = make_user(email="a@test.com")
    _b, b_headers = make_user(email="b@test.com")
    a_tx = _manual(client, a_headers, description="A-only")
    b_project = _project(client, b_headers, name="B's Project")

    # A tries to attach their own transaction to B's project (the IDOR).
    r = client.patch(f"/transactions/{a_tx['id']}/project", headers=a_headers,
                      json={"project_id": b_project["id"]})
    assert r.status_code == 404

    # A's transaction must remain unassigned — the attempt must not have partially applied.
    listed = client.get("/transactions", headers=a_headers).json()
    a_tx_after = next(t for t in listed if t["id"] == a_tx["id"])
    assert a_tx_after.get("project_id") is None


def test_cannot_assign_another_users_transaction_at_all(client, make_user):
    _a, a_headers = make_user(email="c@test.com")
    _b, b_headers = make_user(email="d@test.com")
    b_tx = _manual(client, b_headers, description="B-only")
    a_project = _project(client, a_headers, name="A's Project")

    r = client.patch(f"/transactions/{b_tx['id']}/project", headers=a_headers,
                      json={"project_id": a_project["id"]})
    assert r.status_code == 403
