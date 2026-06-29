from src.platform.store.db import payload_hash


def test_payload_hash_deterministic():
    a = payload_hash(b'{"x": 1}')
    b = payload_hash(b'{"x": 1}')
    assert a == b
    assert payload_hash(b'{"x": 2}') != a
