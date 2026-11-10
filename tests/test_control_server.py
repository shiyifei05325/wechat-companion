# -*- coding: utf-8 -*-
"""控制台服务器路由与本地专用限制测试（Flask 测试客户端，不启动伴侣）"""
import pytest

from control import server as cs


@pytest.fixture(scope="module")
def client():
    return cs.app.test_client()


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "后端控制台".encode("utf-8") in r.data


def test_health_endpoint(client):
    j = client.get("/api/health").get_json()
    assert j["ok"] is True
    assert j["version"]
    assert j["local_only"] is True
    assert j["host"] == "127.0.0.1"
    assert isinstance(j["uptime"], (int, float))
    assert j["running"] is False


def test_config_get(client):
    j = client.get("/api/config").get_json()
    # 公开仓库不内置真实联系人：默认值为空，由用户在控制台填写
    assert isinstance(j["TARGET_WXID"], str)
    assert "TYPE_THINK_DELAY" in j and len(j["TYPE_THINK_DELAY"]) == 2


def test_status_when_idle(client):
    j = client.get("/api/status").get_json()
    assert j["running"] is False
    assert j["local_only"] is True


def test_stop_when_idle_is_ok(client):
    j = client.post("/api/stop").get_json()
    assert j["ok"] is True
    assert j["running"] is False


def test_unknown_route_returns_json_404(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.get_json()["error"]


def test_method_not_allowed_returns_json_405(client):
    r = client.delete("/api/health")
    assert r.status_code == 405
    assert r.get_json()["error"]


def test_config_validation_rejects_bad_payload(client):
    # 非法的停顿范围（下限>上限）应在写入前被拒绝，不落盘
    r = client.post(
        "/api/config",
        json={"TYPE_THINK_DELAY": [5, 1]},
    )
    assert r.status_code == 400
    assert "TYPE_THINK_DELAY" in r.get_json()["error"]


def test_non_loopback_request_is_rejected(client):
    """模拟非本机来源地址：必须 403（本地专用强制）"""
    r = client.get("/api/health", environ_overrides={"REMOTE_ADDR": "8.8.8.8"})
    assert r.status_code == 403
    assert r.get_json()["error"]
