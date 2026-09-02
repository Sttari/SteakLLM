import httpx

from steakllm_common.health import start_probe_server


def test_probes_reflect_readiness():
    state = {"ready": False}
    server = start_probe_server(0, lambda: state["ready"])  # port 0 = any free port
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert httpx.get(f"{base}/healthz").status_code == 200
        assert httpx.get(f"{base}/readyz").status_code == 503
        state["ready"] = True
        assert httpx.get(f"{base}/readyz").status_code == 200
        assert httpx.get(f"{base}/other").status_code == 404
    finally:
        server.shutdown()


def test_a_throwing_readiness_check_means_not_ready():
    def boom():
        raise ConnectionError("kafka unreachable")

    server = start_probe_server(0, boom)
    try:
        r = httpx.get(f"http://127.0.0.1:{server.server_address[1]}/readyz")
        assert r.status_code == 503
    finally:
        server.shutdown()
