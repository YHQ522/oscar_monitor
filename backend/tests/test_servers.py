"""服务器 CRUD 与采集相关测试。"""
from __future__ import annotations


def _server_payload() -> dict:
    return {
        "name": "测试服务器",
        "ssh_host": "192.168.1.100",
        "ssh_port": 22,
        "ssh_user": "root",
        "ssh_pass": "secret",
        "db_host": "127.0.0.1",
        "db_port": 2003,
        "db_user": "SYSDBA",
        "db_pass": "dbsecret",
        "db_name": "OSRDB",
        "db_type": "oscar",
        "os_type": "linux",
    }


def test_server_crud(client, auth_headers):
    resp = client.post("/api/servers", json=_server_payload(), headers=auth_headers)
    assert resp.status_code == 200
    server_id = resp.json()["id"]

    # 列表脱敏
    resp = client.get("/api/servers", headers=auth_headers)
    servers = resp.json()
    assert len(servers) == 1
    assert servers[0]["has_ssh_pass"] is True
    assert servers[0]["has_db_pass"] is True
    assert "ssh_pass" not in servers[0]
    assert servers[0]["enabled_categories"]  # 默认类别已填充

    # 更新
    resp = client.put(f"/api/servers/{server_id}", json={"name": "改名服务器"}, headers=auth_headers)
    assert resp.status_code == 200

    # 无权限用户无法编辑
    token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    client.post("/api/users", json={"username": "viewer", "password": "view123456", "is_admin": False, "perms": ["servers_view"]}, headers=h)
    vtoken = client.post("/api/auth/login", json={"username": "viewer", "password": "view123456"}).json()["token"]
    vh = {"Authorization": f"Bearer {vtoken}"}
    resp = client.post("/api/servers", json=_server_payload(), headers=vh)
    assert resp.status_code == 403

    # 删除
    resp = client.delete(f"/api/servers/{server_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert client.get("/api/servers", headers=auth_headers).json() == []


def test_server_404(client, auth_headers):
    resp = client.get("/api/servers/nonexist/data", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() is None


def test_persist_enabled_requires_log(client, auth_headers):
    payload = _server_payload()
    payload["persist_enabled"] = True
    resp = client.post("/api/servers", json=payload, headers=auth_headers)
    assert resp.status_code == 400
