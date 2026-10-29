import socket
import unittest
from http.client import IncompleteRead

from expreso_bridge.client import ApiUnavailable, AuthenticationError, ExpresoClient


class ScriptedClient(ExpresoClient):
    """Replaces the network with a fixed sequence of (status, body) responses."""

    def __init__(self, responses, **options):
        super().__init__("http://api.test", "key", sleep=self._record_sleep, **options)
        self._responses = list(responses)
        self.sleeps = []
        self.calls = 0

    def _send(self, method, path, payload):
        self.calls += 1
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def _record_sleep(self, seconds):
        self.sleeps.append(seconds)


class RetryTest(unittest.TestCase):
    def test_retries_transient_errors_with_exponential_backoff(self):
        client = ScriptedClient([(503, {}), (503, {}), (201, {"tracking_id": "AND1"})])

        response = client.create_shipment({"external_ref": "R-1"})

        self.assertEqual((response.status, response.attempts), (201, 3))
        self.assertEqual(client.sleeps, [0.5, 1.0])

    def test_returns_the_last_transient_response_when_attempts_run_out(self):
        client = ScriptedClient([(500, {})] * 4)

        response = client.create_shipment({"external_ref": "R-1"})

        self.assertEqual((response.status, response.attempts), (500, 4))

    def test_retries_a_response_cut_off_mid_transfer(self):
        client = ScriptedClient([IncompleteRead(b""), (201, {"tracking_id": "AND1"})])

        response = client.create_shipment({"external_ref": "R-1"})

        self.assertEqual((response.status, response.attempts), (201, 2))

    def test_does_not_retry_client_errors(self):
        client = ScriptedClient([(422, {"error": "validation_error"})])

        response = client.create_shipment({"external_ref": "R-1"})

        self.assertEqual((response.status, client.calls), (422, 1))

    def test_stops_on_invalid_api_key(self):
        client = ScriptedClient([(401, {"error": "unauthorized"})])

        with self.assertRaises(AuthenticationError):
            client.create_shipment({"external_ref": "R-1"})


class ConnectionTest(unittest.TestCase):
    def test_raises_api_unavailable_when_nobody_is_listening(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            free_port = probe.getsockname()[1]
        client = ExpresoClient(
            f"http://127.0.0.1:{free_port}", "key", max_attempts=2, sleep=lambda _: None
        )

        with self.assertRaises(ApiUnavailable):
            client.list_provinces()


if __name__ == "__main__":
    unittest.main()
