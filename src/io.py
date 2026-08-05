"""Safe input/output helpers owned by the coordinator layer."""

import json
from pathlib import Path
from typing import Iterable, List

from .schemas import CaseInput, CaseOutput, ContractError


def load_cases(input_dir: Path) -> List[CaseInput]:
    paths = sorted(input_dir.glob("EC_*.json"))
    cases = [CaseInput.from_dict(json.loads(path.read_text(encoding="utf-8"))) for path in paths]
    if len({case.case_id for case in cases}) != len(cases):
        raise ContractError("duplicate case_id found")
    for path, case in zip(paths, cases):
        if path.stem != case.case_id:
            raise ContractError(f"filename {path.name} does not match case_id {case.case_id}")
    return cases


def write_output(output_dir: Path, output: CaseOutput) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{output.case_id}.json"
    destination.write_text(
        json.dumps(output.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination

