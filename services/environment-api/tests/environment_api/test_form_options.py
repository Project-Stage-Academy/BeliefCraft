import json

from environment_api.api import form_options as form_options_module


class FakeCache:
    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self.store = dict(initial or {})
        self.set_calls: list[tuple[str, int, str]] = []

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        self.store[key] = value
        self.set_calls.append((key, ttl_seconds, value))
        return True


def test_form_options_returns_cached_payload(client, monkeypatch) -> None:
    cached_payload = {
        "origins": ["Origin A"],
        "destinations": ["Destination A"],
        "products": [{"name": "Prod A", "category": "Cat A"}],
        "transport_modes": ["air"],
    }
    cache = FakeCache({"form-options": json.dumps(cached_payload)})
    monkeypatch.setattr(form_options_module, "get_cache_client", lambda: cache)
    monkeypatch.setattr(
        form_options_module,
        "load_form_options_from_db",
        lambda session: (_ for _ in ()).throw(AssertionError("DB loader called")),
    )

    response = client.get("/api/v1/form-options")

    assert response.status_code == 200
    assert response.json() == cached_payload


def test_form_options_populates_cache_on_miss(client, monkeypatch, seed_base_world) -> None:
    cache = FakeCache()
    monkeypatch.setattr(form_options_module, "get_cache_client", lambda: cache)

    response = client.get("/api/v1/form-options")

    assert response.status_code == 200
    body = response.json()
    assert seed_base_world["warehouse"].name in body["origins"]
    assert seed_base_world["supplier"].name in body["origins"]
    assert seed_base_world["warehouse"].name in body["destinations"]
    assert body["products"]
    assert body["transport_modes"]
    assert cache.set_calls


def test_invalid_cache_payload_falls_back_to_db(client, monkeypatch, seed_base_world) -> None:
    cache = FakeCache({"form-options": "not-json"})
    monkeypatch.setattr(form_options_module, "get_cache_client", lambda: cache)

    response = client.get("/api/v1/form-options")

    assert response.status_code == 200
    body = response.json()
    assert seed_base_world["warehouse"].name in body["destinations"]
    assert cache.set_calls
