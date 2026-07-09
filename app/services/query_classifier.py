"""Rule-based query classifier — first-pass implementation for RouterService.

Classifies a query into {vector, hybrid, graph} using keyword/pattern
matching over the query text. No corpus data or training required, so this
can be built and tested before Yusra's data pipeline lands.

Upgrade path: once labeled queries exist (from EnterpriseRAG-Bench's
question_type field), this can be swapped for a lightweight fine-tuned
classifier without changing RouterService's interface — it only needs
something with an async .predict(query) -> (str, float) method.
"""

import re

# Ordered by specificity: graph patterns checked first (most specific),
# then hybrid (medium specificity), falling through to vector (default).
_GRAPH_PATTERNS = [
    r"\bwho (works?|reports?|collaborat\w*) (with|to|on)\b",
    r"\brelationship(s)? between\b",
    r"\bconnect(ed|ion)?\s+(to|between|with)\b",
    r"\bwhich (team|teams|people|person)\s+(is|are)\s+(involved|responsible|assigned)\b",
    r"\bowns?\b.*\bproject\b",
    r"\breports? to\b",
    r"\bwho (owns|leads|manages)\b",
]

_HYBRID_PATTERNS = [
    r"\bcompare\b|\bcomparison\b",
    r"\bdifference(s)? between\b",
    r"\bversus\b|\bvs\.?\b",
    r"\bconflict(s|ing)?\b",
    r"\bacross\s+(all|multiple|the)\b",
    r"\ball\s+(documents|teams|departments|projects)\b",
    r"\btrend(s)?\b",
    r"\bover time\b",
    r"\bsummary of\b|\bsummarize\b",
    r"\bhow (many|much)\b.*\b(total|combined|overall)\b",
]


class RuleBasedClassifier:
    """Keyword/regex classifier. Deterministic (Success Criterion 3's
    stochastic-vs-deterministic distinction: this component is deterministic,
    unlike the generation step)."""

    # Confidence is a fixed heuristic score, not a calibrated probability —
    # good enough to compare against settings.router_confidence_threshold.
    _GRAPH_CONFIDENCE = 0.85
    _HYBRID_CONFIDENCE = 0.75
    _VECTOR_CONFIDENCE = 0.60  # lower: vector is the "nothing else matched" default

    async def predict(self, query: str) -> tuple[str, float]:
        text = query.lower().strip()

        for pattern in _GRAPH_PATTERNS:
            if re.search(pattern, text):
                return "graph", self._GRAPH_CONFIDENCE

        for pattern in _HYBRID_PATTERNS:
            if re.search(pattern, text):
                return "hybrid", self._HYBRID_CONFIDENCE

        return "vector", self._VECTOR_CONFIDENCE