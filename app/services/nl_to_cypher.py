"""Rule-based NL -> Cypher translation for GraphService (M9).

Same philosophy as RuleBasedClassifier (app/services/query_classifier.py):
deterministic regex extraction over a small, fixed graph schema, so
GraphRAG is buildable and testable before any LLM-backed NL->Cypher
component exists. Swappable later behind the same
`.translate(query) -> CypherQuery | None` interface -- GraphService only
depends on that shape, not on how the query was produced.

Graph schema this assumes (seeded by scripts/build_graph_index.py):
    (:Person {name})-[:REPORTS_TO]->(:Person)
    (:Person {name})-[:WORKS_ON]->(:Project {name})
    (:Person {name})-[:OWNS]->(:Project {name})
    (:Person {name})-[:COLLABORATES_WITH]-(:Person)

Every template returns rows already shaped like RetrievedChunk fields
(text/id/score/source) so GraphService can build chunks directly from
records without a separate per-intent formatting step.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class CypherQuery:
    text: str
    parameters: dict = field(default_factory=dict)


def _clean_entity(raw: str) -> str:
    value = raw.strip().rstrip("?.!").strip()
    if value[:4].lower() == "the ":
        value = value[4:].strip()
    for suffix in (" project", " team"):
        if value.lower().endswith(suffix):
            value = value[: -len(suffix)].strip()
    return value


def _reports_to(match: re.Match) -> CypherQuery:
    return CypherQuery(
        text=(
            "MATCH (p:Person {name: $name})-[:REPORTS_TO]->(m:Person) "
            "RETURN m.name + ' is the manager ' + p.name + ' reports to.' AS text, "
            "p.name + '_reports_to_' + m.name AS id, 1.0 AS score, 'graph:org_chart' AS source"
        ),
        parameters={"name": _clean_entity(match.group(1))},
    )


def _direct_reports(match: re.Match) -> CypherQuery:
    return CypherQuery(
        text=(
            "MATCH (m:Person {name: $name})<-[:REPORTS_TO]-(p:Person) "
            "RETURN p.name + ' reports to ' + m.name + '.' AS text, "
            "p.name + '_reports_to_' + m.name AS id, 1.0 AS score, 'graph:org_chart' AS source"
        ),
        parameters={"name": _clean_entity(match.group(1))},
    )


def _owns_project(match: re.Match) -> CypherQuery:
    return CypherQuery(
        text=(
            "MATCH (p:Person)-[:OWNS]->(proj:Project {name: $name}) "
            "RETURN p.name + ' owns the project ' + proj.name + '.' AS text, "
            "p.name + '_owns_' + proj.name AS id, 1.0 AS score, 'graph:project_ownership' AS source"
        ),
        parameters={"name": _clean_entity(match.group(1))},
    )


def _works_on(match: re.Match) -> CypherQuery:
    return CypherQuery(
        text=(
            "MATCH (p:Person {name: $name})-[:WORKS_ON]->(proj:Project) "
            "RETURN p.name + ' works on ' + proj.name + '.' AS text, "
            "p.name + '_works_on_' + proj.name AS id, 1.0 AS score, 'graph:project_membership' AS source"
        ),
        parameters={"name": _clean_entity(match.group(1))},
    )


def _collaborators(match: re.Match) -> CypherQuery:
    return CypherQuery(
        text=(
            "MATCH (p:Person {name: $name})-[:COLLABORATES_WITH]-(c:Person) "
            "RETURN c.name + ' collaborates with ' + p.name + '.' AS text, "
            "p.name + '_collaborates_with_' + c.name AS id, 1.0 AS score, 'graph:collaboration' AS source"
        ),
        parameters={"name": _clean_entity(match.group(1))},
    )


def _relationship_between(match: re.Match) -> CypherQuery:
    return CypherQuery(
        text=(
            "MATCH path = shortestPath((a:Person {name: $name_a})-[*..4]-(b:Person {name: $name_b})) "
            "WITH a, b, "
            "[n IN nodes(path) | coalesce(n.name, 'unknown')] AS names, "
            "[r IN relationships(path) | type(r)] AS rels "
            "RETURN a.name + ' and ' + b.name + ' are connected via: ' + "
            "reduce(s = names[0], i IN range(1, size(names) - 1) | "
            "s + ' -[' + rels[i - 1] + ']-> ' + names[i]) AS text, "
            "a.name + '_to_' + b.name AS id, 1.0 AS score, 'graph:relationship_path' AS source"
        ),
        parameters={"name_a": _clean_entity(match.group(1)), "name_b": _clean_entity(match.group(2))},
    )


# Entities followed by more literal pattern text (e.g. " and ", " report to")
# can stay non-greedy -- the literal bounds them. Entities at the *end* of a
# pattern must be anchored to end-of-string (_END), or a non-greedy group
# with nothing but "\b" after it matches the shortest possible span (e.g.
# stopping at "the" in "the Phoenix project") instead of the full name.
_NAME = r"([A-Za-z][\w' .-]*?)"
_END = r"\s*\??\s*$"

# Ordered most-specific first, same rationale as query_classifier.py's
# _GRAPH_PATTERNS: two-entity patterns before one-entity ones.
_PATTERNS: list[tuple[re.Pattern, Callable[[re.Match], CypherQuery]]] = [
    (re.compile(rf"\brelationship(?:s)? between {_NAME} and {_NAME}{_END}", re.I), _relationship_between),
    (re.compile(rf"\bhow is {_NAME} connected to {_NAME}{_END}", re.I), _relationship_between),
    (re.compile(rf"\bwho does {_NAME} report to{_END}", re.I), _reports_to),
    (re.compile(rf"\bwho reports to {_NAME}{_END}", re.I), _direct_reports),
    (re.compile(rf"\bwho (?:owns|leads|manages) {_NAME}{_END}", re.I), _owns_project),
    (re.compile(rf"\bwhat (?:is|are) {_NAME} working on{_END}", re.I), _works_on),
    (re.compile(rf"\bwho (?:works?|collaborat\w*) with {_NAME}{_END}", re.I), _collaborators),
]


class NLToCypher:
    """Deterministic NL -> Cypher translator. No corpus data, model, or live
    LLM required, so GraphService is testable before a real translator lands.
    """

    async def translate(self, query: str) -> CypherQuery | None:
        text = query.strip()
        for pattern, build in _PATTERNS:
            match = pattern.search(text)
            if match:
                return build(match)
        return None
