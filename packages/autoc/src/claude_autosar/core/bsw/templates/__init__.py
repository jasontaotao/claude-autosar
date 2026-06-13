"""XDM template diff — Sprint 9.2 M1-T.

Sprint 9.2 splits template comparison into two independent modules:

  - :mod:`claude_autosar.core.bsw.templates.xdm_value` —
    ``XDMValue`` / ``XDMModule`` frozen dataclasses + ``load_xdm_module``
    (uses dispatcher to read .xdm + lxml xpath to extract leaves).
  - :mod:`claude_autosar.core.bsw.templates.xdm_diff` —
    ``TemplateDiff`` / ``TemplateDiffResult`` frozen dataclasses +
    ``diff_xdm_templates`` (add / modify / delete ops).

Design notes (aligned with plan §2.1 / §2.2):

  - **No shared InstanceTree abstraction** — each format owns its own
    dataclasses; XDM leaves are ``<d:var>``, not
    ``<ECUC-NUMERICAL-PARAM-VALUE>``, so they cannot reuse
    :class:`claude_autosar.core.bsw.ecuc.ECUCValue`.
  - **Type inference heuristic** — ``_infer_xdm_type`` reads the
    ``type`` attribute: ``INT/INTEGER`` → INTEGER; ``FLOAT/DOUBLE`` →
    FLOAT; ``BOOL/BOOLEAN`` → BOOLEAN; ``ENUM`` → ENUMERATION;
    otherwise → STRING.
  - **Immutability** — every dataclass is ``frozen=True``; the input
    XDMModule is never mutated.
  - **Pure diff function** — ``diff_xdm_templates`` does not mutate
    inputs and returns a new ``TemplateDiffResult``.
"""

from __future__ import annotations

from claude_autosar.core.bsw.templates.xdm_diff import (
    TemplateDiff,
    TemplateDiffOp,
    TemplateDiffResult,
    diff_xdm_templates,
)
from claude_autosar.core.bsw.templates.xdm_value import (
    XDMModule,
    XDMValue,
    XDMValueError,
    XDMValueType,
    load_xdm_module,
)

__all__ = [
    # xdm_value
    "XDMValue",
    "XDMValueType",
    "XDMValueError",
    "XDMModule",
    "load_xdm_module",
    # xdm_diff
    "TemplateDiff",
    "TemplateDiffOp",
    "TemplateDiffResult",
    "diff_xdm_templates",
]
