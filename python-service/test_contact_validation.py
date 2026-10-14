import unittest
from pydantic import ValidationError
from contact_validation import validate_phone, validate_instagram
from account_auth import Register, Profile
from shared_data import validate_contact_changes
from fastapi import HTTPException


class ContactValidationTests(unittest.TestCase):
    def test_phone_formats(self):
        for value in ["11987654321", "11999999999", "(11) 3333-3333", "(81) 3456-7890", "+55 (81) 98765-4321", "+1 415 555 2671"]:
            self.assertEqual(validate_phone(value), value)
        for value in ["32132132131", "abc11987654321", "@maria", "00123456789", "119876543210", "+551198765432100", "１１９８７６５４３２１"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_phone(value)

    def test_instagram_identifiers(self):
        for value in ["@maria.loja", "loja_81", "@12345", "", None, "—"]:
            self.assertEqual(validate_instagram(value), value)
        for value in ["11987654321", "https://instagram.com/maria", "@maria loja", "@maria..loja"]:
            with self.assertRaises(ValueError):
                validate_instagram(value)

    def test_account_and_crm_reject_invalid_contact(self):
        with self.assertRaises(ValidationError):
            Register(nome="Maria", email="maria@example.com", senha="Valid-password-123!", convite="a" * 64, telefone="@maria")
        with self.assertRaises(ValidationError):
            Profile(nome="Maria", telefone="32132132131")
        for payload in [{"telefone": "32132132131"}, {"instagram": "11987654321"}]:
            with self.assertRaises(HTTPException) as error:
                validate_contact_changes(payload)
            self.assertEqual(error.exception.status_code, 422)
        validate_contact_changes({"nome": "Maria"})
        for value in ["@maria", "32132132131", 123]:
            with self.assertRaises(ValidationError):
                Profile(configuracao_negocio={"telefone": value})
        self.assertEqual(Profile(configuracao_negocio={"horario": "9–18"}).configuracao_negocio, {"horario": "9–18"})
        self.assertEqual(Profile(telefone=None).telefone, None)


if __name__ == "__main__":
    unittest.main()
