"""Runs the upload against the kit's mock API with the real export."""
import socket
import subprocess
import sys
import time
import unittest
from collections import Counter
from pathlib import Path

from expreso_bridge.client import ExpresoClient
from expreso_bridge.remitos import is_andino, load_remitos
from expreso_bridge.upload import Outcome, upload_remitos

KIT_DIR = Path(__file__).resolve().parent.parent / "kit"
API_KEY = "andino-test-7f3a91"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _wait_until_listening(port: int, timeout_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"mock API did not start on port {port}")


class UploadAgainstMockApiTest(unittest.TestCase):
    def setUp(self):
        port = _free_port()
        self.server = subprocess.Popen(
            [sys.executable, str(KIT_DIR / "expreso_api.py"), str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(self.server.wait)
        self.addCleanup(self.server.terminate)
        _wait_until_listening(port)
        self.client = ExpresoClient(f"http://127.0.0.1:{port}", API_KEY, sleep=lambda _: None)
        remitos = load_remitos(KIT_DIR / "remitos_2026-09-30.json")
        self.andino_remitos = [remito for remito in remitos if is_andino(remito)]

    def test_first_run_uploads_every_valid_remito(self):
        results = upload_remitos(self.andino_remitos, self.client)

        self.assertEqual(
            Counter(result.outcome for result in results),
            Counter({
                Outcome.CREATED: 19,
                Outcome.ALREADY_EXISTS: 1,
                Outcome.DUPLICATE: 1,
                Outcome.REJECTED: 3,
            }),
        )

    def test_second_run_creates_nothing_new(self):
        first_run = upload_remitos(self.andino_remitos, self.client)
        second_run = upload_remitos(self.andino_remitos, self.client)

        tracking_by_remito = {r.remito_number: r.tracking_id for r in first_run if r.tracking_id}
        self.assertNotIn(Outcome.CREATED, {result.outcome for result in second_run})
        for result in second_run:
            if result.outcome is Outcome.ALREADY_EXISTS:
                self.assertEqual(result.tracking_id, tracking_by_remito[result.remito_number])


if __name__ == "__main__":
    unittest.main()
