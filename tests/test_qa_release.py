import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.qa_release import EXPECTED_ARCHIVE, create_zip


class ReleaseArchiveTests(unittest.TestCase):
    def test_zip_keeps_required_output_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            output.mkdir()
            for number in range(1, 51):
                case_id = f"EC_{number:03d}"
                (output / f"{case_id}.json").write_text(
                    json.dumps({"case_id": case_id}), encoding="utf-8",
                )
            destination = root / "submission.zip"

            create_zip(output, destination)

            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(EXPECTED_ARCHIVE, sorted(archive.namelist()))


if __name__ == "__main__":
    unittest.main()
