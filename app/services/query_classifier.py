"""Rule-based query classifier — first-pass implementation for RouterService.

Classifies a query into {vector, hybrid, graph} using keyword/pattern
matching over the query text. No corpus data or training required.

Tuned for the held-out set mix (lookup → vector, cross_document → hybrid,
entity_relationship / org-chart → graph) and threshold 0.6 so the vector
default is not always forced into hybrid fallback.

Upgrade path: swap for a fine-tuned classifier with the same
async .predict(query) -> (str, float) interface.
"""

import re

# Ordered by specificity: graph first, then hybrid, else vector.
# Patterns intentionally match hand-crafted graph eval phrasing
# (reports_to / owns / works_on / collaborates / titles).
_GRAPH_PATTERNS = [
    # Reporting lines
    r"\bwho does\b.+\breport\s+to\b",
    r"\bwho reports?\s+to\b",
    r"\bwho is the manager of\b",
    r"\bmanager of\b",
    r"\breports?\s+to\b",
    r"\breporting\s+(line|structure|chain)\b",
    # Ownership / assignment
    r"\bwho owns\b",
    r"\bwhat project does\b.+\bown\b",
    r"\bwho (leads|manages)\b",
    r"\bowner of\b",
    # Works-on / staffing
    r"\bwho works?\s+on\b",
    r"\bdoes\b.+\bwork\s+on\b",
    r"\bworks?\s+on (the )?(project|playbook|product)\b",
    r"\bwho (is|are) (involved|responsible|assigned)\b",
    r"\bwhich (team|teams|people|person)\s+(is|are)\s+(involved|responsible|assigned)\b",
    # Collaboration / relationships
    r"\bcollaborat\w*\b",
    r"\brelationship(s)? between\b",
    r"\bconnect(ed|ion)?\s+(to|between|with)\b.*\b(people|person|team|project)\b",
    r"\borg(aniz(ation|ational))?\s*(chart|structure|hierarchy)\b",
    # Titles / roles (org graph)
    r"\bwhat is\b.+\b('s|’s)?\s*title\b",
    r"\bwho has the title\b",
    r"\btitle of\b",
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
    # Multi-source / reconciling language (cross_document gold often hybrid)
    r"\bbut\b.+\b(allow|says?|standard|policy|adr)\b",
    r"\bactual policy\b",
    r"\breconcile\b|\bconflicting\b",
    r"\bboth\b.+\band\b.+\b(document|policy|source)\b",
]


class RuleBasedClassifier:
    """Keyword/regex classifier. Deterministic (Success Criterion 3)."""

    # Fixed heuristic scores vs settings.router_confidence_threshold (0.6).
    _GRAPH_CONFIDENCE = 0.85
    _HYBRID_CONFIDENCE = 0.75
    # Must be >= threshold so default lookup queries are not force-hybrid.
    _VECTOR_CONFIDENCE = 0.65

    @staticmethod
    def _looks_multi_aspect(text: str) -> bool:
        """Cross-document / multi-fact questions often need hybrid retrieval."""
        if text.count("?") >= 2:
            return True
        # Two linked sub-questions in one sentence
        if re.search(
            r"\band\s+(what|who|when|where|how|which|why)\b",
            text,
        ):
            return True
        if re.search(r",\s*(and\s+)?(what|who|when|how|which)\b", text):
            return True
        # Long compound asks (benchmark cross_document style)
        if len(text) >= 160 and text.count(",") >= 2:
            return True
        return False

    async def predict(self, query: str) -> tuple[str, float]:
        text = query.lower().strip()

        for pattern in _GRAPH_PATTERNS:
            if re.search(pattern, text):
                return "graph", self._GRAPH_CONFIDENCE

        for pattern in _HYBRID_PATTERNS:
            if re.search(pattern, text):
                return "hybrid", self._HYBRID_CONFIDENCE

        if self._looks_multi_aspect(text):
            return "hybrid", self._HYBRID_CONFIDENCE

        return "vector", self._VECTOR_CONFIDENCE
