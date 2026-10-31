"""验证公开统计口径与SVG转义，不访问网络。"""
import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location('stats', Path(__file__).resolve().parents[1]/'scripts/generate_stats.py')
stats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stats)


class StatsTests(unittest.TestCase):
    def fixture(self):
        return {'username': 'Dengzi555', 'updated_at': '2026-10-31T12:00:00+08:00',
                'pull_requests': [], 'repositories': []}

    def test_zero_is_valid_and_svg_supports_both_themes(self):
        data = self.fixture()
        self.assertEqual(stats.summarize(data)['total'], 0)
        for dark in (False, True):
            image = stats.render(data, dark)
            ET.fromstring(image)
            self.assertIn('暂无已合并的公开 PR', image)

    def test_china_day_boundary_recent_window_and_external_count(self):
        data = self.fixture()
        data['pull_requests'] = [
            {'repository': 'Dengzi555/example', 'number': 1, 'merged_at': '2026-10-01T16:00:00Z'},
            {'repository': 'other/example', 'number': 2, 'merged_at': '2026-10-01T15:59:59Z'},
            {'repository': 'other/example', 'number': 3, 'merged_at': '2026-10-30T16:00:00Z'}]
        data['repositories'] = [{'name': 'Dengzi555/example', 'stars': 1}, {'name': 'other/example', 'stars': 12}]
        result = stats.summarize(data)
        self.assertEqual(result['total'], 3)
        self.assertEqual(result['external'], 2)
        self.assertEqual(result['recent'], 2)
        self.assertEqual(result['repos'][0]['name'], 'other/example')
        ET.fromstring(stats.render(data))

    def test_svg_escapes_text_and_caps_busy_day_points(self):
        data = self.fixture()
        data['username'] = 'A&B'
        data['pull_requests'] = [{'repository': 'other/example', 'number': i, 'merged_at': '2026-10-31T00:00:00Z'} for i in range(20)]
        data['repositories'] = [{'name': 'other/example', 'stars': 2000}]
        image = stats.render(data)
        ET.fromstring(image)
        self.assertIn('A&amp;B', image)
        self.assertEqual(image.count('<circle '), 6)


if __name__ == '__main__':
    unittest.main()
