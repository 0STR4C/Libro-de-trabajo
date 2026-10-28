import unittest
import json
from unittest.mock import patch

from app.identity import GoogleMapsRedirectHandler, allowed_maps_url, parse_coordinates
from app.quote_geography import REGIONAL_PRICE_MESSAGE, is_uruguay_point, require_near_road, require_uruguay_points, require_uruguay_route
from app.quote_geocoding import GeocodingUnavailable, normalize_photon_results, search_address


class QuoteGeographyTests(unittest.TestCase):
    def test_coordinates_from_uruguay_argentina_and_brazil_are_parsed(self):
        examples = [
            ("-34.9011, -56.1645", (-34.9011, -56.1645)),
            ("-34.6037, -58.3816", (-34.6037, -58.3816)),
            ("-23.5505, -46.6333", (-23.5505, -46.6333)),
        ]
        for source, expected in examples:
            self.assertEqual(parse_coordinates(source), expected)
        self.assertTrue(is_uruguay_point(*examples[0][1]))
        self.assertFalse(is_uruguay_point(*examples[1][1]))
        self.assertFalse(is_uruguay_point(*examples[2][1]))

    def test_google_maps_regional_links_follow_only_google_hosts(self):
        class Response:
            def geturl(self): return "https://www.google.com/maps/@-34.9011,-56.1645,17z"
            def __enter__(self): return self
            def __exit__(self, *_): pass
        class Opener:
            def open(self, *_args, **_kwargs): return Response()
        for host in ("www.google.com.ar", "www.google.com.br", "maps.google.com.uy"):
            with patch("app.identity.build_opener", return_value=Opener()) as opener:
                self.assertEqual(parse_coordinates(f"https://{host}/maps/place/ejemplo"), (-34.9011, -56.1645))
                opener.assert_called_once()
        with patch("app.identity.build_opener") as opener:
            with self.assertRaises(ValueError):
                parse_coordinates("https://notgoogle.com/maps/place/ejemplo")
            opener.assert_not_called()

    def test_maps_redirect_cannot_reach_an_internal_or_non_google_host(self):
        handler = GoogleMapsRedirectHandler()
        for target in ("http://127.0.0.1/admin", "https://localhost/admin",
                       "https://google.com.evil.example/maps", "http://www.google.com/maps",
                       "https://www.google.com:8443/maps"):
            self.assertFalse(allowed_maps_url(target))
            with self.assertRaises(ValueError):
                handler.redirect_request(None, None, 302, "Found", {}, target)
        self.assertTrue(allowed_maps_url("https://maps.google.com.uy/maps"))

    def test_route_crossing_border_is_not_priced_even_with_uruguayan_endpoints(self):
        route = {"coordinates": [[-56.1645, -34.9011], [-58.3816, -34.6037], [-56.1645, -34.9011]]}
        with self.assertRaisesRegex(ValueError, "tarifa regional"):
            require_uruguay_route(route)
        self.assertIn("no se guardó un precio", REGIONAL_PRICE_MESSAGE)

    def test_capture_destination_is_rejected_before_routing_as_far_from_road(self):
        origin = parse_coordinates("-34.813803, -55.238921")
        destination = parse_coordinates("-33.979809, -58.382095")
        self.assertTrue(is_uruguay_point(*origin))
        self.assertFalse(is_uruguay_point(*destination))
        self.assertTrue(is_uruguay_point(-33.957245, -58.356012))
        nearest = lambda point: {"distance": 3474.786778, "location": [-58.356012, -33.957245]}
        with self.assertRaisesRegex(ValueError, "Destino: ubicación en agua o sin vía cercana.*3.47 km"):
            require_uruguay_points(origin, destination, nearest=nearest)

    def test_coast_border_and_foreign_points_remain_conservative(self):
        self.assertTrue(is_uruguay_point(-34.9011, -56.1645))  # interior urbano
        self.assertTrue(is_uruguay_point(-33.95, -58.35))  # costa cercana al destino rechazado
        self.assertFalse(is_uruguay_point(-33.979809, -58.382095))
        self.assertFalse(is_uruguay_point(-34.6037, -58.3816))  # Argentina
        with self.assertRaisesRegex(ValueError, "Destino: punto fuera del territorio tarifado"):
            require_uruguay_points((-34.9011, -56.1645), (-34.6037, -58.3816))

    def test_osrm_snapping_far_from_road_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "3475 m"):
            require_near_road({"waypoints": [{"distance": 60, "location": [-55.23957, -34.81366]}, {"distance": 3474.786778, "location": [-58.356012, -33.957245]}]})

    def test_ambiguous_street_results_keep_locality_state_and_country(self):
        def feature(city, state, lat, lon):
            return {"properties": {"street": "San Martín", "housenumber": "100", "city": city, "state": state, "countrycode": "AR"}, "geometry": {"coordinates": [lon, lat]}}
        options = normalize_photon_results({"features": [feature("Buenos Aires", "Buenos Aires", -34.6, -58.4), feature("Rosario", "Santa Fe", -32.9, -60.7)]})
        self.assertEqual(len(options), 2)
        self.assertNotEqual(options[0]["label"], options[1]["label"])
        self.assertIn("Argentina", options[0]["label"])
        self.assertIn("Santa Fe", options[1]["label"])

    def test_geocoder_uses_configured_endpoint_and_filters_countries(self):
        payload = {"features": [
            {"properties": {"name": "Montevideo", "countrycode": "UY"}, "geometry": {"coordinates": [-56.1645, -34.9011]}},
            {"properties": {"name": "Santiago", "countrycode": "CL"}, "geometry": {"coordinates": [-70.67, -33.45]}},
        ]}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self, _limit): return json.dumps(payload).encode()
        with patch.dict("os.environ", {"APP_ENV": "production", "GEOCODER_URL": "https://geocoder.example"}), patch("app.quote_geocoding.urlopen", return_value=Response()) as request:
            results = search_address("Montevideo")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["country_code"], "UY")
        self.assertEqual(request.call_args.kwargs["timeout"], 5)
        self.assertIn("countrycode=BR", request.call_args.args[0].full_url)
        self.assertNotIn("lang=es", request.call_args.args[0].full_url)

    def test_geocoder_country_and_intersection_query(self):
        payload = {"features": [{"properties": {"name": "18 de Julio y Ejido", "city": "Montevideo", "state": "Montevideo", "countrycode": "UY"}, "geometry": {"coordinates": [-56.18, -34.90]}}]}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self, _limit): return json.dumps(payload).encode()
        with patch.dict("os.environ", {"APP_ENV": "production", "GEOCODER_URL": "https://geocoder.example"}), patch("app.quote_geocoding.urlopen", return_value=Response()) as request:
            results = search_address("18 de Julio y Ejido, Montevideo", "UY")
        self.assertIn("Montevideo, Uruguay", results[0]["label"])
        self.assertIn("countrycode=UY", request.call_args.args[0].full_url)
        self.assertNotIn("countrycode=AR", request.call_args.args[0].full_url)

    def test_production_without_provider_fails_explicitly(self):
        with patch.dict("os.environ", {"APP_ENV": "production", "GEOCODER_URL": ""}):
            with self.assertRaises(GeocodingUnavailable):
                search_address("Montevideo")


if __name__ == "__main__":
    unittest.main()
