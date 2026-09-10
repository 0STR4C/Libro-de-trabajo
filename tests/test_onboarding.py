import unittest
from tools.user_onboarding.import_users import validate_roster


class OnboardingTests(unittest.TestCase):
    def test_corporate_normalization(self):
        row=validate_roster([dict(name=' Persona Prueba ',email=' PRUEBA@PORTOSERVICIOS.COM.UY ')])[0]
        self.assertEqual(row,dict(name='Persona Prueba',email='prueba@portoservicios.com.uy',username='prueba'))

    def test_invalid_and_duplicate(self):
        for value in ([],{},[dict(name='Persona',email='x@example.com')],[dict(name='Persona',email='x@portoservicios.com.uy')]*2):
            with self.assertRaises(ValueError):validate_roster(value)
