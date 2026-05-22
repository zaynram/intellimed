"""Type-level marker classes for the OCR extraction surface (spec §5.2)."""

from __future__ import annotations


class IncompleteUntilValidated:
    """Type-level marker on ``FieldExtraction.normalized_value``.

    Indicates the value has not been validated against its target
    TrustData field's type and may not satisfy that field's constraints.
    Consumers MUST narrow via isinstance against the target type before
    use. The field's static type is ``object``, which makes this
    discipline visible to type checkers.
    """


class RawSelfReport:
    """Type-level marker on ``FieldExtraction.confidence_self_report``.

    Indicates the value is the model's own first-order confidence report
    in [0.0, 1.0], with no calibration applied. Consumers requiring
    calibrated confidence MUST route the value through a
    ``ConfidenceProtocol`` implementation (Session 4.3c). Both readers
    and producers must respect this marker; any future calibrated
    channel receives a sibling marker (e.g., ``Calibrated``) and a
    separate field.
    """
