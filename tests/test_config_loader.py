import tempfile
import textwrap
import unittest
from pathlib import Path

from api_test_framework.config_loader import SpecValidationError, load_test_spec


class ConfigLoaderTests(unittest.TestCase):
    def _write_spec(self, content: str) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        tmp.write(textwrap.dedent(content))
        tmp.flush()
        tmp.close()
        path = Path(tmp.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_load_valid_spec(self) -> None:
        path = self._write_spec(
            """
            base_url: "http://127.0.0.1:5000"
            endpoints:
              transfer:
                method: POST
                path: /transfer
                body:
                  from: A
                  to: B
                  amount: 100
            """
        )

        spec = load_test_spec(path)
        self.assertEqual(spec.base_url, "http://127.0.0.1:5000")
        self.assertIn("transfer", spec.endpoints)
        self.assertEqual(spec.endpoints["transfer"].method, "POST")

    def test_rejects_invalid_method(self) -> None:
        path = self._write_spec(
            """
            base_url: "http://127.0.0.1:5000"
            endpoints:
              transfer:
                method: PATCH
                path: /transfer
            """
        )

        with self.assertRaises(SpecValidationError):
            load_test_spec(path)


if __name__ == "__main__":
    unittest.main()
