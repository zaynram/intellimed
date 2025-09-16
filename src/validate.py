from __future__ import annotations

import re
import typing as ty
from .utils import timings

from .typeshed import ValidationSubject, ValidatedResult

if ty.TYPE_CHECKING:
    from .typeshed import *


class ValidationDict(dict[ValidationSubject, ValidatedResult]):
    """Runtime validation container.

    Keeps the same external shape as `ValidatedResult` but is available at
    runtime (the previous implementation only defined the class under
    TYPE_CHECKING). This class also implements a confidence scoring algorithm
    that favors consecutive n-gram matches.
    """

    _subjects = ty.final(("injuries", "treatments"))
    _verdicts = ty.final(("verified", "unverified"))

    def __init__(self, plaintext: str, analysis_results) -> None:
        # counts are per-item (not per-token)
        self.match_counts = {s: {v: 0 for v in self._verdicts} for s in self._subjects}
        self.plaintext = plaintext
        self.base_results = analysis_results
        super().__init__()
        for s in self._subjects:
            self[s] = {v: {} for v in self._verdicts}

    def _set(
        self,
        item: str,
        matches: list[str],
        confidence: float,
        subj: ValidationSubject,
        verdict: ValidationVerdict,
    ) -> None:
        """Store the matched phrases for an item and increment per-item counts."""
        self[subj][verdict][item] = confidence, matches
        self.match_counts[subj][verdict] += 1

    def _score_item(self, item_str: str, bonus_factor: float = 0.5) -> tuple[float, list[str]]:
        """Compute a confidence score [0,1] and return the list of matched phrases.

        Algorithm (greedy n-gram match):
        - Tokenize the item and the plaintext into lowercase words.
        - Walk the item tokens left-to-right and at each position greedily try the
          longest n-gram (within the remaining tokens) that occurs in the
          plaintext.
        - Each matched n-gram of length r contributes r points (for the words)
          plus a non-linear bonus proportional to r*(r-1)/2 scaled by
          `bonus_factor`. This rewards longer consecutive matches.
        - Normalize the raw score by the theoretical maximum for the item's
          token length so the returned confidence is in [0,1].
        """

        token_re = re.compile(r"\w+", re.UNICODE)
        words = token_re.findall(item_str.lower())
        if not words:
            return 0.0, []

        plaintext = self.plaintext.lower()

        i = 0
        runs: list[int] = []
        matched_phrases: list[str] = []
        n = len(words)

        while i < n:
            found_len = 0
            # try longest n-gram first (greedy)
            for L in range(n - i, 0, -1):
                phrase = " ".join(words[i : i + L])
                if phrase in plaintext:
                    found_len = L
                    matched_phrases.append(phrase)
                    break

            if found_len > 0:
                runs.append(found_len)
                i += found_len
            else:
                i += 1

        base_matches = sum(runs)
        # triangular bonus to favor longer consecutive runs
        bonus = sum((r * (r - 1) / 2) * bonus_factor for r in runs)
        raw_score = base_matches + bonus

        # theoretical maximum: all tokens matched in a single run
        max_score = n + ((n * (n - 1) / 2) * bonus_factor)
        confidence = float(raw_score / max_score) if max_score > 0 else 0.0
        # clamp for safety
        confidence = max(0.0, min(1.0, confidence))

        return confidence, matched_phrases

    @timings()
    def validate(self, threshold: float = 0.5) -> tuple["ValidationDict", dict]:
        """Validate base_results against plaintext and compute match_counts.

        Returns (self, match_counts). Items with confidence >= threshold are
        considered 'verified', others 'unverified'.
        """

        for subj in self._subjects:
            for item in self.base_results.get(subj, ()):
                item_str = str(item)
                confidence, matches = self._score_item(item_str)
                verdict = "verified" if confidence >= threshold and matches else "unverified"
                self._set(item_str, matches, confidence, subj, verdict)

        return self, self.match_counts
