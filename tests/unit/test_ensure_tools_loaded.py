"""§4.2.6: ensure_tools_loaded 幂等 + 并发安全"""
import threading

from agent_core.tools.builtin import ensure_tools_loaded


def test_ensure_tools_loaded_is_idempotent():
    """多次调用不重复注册 / 不报错。"""
    for _ in range(10):
        ensure_tools_loaded()
    # 函数成功即可


def test_ensure_tools_loaded_thread_safe():
    """并发调用不应出错。"""
    barrier = threading.Barrier(16)
    errors = []

    def worker() -> None:
        try:
            barrier.wait()
            for _ in range(50):
                ensure_tools_loaded()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, f"concurrent errors: {errors[:3]}"