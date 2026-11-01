import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[2] / 'quickshell/.config/quickshell/labfy-sway/systemmonitor/backend.py'
spec = importlib.util.spec_from_file_location('monitor_backend', path)
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class BackendTests(unittest.TestCase):
    def test_cpu_excludes_guest_double_count(self):
        data = 'cpu 10 2 3 20 1 4 5 6 7 8\ncpu0 1 2 3 4 5 6 7 8 9 10\n'
        self.assertEqual(backend.cpu_ticks(data)['cpu'], [51, 21])

    def test_mem_available_and_swap(self):
        d = backend.meminfo('MemTotal: 100 kB\nMemFree: 2 kB\nMemAvailable: 40 kB\nCached: 20 kB\nSwapTotal: 10 kB\nSwapFree: 3 kB')
        self.assertEqual(d['used'], 60 * 1024)
        self.assertEqual(d['swapUsed'], 7 * 1024)

    def test_psi_and_missing(self):
        d = backend.psi('some avg10=1.25 avg60=2.50 avg300=3.75 total=9\nfull avg10=0.01 avg60=0.02 avg300=0.03 total=2')
        self.assertEqual(d['some'], [1.25, 2.5, 3.75])
        self.assertIsNone(backend.psi('')['full'])

    def test_zram_and_frequency(self):
        self.assertEqual(backend.zram('100 40 48 0 0')['ratio'], 2.5)
        self.assertIsNone(backend.zram(''))
        self.assertEqual(backend.gpu_frequency('0: 400Mhz\n1: 1200Mhz *'), 1200)
        self.assertIsNone(backend.gpu_frequency(''))


if __name__ == '__main__':
    unittest.main()
