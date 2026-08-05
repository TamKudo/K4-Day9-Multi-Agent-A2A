"""Validate the 50 outputs and create a submission ZIP with no extra files."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path


EXPECTED = [f"EC_{number:03d}.json" for number in range(1, 51)]
EXPECTED_ARCHIVE = [f"output/{name}" for name in EXPECTED]


def validate_output_dir(output_dir: Path) -> None:
    actual = sorted(path.name for path in output_dir.glob("*.json"))
    if actual != EXPECTED:
        missing = sorted(set(EXPECTED) - set(actual))
        extra = sorted(set(actual) - set(EXPECTED))
        raise ValueError(f"output set mismatch; missing={missing}, extra={extra}")
    for name in EXPECTED:
        payload = json.loads((output_dir / name).read_text(encoding="utf-8"))
        if payload.get("case_id") != Path(name).stem:
            raise ValueError(f"{name}: case_id mismatch")


def create_zip(output_dir: Path, destination: Path) -> None:
    validate_output_dir(output_dir)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in EXPECTED:
            archive.write(output_dir / name, arcname=f"output/{name}")
    with zipfile.ZipFile(destination) as archive:
        if sorted(archive.namelist()) != EXPECTED_ARCHIVE:
            raise ValueError("ZIP content validation failed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--zip", type=Path, default=Path("submission_output.zip"))
    args = parser.parse_args()
    create_zip(args.output_dir, args.zip)
    print(f"validated=50 zip={args.zip}")


if __name__ == "__main__":
    main()
