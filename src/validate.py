from __future__ import annotations

import json
import typing as ty

if ty.TYPE_CHECKING:
    from .types import *


class ValidationDict(dict[ValidationSubject, ValidatedResult]):
    _subjects = ty.final(("injuries", "treatments"))
    _verdicts = ty.final(("verified", "unverified"))

    plaintext: str
    summary: ValidationSummary

    def __init__(self, plaintext: str, analysis_results: dict[str, ty.Any]) -> None:
        self.summary: ValidationSummary = dict.fromkeys(
            self._subjects, dict.fromkeys(self._verdicts, 0)
        )
        self.plaintext = plaintext
        self.base_results = analysis_results
        super().__init__(self)
        self.update(
            dict.fromkeys(
                ("injuries", "treatments"),
                dict.fromkeys(("verified", "unverified"), list[str]()),
            )
        )

    def _set(
        self, item: str, subj: ValidationSubject, verdict: ValidationVerdict
    ) -> None:
        self[subj][verdict].append(item)
        self.summary[subj][verdict] += 1

    def validate(self) -> tuple[ty.Self, ValidationSummary]:
        for subject in self._subjects:
            for item in self.base_results.get(subject, []):
                verdict = "verified" if item in self.plaintext else "unverified"
                self._set(item, subject, verdict)
        return self, self.summary


def validate_analysis_results(results_dir: Path) -> ValidationSummary:
    validate_path = results_dir.parent.parent / "results.json"

    results = {}
    summary = {}

    for f in results_dir.iterdir():
        raw_results = json.loads(f.read_text(encoding="utf-8"))

        if not isinstance(raw_results, dict):
            from .utils import error

            error(
                "Could not parse analysis results.",
                f"File: {f.as_uri()}",
                exception=TypeError,
            )

        text_name = f.stem.replace("_analysis.json", ".txt")
        text_file = (results_dir.parent / text_name).resolve(strict=True)

        plaintext = text_file.read_text(encoding="utf-8")

        results[f.stem], summary[f.stem] = ValidationDict(
            plaintext, raw_results
        ).validate()

    validate_path.write_text(json.dumps(results, indent=4), encoding="utf-8")

    return summary
