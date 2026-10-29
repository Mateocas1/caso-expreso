import unittest

from expreso_bridge.remitos import (
    InvalidRemito,
    build_province_lookup,
    is_andino,
    parse_decimal,
    to_shipment,
)

OFFICIAL_PROVINCES = [
    "Buenos Aires",
    "Ciudad Autónoma de Buenos Aires",
    "Córdoba",
    "Neuquén",
    "Tucumán",
]


def make_remito(**overrides):
    remito = {
        "nro_remito": "R-1",
        "destinatario": {
            "razon_social": "Ferretería El Tornillo",
            "direccion": "Av. San Martín 1234",
            "localidad": "San Isidro",
            "provincia": "Buenos Aires",
            "codigo_postal": "1642",
            "telefono": "1145678901",
        },
        "bultos": 3,
        "peso_kg": 25.4,
        "valor_declarado": 150000.0,
        "transportista": "EXPRESO ANDINO",
        "servicio": "NORMAL",
    }
    remito.update(overrides)
    return remito


class IsAndinoTest(unittest.TestCase):
    def test_accepts_every_spelling_found_in_the_export(self):
        spellings = [
            "EXPRESO ANDINO",
            "Expreso Andino",
            "EXPRESO ANDINO ",
            "Exp. Andino",
            "expreso andino",
        ]
        for carrier in spellings:
            with self.subTest(carrier=carrier):
                self.assertTrue(is_andino(make_remito(transportista=carrier)))

    def test_rejects_other_carriers(self):
        for carrier in ["Cruz del Norte", "RETIRA CLIENTE", "TRANSPORTE LITORAL", "", None]:
            with self.subTest(carrier=carrier):
                self.assertFalse(is_andino(make_remito(transportista=carrier)))


class ParseDecimalTest(unittest.TestCase):
    def test_parses_numbers_and_decimal_comma_strings(self):
        self.assertEqual(parse_decimal(25.4), 25.4)
        self.assertEqual(parse_decimal(30), 30.0)
        self.assertEqual(parse_decimal("145,1"), 145.1)

    def test_rejects_values_it_cannot_read_unambiguously(self):
        for value in ["1.234,5", "abc", "", "nan", "inf", float("nan"), None, True]:
            with self.subTest(value=value):
                self.assertIsNone(parse_decimal(value))


class ToShipmentTest(unittest.TestCase):
    def setUp(self):
        self.provinces = build_province_lookup(OFFICIAL_PROVINCES)

    def test_maps_every_field_to_the_api_format(self):
        self.assertEqual(
            to_shipment(make_remito(), self.provinces),
            {
                "external_ref": "R-1",
                "recipient": {
                    "name": "Ferretería El Tornillo",
                    "street": "Av. San Martín 1234",
                    "city": "San Isidro",
                    "province": "Buenos Aires",
                    "zip_code": "1642",
                    "phone": "1145678901",
                },
                "packages": 3,
                "weight_kg": 25.4,
                "declared_value": 150000.0,
                "service": "standard",
            },
        )

    def test_maps_province_variants_to_official_names(self):
        expected_by_raw = {
            "BA": "Buenos Aires",
            "Bs. As.": "Buenos Aires",
            "CABA": "Ciudad Autónoma de Buenos Aires",
            "Capital Federal": "Ciudad Autónoma de Buenos Aires",
            "Cba": "Córdoba",
            "Tucuman": "Tucumán",
            "Neuquen": "Neuquén",
        }
        for raw, official in expected_by_raw.items():
            with self.subTest(raw=raw):
                remito = make_remito()
                remito["destinatario"]["provincia"] = raw
                recipient = to_shipment(remito, self.provinces)["recipient"]
                self.assertEqual(recipient["province"], official)

    def test_maps_urgent_service_to_express(self):
        shipment = to_shipment(make_remito(servicio="URGENTE"), self.provinces)
        self.assertEqual(shipment["service"], "express")

    def test_trims_text_and_omits_empty_phone(self):
        remito = make_remito()
        remito["destinatario"]["direccion"] = "  "
        remito["destinatario"]["telefono"] = ""
        recipient = to_shipment(remito, self.provinces)["recipient"]
        self.assertEqual(recipient["street"], "")
        self.assertNotIn("phone", recipient)

    def test_reports_every_unmappable_field_at_once(self):
        remito = make_remito(peso_kg="mucho", servicio="EN MANO")
        remito["destinatario"]["provincia"] = "Narnia"
        with self.assertRaises(InvalidRemito) as raised:
            to_shipment(remito, self.provinces)
        self.assertEqual(
            raised.exception.problems,
            [
                "provincia desconocida: 'Narnia'",
                "peso inválido: 'mucho'",
                "servicio desconocido: 'EN MANO'",
            ],
        )


if __name__ == "__main__":
    unittest.main()
