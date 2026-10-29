import unittest
from datetime import date

from expreso_bridge.overdue import is_overdue

TODAY = date(2026, 10, 3)


def make_shipment(status, estimated_delivery):
    return {"tracking_id": "AND1", "external_ref": "R-1", "status": status, "estimated_delivery": estimated_delivery}


class IsOverdueTest(unittest.TestCase):
    def test_undelivered_shipments_past_their_estimated_date_are_overdue(self):
        for status in ["CREATED", "IN_TRANSIT", "EXCEPTION"]:
            with self.subTest(status=status):
                self.assertTrue(is_overdue(make_shipment(status, "2026-10-02"), TODAY))

    def test_delivered_shipments_are_never_overdue(self):
        self.assertFalse(is_overdue(make_shipment("DELIVERED", "2026-10-01"), TODAY))

    def test_shipments_due_today_or_later_are_not_overdue_yet(self):
        for estimated_delivery in ["2026-10-03", "2026-10-05"]:
            with self.subTest(estimated_delivery=estimated_delivery):
                self.assertFalse(is_overdue(make_shipment("IN_TRANSIT", estimated_delivery), TODAY))


if __name__ == "__main__":
    unittest.main()
