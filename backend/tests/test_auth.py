"""认证/用户/限速测试。"""
from __future__ import annotations


def test_login_success(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"
    assert resp.json()["is_admin"] is True


def test_login_wrong_password(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_me_without_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_change_password(client, auth_headers):
    resp = client.put(
        "/api/auth/password",
        json={"old_password": "admin123", "new_password": "newpass123"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    # 旧密码登录失败，新密码成功
    assert client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": "newpass123"}).status_code == 200


def test_user_crud(client, auth_headers):
    resp = client.post("/api/users", json={"username": "ops", "password": "ops123456", "is_admin": False, "perms": ["dashboard"]}, headers=auth_headers)
    assert resp.status_code == 200

    resp = client.get("/api/users", headers=auth_headers)
    users = resp.json()
    assert any(u["username"] == "ops" for u in users)
    # 密码不泄露
    assert all("password" not in u for u in users)

    resp = client.put("/api/users/ops", json={"perms": ["dashboard", "servers_view"]}, headers=auth_headers)
    assert resp.status_code == 200

    resp = client.delete("/api/users/ops", headers=auth_headers)
    assert resp.status_code == 200


def test_cannot_delete_admin(client, auth_headers):
    resp = client.delete("/api/users/admin", headers=auth_headers)
    assert resp.status_code == 400


def test_permission_denied(client):
    # 添加一个无权限用户
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/users", json={"username": "viewer", "password": "view123456", "is_admin": False, "perms": []}, headers=headers)
    vtoken = client.post("/api/auth/login", json={"username": "viewer", "password": "view123456"}).json()["token"]
    vheaders = {"Authorization": f"Bearer {vtoken}"}

    resp = client.get("/api/users", headers=vheaders)
    assert resp.status_code == 403

    # 无任何权限的用户不能访问服务器列表（需 dashboard 或 servers_view）
    resp = client.get("/api/servers", headers=vheaders)
    assert resp.status_code == 403

    # 拥有 dashboard 权限的用户可访问服务器列表
    client.post(
        "/api/users",
        json={"username": "viewer2", "password": "view123456", "is_admin": False, "perms": ["dashboard"]},
        headers=headers,
    )
    v2token = client.post("/api/auth/login", json={"username": "viewer2", "password": "view123456"}).json()["token"]
    resp = client.get("/api/servers", headers={"Authorization": f"Bearer {v2token}"})
    assert resp.status_code == 200


def test_login_rate_limit(client):
    for _ in range(6):
        client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    # 第 7 次尝试应被限速
    resp = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert resp.status_code == 429
