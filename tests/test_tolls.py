import unittest
from app.tolls import detect_toll_passes, point_segment_distance_meters


class TollDetectionTests(unittest.TestCase):
    def setUp(self):
        self.toll = {'id': 7, 'name': 'Peaje prueba', 'latitude': -34.0, 'longitude': -56.0, 'price': None, 'active': True}

    def test_near_segment_counts_once_per_service_segment(self):
        routes = [
            {'label': 'Salida móvil → origen', 'coordinates': [[-56.01,-34.0],[-55.99,-34.0]]},
            {'label': 'Origen → destino', 'coordinates': [[-56.02,-34.0],[-55.98,-34.0]]},
        ]
        passes = detect_toll_passes(routes, [self.toll], 416)
        self.assertEqual([(item['segment'], item['price']) for item in passes], [('Salida móvil → origen',416.0),('Origen → destino',416.0)])

    def test_far_or_inactive_station_is_not_counted(self):
        route = [{'label':'Origen → destino','coordinates':[[-56.01,-34.0],[-55.99,-34.0]]}]
        far = dict(self.toll, latitude=-34.01)
        inactive = dict(self.toll, active=False)
        self.assertEqual(detect_toll_passes(route,[far,inactive],416),[])

    def test_station_on_opposite_carriageway_within_300_meters_is_counted(self):
        route = [{'label':'Origen → destino','coordinates':[[-56.01,-34.0],[-55.99,-34.0]]}]
        opposite_carriageway = dict(self.toll, latitude=-34.002)
        self.assertEqual(len(detect_toll_passes(route,[opposite_carriageway],416)),1)

    def test_point_to_segment_distance_is_symmetric(self):
        forward=point_segment_distance_meters(-34,-56,[ -56.01,-34],[-55.99,-34])
        reverse=point_segment_distance_meters(-34,-56,[-55.99,-34],[-56.01,-34])
        self.assertAlmostEqual(forward,reverse,places=6)
