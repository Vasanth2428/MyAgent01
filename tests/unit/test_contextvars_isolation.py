import contextvars
import threading

from src.core.model_provider import active_model_provider, active_model_name


def test_contextvars_default_unset():
    assert active_model_provider.get() is None
    assert active_model_name.get() is None


def test_contextvars_set_and_reset_reverts_to_default():
    token_provider = active_model_provider.set("openai")
    token_name = active_model_name.set("gpt-4o")
    assert active_model_provider.get() == "openai"
    assert active_model_name.get() == "gpt-4o"
    active_model_provider.reset(token_provider)
    active_model_name.reset(token_name)
    assert active_model_provider.get() is None
    assert active_model_name.get() is None


def test_contextvars_request_isolation_same_thread():
    active_model_provider.set(None)
    active_model_name.set(None)

    token1 = active_model_provider.set("provider_a")
    active_model_name.set("model_a")
    assert active_model_provider.get() == "provider_a"
    assert active_model_name.get() == "model_a"

    active_model_provider.reset(token1)
    active_model_name.set(None)
    assert active_model_provider.get() is None
    assert active_model_name.get() is None


def test_contextvars_thread_isolation():
    active_model_provider.set(None)
    active_model_name.set(None)

    errors = []

    def worker():
        try:
            active_model_provider.set("thread_provider")
            active_model_name.set("thread_model")
            assert active_model_provider.get() == "thread_provider"
            assert active_model_name.get() == "thread_model"
        except Exception as e:
            errors.append(e)

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert not errors
    assert active_model_provider.get() is None
    assert active_model_name.get() is None


def test_contextvars_nested_set_does_not_leak():
    token_outer_provider = active_model_provider.set("outer")
    token_outer_name = active_model_name.set("outer_model")
    assert active_model_provider.get() == "outer"
    assert active_model_name.get() == "outer_model"

    token_inner = active_model_provider.set("inner")
    active_model_name.set("inner_model")
    assert active_model_provider.get() == "inner"
    assert active_model_name.get() == "inner_model"

    active_model_provider.reset(token_inner)
    active_model_name.reset(token_outer_name)
    assert active_model_provider.get() == "outer"
    assert active_model_name.get() == "outer_model"

    active_model_provider.reset(token_outer_provider)
    assert active_model_provider.get() is None
    assert active_model_name.get() is None
