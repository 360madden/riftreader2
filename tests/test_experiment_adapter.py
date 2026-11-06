"""The obsolete adapter cannot load or invoke legacy operational modules."""
import json
from pathlib import Path
import subprocess
import sys
import unittest


class RetiredAdapterTests(unittest.TestCase):
    def test_old_invocation_fails_closed_with_rr2_replacement(self):
        script = Path(__file__).parents[1] / 'scripts' / 'rift-experiment.py'
        result = subprocess.run([sys.executable, str(script), '--reference', 'missing', 'run'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        message = json.loads(result.stderr)
        self.assertEqual(message['status'], 'retired')
        self.assertIn('ensure_controller.py', message['replacement'])


if __name__ == '__main__':
    unittest.main()
