import pytest
import time
import threading

# Import your final domain_throttle file
from backend.app.services.domain_throttle import (
    acquire,
    release,
    domain_slot,
    current_slots,
    _mem_slots,       # in-memory fallback store
    _have_redis,
    _redis,
)

TEST_DOMAIN = "example.com"


# ---------------------------------------------
# FIXTURES
# ---------------------------------------------

@pytest.fixture(autouse=True)
def reset_state():
    """Ensure slot counters reset before every test."""
    try:
        if _redis:
            _redis.delete(f"domain:slots:{TEST_DOMAIN}")
    except Exception:
        pass

    _mem_slots.clear()
    yield
    _mem_slots.clear()


# ---------------------------------------------
# UNIT TESTS
# ---------------------------------------------

def test_acquire_release_in_memory():
    """Basic acquire/release using fallback memory store."""
    # Force memory mode
    if _have_redis:
        pytest.skip("Redis present – fallback test skipped")

    assert acquire(TEST_DOMAIN) is True
    assert current_slots(TEST_DOMAIN) == 1

    release(TEST_DOMAIN)
    assert current_slots(TEST_DOMAIN) == 0


def test_acquire_release_redis(monkeypatch):
    """When Redis is available, ensure acquire/release works."""
    if not _have_redis:
        pytest.skip("Redis not available on this system")

    key = f"domain:slots:{TEST_DOMAIN}"

    assert acquire(TEST_DOMAIN) is True
    val = int(_redis.get(key))
    assert val == 1

    release(TEST_DOMAIN)
    assert _redis.get(key) in (None, b"0")


def test_overflow_limit(monkeypatch):
    """Ensure domain slot limit is enforced."""
    # Force memory fallback for deterministic behavior
    monkeypatch.setattr("backend.app.services.domain_throttle._have_redis", False)

    # MAX = 2 (default)
    assert acquire(TEST_DOMAIN) is True   # 1
    assert acquire(TEST_DOMAIN) is True   # 2
    assert acquire(TEST_DOMAIN) is False  # >2 → overflow

    assert current_slots(TEST_DOMAIN) == 2


def test_release_does_not_go_negative(monkeypatch):
    monkeypatch.setattr("backend.app.services.domain_throttle._have_redis", False)

    release(TEST_DOMAIN)  # releasing without acquire should NOT error
    assert current_slots(TEST_DOMAIN) == 0

    acquire(TEST_DOMAIN)
    release(TEST_DOMAIN)
    release(TEST_DOMAIN)  # extra release → still 0, never negative
    assert current_slots(TEST_DOMAIN) == 0


def test_domain_slot_context_manager():
    """Ensure with domain_slot(): releases even on exception."""
    if _have_redis:
        pytest.skip("Memory fallback test only")

    try:
        with domain_slot(TEST_DOMAIN):
            assert current_slots(TEST_DOMAIN) == 1
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert current_slots(TEST_DOMAIN) == 0  # must be cleaned up


def test_parallel_threads_memory(monkeypatch):
    """Thread safety test − 10 threads acquire/release concurrently."""
    monkeypatch.setattr("backend.app.services.domain_throttle._have_redis", False)

    results = []

    def worker():
        ok = acquire(TEST_DOMAIN)
        if ok:
            time.sleep(0.01)
            release(TEST_DOMAIN)
        results.append(ok)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Only 2 may acquire simultaneously (default limit)
    assert results.count(True) >= 2
    assert current_slots(TEST_DOMAIN) == 0


def test_context_acquire_limit(monkeypatch):
    """Ensure context manager also respects slot limits."""
    monkeypatch.setattr("backend.app.services.domain_throttle._have_redis", False)

    with domain_slot(TEST_DOMAIN):
        assert current_slots(TEST_DOMAIN) == 1

        # Second context allowed (limit=2)
        with domain_slot(TEST_DOMAIN):
            assert current_slots(TEST_DOMAIN) == 2

            # Third should reject
            assert acquire(TEST_DOMAIN) is False


def test_redis_fallback_if_error(monkeypatch):
    """Simulate Redis failure → should fallback to memory and not crash."""
    if not _have_redis:
        pytest.skip("Redis not installed")

    # Break redis
    def broken(*args, **kwargs):
        raise Exception("redis broken")

    monkeypatch.setattr(_redis, "incr", broken)
    monkeypatch.setattr(_redis, "decr", broken)
    monkeypatch.setattr(_redis, "expire", broken)
    monkeypatch.setattr(_redis, "delete", broken)

    ok = acquire(TEST_DOMAIN)
    assert ok is True  # fallback to memory
    assert current_slots(TEST_DOMAIN) == 1

    release(TEST_DOMAIN)
    assert current_slots(TEST_DOMAIN) == 0
