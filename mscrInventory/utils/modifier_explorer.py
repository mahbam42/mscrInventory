"""Utility helpers for analyzing Square modifier CSV files."""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from django.db.models import QuerySet

from importers._handle_extras import normalize_modifier
from mscrInventory.models import RecipeModifier, RecipeModifierAlias

# Tokens that should be ignored because they represent size or temperature rather
# than actionable modifiers. This intentionally mirrors the Square importer logic
# so that diagnostics stay aligned with production handling.
IGNORED_TOKENS: set[str] = {"iced", "ice", "hot", "small", "medium", "large", "xl"}
NAME_YOUR_DRINK_PREFIX = "name this coffee"

# Default directory that stores Square CSV exports inside the repository.
DEFAULT_SQUARE_DIR = Path("squareCSVs")


@dataclass
class FuzzyMatch:
    """Represents a fuzzy match candidate for a modifier label."""

    id: int
    name: str
    behavior: str
    score: float


@dataclass
class ModifierInsight:
    """Aggregated insight for a normalized modifier label."""

    normalized: str
    total_count: int = 0
    raw_labels: Counter[str] = field(default_factory=Counter)
    items: Counter[str] = field(default_factory=Counter)
    co_occurrence: Counter[str] = field(default_factory=Counter)
    classification: str = "unknown"
    modifier_id: Optional[int] = None
    modifier_name: Optional[str] = None
    modifier_behavior: Optional[str] = None
    fuzzy_matches: List[FuzzyMatch] = field(default_factory=list)
    alias_label: Optional[str] = None
    product_match_name: Optional[str] = None

    @property
    def matches_product(self) -> bool:
        return bool(self.product_match_name)

    def _clean_display_label(self, label: str) -> str:
        cleaned = (label or "").strip()
        cleaned = cleaned.lstrip("-–—•· ")
        return cleaned or (label or "").strip() or label

    def aggregated_raw_labels(self, limit: Optional[int] = None) -> List[tuple[str, int]]:
        aggregated: dict[str, int] = {}
        display_labels: dict[str, str] = {}

        for raw_label, count in self.raw_labels.items():
            if not raw_label:
                continue
            normalized = normalize_modifier(raw_label)
            key = normalized or raw_label.strip().lower() or raw_label
            aggregated[key] = aggregated.get(key, 0) + count
            display_labels.setdefault(key, self._clean_display_label(raw_label))

        rows = sorted(
            aggregated.items(),
            key=lambda item: (-item[1], display_labels[item[0]].lower()),
        )

        results = [(display_labels[key], count) for key, count in rows]
        if limit is not None:
            return results[:limit]
        return results

    @property
    def top_raw_labels(self) -> List[tuple[str, int]]:
        return self.aggregated_raw_labels(limit=5)

    @property
    def top_items(self) -> List[tuple[str, int]]:
        return self.items.most_common(5)

    def add_observation(self, raw_label: str, item_name: str) -> None:
        """Update counters from a CSV observation."""
        self.total_count += 1
        if raw_label:
            self.raw_labels[raw_label] += 1
        if item_name:
            self.items[item_name] += 1

    def add_co_occurrence(self, other_normalized: str) -> None:
        if other_normalized and other_normalized != self.normalized:
            self.co_occurrence[other_normalized] += 1

    def as_dict(self) -> Dict[str, object]:
        """Serialize the insight for JSON responses."""
        return {
            "normalized": self.normalized,
            "total_count": self.total_count,
            "raw_labels": dict(self.aggregated_raw_labels()),
            "top_items": dict(self.items.most_common(10)),
            "classification": self.classification,
            "modifier": (
                {
                    "id": self.modifier_id,
                    "name": self.modifier_name,
                    "behavior": self.modifier_behavior,
                }
                if self.modifier_id
                else None
            ),
            "alias_label": self.alias_label,
            "fuzzy_matches": [
                {
                    "id": match.id,
                    "name": match.name,
                    "behavior": match.behavior,
                    "score": round(match.score, 4),
                }
                for match in self.fuzzy_matches
            ],
            "co_occurrence": dict(self.co_occurrence.most_common(10)),
        }

    def to_csv_row(self) -> Dict[str, object]:
        """Provide a flat row suitable for CSV export."""
        top_raw = ", ".join(
            f"{label} ({count})" for label, count in self.aggregated_raw_labels(limit=5)
        )
        top_items = ", ".join(
            f"{item} ({count})" for item, count in self.items.most_common(5)
        )
        return {
            "normalized": self.normalized,
            "total_count": self.total_count,
            "classification": self.classification,
            "modifier_id": self.modifier_id or "",
            "modifier_name": self.modifier_name or "",
            "modifier_behavior": self.modifier_behavior or "",
            "alias_label": self.alias_label or "",
            "top_raw_labels": top_raw,
            "top_items": top_items,
        }


@dataclass
class ModifierExplorerReport:
    """Final aggregated report returned by the analyzer."""

    insights: Dict[str, ModifierInsight]
    co_occurrence_pairs: Dict[Tuple[str, str], int]
    source_files: List[Path]

    def to_json(self) -> Dict[str, object]:
        return {
            "source_files": [str(path) for path in self.source_files],
            "modifiers": {
                normalized: insight.as_dict()
                for normalized, insight in sorted(self.insights.items())
            },
            "co_occurrence_pairs": {
                f"{a}|{b}": count for (a, b), count in sorted(self.co_occurrence_pairs.items())
            },
        }

    def to_csv_rows(self) -> List[Dict[str, object]]:
        return [insight.to_csv_row() for insight in sorted(self.insights.values(), key=lambda x: x.normalized)]


class ModifierExplorerAnalyzer:
    """Collects and summarizes modifier usage from Square CSV exports."""

    def __init__(
        self,
        ignored_tokens: Optional[Iterable[str]] = None,
        custom_name_prefixes: Optional[Iterable[str]] = None,
    ) -> None:
        self.ignored_tokens = set(ignored_tokens or IGNORED_TOKENS)
        prefixes = custom_name_prefixes or (NAME_YOUR_DRINK_PREFIX,)
        self.custom_name_prefixes = tuple(prefix.strip().lower() for prefix in prefixes)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def analyze(self, paths: Optional[Sequence[Path]] = None) -> ModifierExplorerReport:
        csv_files = list(self._resolve_paths(paths))
        insights: Dict[str, ModifierInsight] = {}
        co_occurrence_pairs: Dict[Tuple[str, str], int] = defaultdict(int)

        for csv_path in csv_files:
            for row in self._iter_csv(csv_path):
                item_name = (row.get("Item") or "").strip()
                raw_modifiers = self._parse_modifiers(row.get("Modifiers Applied"))
                normalized_modifiers = [
                    normalize_modifier(raw) for raw in raw_modifiers
                ]
                filtered = [
                    (raw, normalized)
                    for raw, normalized in zip(raw_modifiers, normalized_modifiers)
                    if normalized
                    and normalized not in self.ignored_tokens
                    and not self._is_custom_drink_token(normalized)
                ]
                if not filtered:
                    continue

                # Update per-modifier counters
                for raw, normalized in filtered:
                    insight = insights.setdefault(
                        normalized, ModifierInsight(normalized=normalized)
                    )
                    insight.add_observation(raw, item_name)

                # Track co-occurrence once per unique pair per row
                unique_norms = sorted({normalized for _, normalized in filtered})
                for i, left in enumerate(unique_norms):
                    for right in unique_norms[i + 1 :]:
                        co_occurrence_pairs[(left, right)] += 1
                        insights[left].add_co_occurrence(right)
                        insights[right].add_co_occurrence(left)

        modifiers = self._fetch_modifiers()
        aliases = self._fetch_aliases()
        self._classify_modifiers(insights, modifiers, aliases)

        return ModifierExplorerReport(
            insights=insights,
            co_occurrence_pairs=dict(co_occurrence_pairs),
            source_files=csv_files,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _resolve_paths(self, paths: Optional[Sequence[Path]]) -> Iterator[Path]:
        if paths:
            for supplied in paths:
                supplied_path = Path(supplied)
                if supplied_path.is_file():
                    yield supplied_path
                elif supplied_path.is_dir():
                    yield from sorted(supplied_path.glob("*.csv"))
            return

        if DEFAULT_SQUARE_DIR.exists():
            yield from sorted(DEFAULT_SQUARE_DIR.glob("*.csv"))

    def _iter_csv(self, path: Path) -> Iterator[Dict[str, str]]:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                yield row

    def _parse_modifiers(self, raw_value: Optional[str]) -> List[str]:
        if not raw_value:
            return []
        return [token.strip() for token in raw_value.split(",") if token.strip()]

    def _fetch_modifiers(self) -> QuerySet[RecipeModifier]:
        return RecipeModifier.objects.all().only("id", "name", "behavior")

    def _fetch_aliases(self) -> QuerySet[RecipeModifierAlias]:
        return RecipeModifierAlias.objects.select_related("modifier").all()

    def _is_custom_drink_token(self, token: str) -> bool:
        normalized = (token or "").strip().lower()
        if not normalized:
            return False
        return any(normalized.startswith(prefix) for prefix in self.custom_name_prefixes)

    def _classify_modifiers(
        self,
        insights: Dict[str, ModifierInsight],
        modifiers: QuerySet[RecipeModifier],
        aliases: QuerySet[RecipeModifierAlias],
    ) -> None:
        normalized_lookup: Dict[str, RecipeModifier] = {}
        names_lower: Dict[str, RecipeModifier] = {}
        alias_lookup: Dict[str, RecipeModifierAlias] = {}
        for modifier in modifiers:
            normalized_lookup[normalize_modifier(modifier.name)] = modifier
            names_lower[modifier.name.lower()] = modifier

        for alias in aliases:
            alias_lookup[alias.normalized_label] = alias

        for insight in insights.values():
            modifier = normalized_lookup.get(insight.normalized)
            if modifier:
                insight.classification = "known"
                insight.modifier_id = modifier.id
                insight.modifier_name = modifier.name
                insight.modifier_behavior = modifier.behavior
                continue

            modifier = names_lower.get(insight.normalized)
            if modifier:
                insight.classification = "known"
                insight.modifier_id = modifier.id
                insight.modifier_name = modifier.name
                insight.modifier_behavior = modifier.behavior
                continue

            alias = alias_lookup.get(insight.normalized)
            if not alias and insight.raw_labels:
                for raw_label in insight.raw_labels:
                    normalized = normalize_modifier(raw_label)
                    alias = alias_lookup.get(normalized)
                    if alias:
                        break
            if alias:
                modifier = alias.modifier
                insight.classification = "alias"
                insight.modifier_id = modifier.id
                insight.modifier_name = modifier.name
                insight.modifier_behavior = modifier.behavior
                insight.alias_label = alias.raw_label
                continue

            fuzzy_matches = self._find_fuzzy_matches(
                insight.normalized, list(normalized_lookup.items())
            )
            if fuzzy_matches:
                insight.classification = "fuzzy"
                insight.fuzzy_matches = fuzzy_matches
                best = fuzzy_matches[0]
                insight.modifier_id = best.id
                insight.modifier_name = best.name
                insight.modifier_behavior = best.behavior
            else:
                insight.classification = "unknown"

    def _find_fuzzy_matches(
        self,
        token: str,
        candidates: Sequence[Tuple[str, RecipeModifier]],
        limit: int = 3,
        cutoff: float = 0.72,
    ) -> List[FuzzyMatch]:
        scored: List[FuzzyMatch] = []
        for normalized_name, modifier in candidates:
            score = SequenceMatcher(None, token, normalized_name).ratio()
            if score >= cutoff:
                scored.append(
                    FuzzyMatch(
                        id=modifier.id,
                        name=modifier.name,
                        behavior=modifier.behavior,
                        score=score,
                    )
                )
        scored.sort(key=lambda match: match.score, reverse=True)
        return scored[:limit]


__all__ = [
    "ModifierExplorerAnalyzer",
    "ModifierExplorerReport",
    "ModifierInsight",
]
