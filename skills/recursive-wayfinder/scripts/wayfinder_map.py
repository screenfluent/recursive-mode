#!/usr/bin/env python3
"""Read-only validation and frontier queries for Recursive Wayfinder maps."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DELIVERY_SPEC_RE = re.compile(
    r"^/\.recursive/deliveries/[a-z0-9]+(?:-[a-z0-9]+)*/spec\.md$"
)
LINK_RE = re.compile(r"\[([^]]+)]\(([^)]+)\)")
CLAIM_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T"
    r"(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d"
    r"(?:\.\d+)?"
    r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)
MAP_SECTIONS = (
    "Destination",
    "Notes",
    "Decisions so far",
    "Candidate slices",
    "Not yet specified",
    "Out of scope",
)
UNIT_SECTIONS = ("Question", "Resolution", "Evidence", "Consequences")
PROMOTION_SECTIONS = (
    "Outcome boundary",
    "Settled inputs",
    "Evidence",
    "Remaining unknowns",
    "Out of scope",
    "Spec handoff",
)


@dataclass(frozen=True)
class Document:
    path: Path
    title: str
    text: str


@dataclass(frozen=True)
class Unit:
    doc: Document
    kind: str
    mode: str
    status: str
    claimed_by: str
    claimed_at: str
    blockers: tuple[Path, ...]
    outcome: str


@dataclass(frozen=True)
class Promotion:
    doc: Document
    status: str
    source_units: tuple[Path, ...]
    blocking: str
    human_approval: str
    promoted_to: str


class MapValidationError(Exception):
    """Raised after validation finds one or more contract violations."""


def scalar(text: str, name: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(name)}:\s*(.*?)\s*$", text)
    return match.group(1).strip() if match else None


def heading(text: str) -> str | None:
    match = re.match(r"^# ([^\n]+)\n", text)
    return match.group(1).strip() if match else None


def section(text: str, name: str) -> str | None:
    match = re.search(
        rf"(?ms)^## {re.escape(name)}\s*\n(.*?)(?=^## |\Z)", text
    )
    return match.group(1).strip() if match else None


def links(text: str) -> list[tuple[str, str]]:
    return [(label.strip(), target.strip()) for label, target in LINK_RE.findall(text)]


def scalar_values(text: str, name: str) -> list[str]:
    return [
        match.strip()
        for match in re.findall(rf"(?m)^{re.escape(name)}:\s*(.*?)\s*$", text)
    ]


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def load_document(path: Path, errors: list[str]) -> Document | None:
    if not path.is_file():
        errors.append(f"missing document: {path}")
        return None
    text = path.read_text(encoding="utf-8")
    title = heading(text)
    if not title:
        errors.append(f"{path}: first line must be '# <name>'")
        return None
    return Document(path=path, title=title, text=text)


def require_sections(doc: Document, names: tuple[str, ...], errors: list[str]) -> None:
    for name in names:
        if section(doc.text, name) is None:
            errors.append(f"{doc.path}: missing section '## {name}'")


def validate_slug(value: str, label: str, errors: list[str]) -> None:
    if not SLUG_RE.fullmatch(value):
        errors.append(f"{label} must be a kebab-case slug: {value}")


def validate_map_date(doc: Document, name: str, errors: list[str]) -> None:
    value = scalar(doc.text, name)
    if value is None:
        errors.append(f"{doc.path}: missing field '{name}:'")
        return
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        errors.append(f"{doc.path}: {name} must use YYYY-MM-DD")
        return
    try:
        date.fromisoformat(value)
    except ValueError:
        errors.append(f"{doc.path}: {name} must be a valid date")


def validate_claim_timestamp(path: Path, value: str, errors: list[str]) -> None:
    message = (
        f"{path}: Claimed at must match the claim timestamp profile: full date, "
        "T, 00-23 hours, 00-59 minutes and seconds, optional fractional seconds, "
        "and a required Z or +/-HH:MM timezone; leap seconds are outside the profile"
    )
    if not CLAIM_TIMESTAMP_RE.fullmatch(value):
        errors.append(message)
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(message)
        return
    if parsed.utcoffset() is None:
        errors.append(message)


def resolve_local_link(base: Path, target: str, map_dir: Path) -> Path | None:
    if "://" in target or target.startswith("#"):
        return None
    plain = target.split("#", 1)[0]
    if not plain:
        return None
    candidate = Path(plain)
    if candidate.is_absolute():
        raise ValueError("absolute local links are not allowed")
    resolved = (base / candidate).resolve()
    if not is_within(resolved, map_dir):
        raise ValueError("local links must stay within the map directory")
    return resolved


def resolve_markdown_link(base: Path, target: str, map_dir: Path) -> Path | None:
    resolved = resolve_local_link(base, target, map_dir)
    if resolved is None or resolved.suffix.lower() != ".md":
        return None
    return resolved


def validate_named_link(
    source: Path,
    label: str,
    target: str,
    map_dir: Path,
    documents: dict[Path, Document],
    errors: list[str],
) -> Path | None:
    try:
        resolved = resolve_markdown_link(source.parent, target, map_dir)
    except ValueError as error:
        errors.append(f"{source}: {error}: {target!r}")
        return None
    if resolved is None:
        errors.append(f"{source}: expected a relative Markdown link, got {target!r}")
        return None
    target_doc = documents.get(resolved)
    if target_doc is None:
        return resolved
    if label != target_doc.title:
        errors.append(
            f"{source}: link text {label!r} does not match target title {target_doc.title!r}"
        )
    return resolved


def validate_local_links(
    map_dir: Path, documents: dict[Path, Document], errors: list[str]
) -> None:
    """Require every local linked asset from a contract document to exist."""
    checked: set[tuple[Path, Path]] = set()
    for doc in documents.values():
        for _label, target in links(doc.text):
            try:
                resolved = resolve_local_link(doc.path.parent, target, map_dir)
            except ValueError as error:
                errors.append(f"{doc.path}: {error}: {target!r}")
                continue
            if resolved is None:
                continue
            key = (doc.path.resolve(), resolved)
            if key in checked:
                continue
            checked.add(key)
            if not resolved.is_file():
                errors.append(f"{doc.path}: local link does not exist: {target}")


def valid_promoted_to(value: str) -> bool:
    return value not in {"none", "pending"} and bool(
        SLUG_RE.fullmatch(value) or DELIVERY_SPEC_RE.fullmatch(value)
    )


def load_units(map_dir: Path, errors: list[str]) -> tuple[dict[Path, Unit], dict[Path, Document]]:
    units: dict[Path, Unit] = {}
    documents: dict[Path, Document] = {}
    units_dir = map_dir / "units"
    if not units_dir.is_dir():
        errors.append(f"missing units directory: {units_dir}")
        return units, documents

    for path in sorted(units_dir.glob("*.md")):
        if not is_within(path.resolve(), map_dir):
            errors.append(f"{path}: discovery unit resolves outside the map directory")
            continue
        validate_slug(path.stem, "unit id", errors)
        doc = load_document(path, errors)
        if doc is None:
            continue
        documents[path.resolve()] = doc
        require_sections(doc, UNIT_SECTIONS, errors)
        values = {
            name: scalar(doc.text, name)
            for name in ("Kind", "Mode", "Status", "Claimed by", "Claimed at", "Blocked by", "Outcome")
        }
        for name, value in values.items():
            if value is None:
                errors.append(f"{path}: missing field '{name}:'")

        kind = values["Kind"] or ""
        mode = values["Mode"] or ""
        status = values["Status"] or ""
        claimed_by = values["Claimed by"] or ""
        claimed_at = values["Claimed at"] or ""
        blocker_value = values["Blocked by"] or ""
        outcome = values["Outcome"] or ""

        if kind not in {"research", "prototype", "grilling", "unblocker"}:
            errors.append(f"{path}: invalid Kind: {kind}")
        if mode not in {"HITL", "AFK"}:
            errors.append(f"{path}: invalid Mode: {mode}")
        if kind == "research" and mode != "AFK":
            errors.append(f"{path}: research units must be AFK")
        if kind in {"prototype", "grilling"} and mode != "HITL":
            errors.append(f"{path}: {kind} units must be HITL")
        if status not in {"open", "claimed", "resolved", "out-of-scope"}:
            errors.append(f"{path}: invalid Status: {status}")
        if outcome not in {"pending", "resolved", "inconclusive"}:
            errors.append(f"{path}: invalid Outcome: {outcome}")
        if status == "resolved" and outcome not in {"resolved", "inconclusive"}:
            errors.append(f"{path}: resolved Status requires resolved or inconclusive Outcome")
        if status != "resolved" and outcome != "pending":
            errors.append(f"{path}: Outcome must be pending unless Status is resolved")

        if status == "claimed":
            if claimed_by in {"", "none"}:
                errors.append(f"{path}: claimed Status requires Claimed by")
            if claimed_at in {"", "none"}:
                errors.append(f"{path}: claimed Status requires Claimed at")
            else:
                validate_claim_timestamp(path, claimed_at, errors)
        elif claimed_by != "none" or claimed_at != "none":
            errors.append(f"{path}: only claimed Status may retain Claimed by/Claimed at")

        blocker_links = links(blocker_value)
        if blocker_value != "none" and not blocker_links:
            errors.append(f"{path}: Blocked by must be none or named Markdown links")
        blockers = tuple((path.parent / target).resolve() for _, target in blocker_links)
        units[path.resolve()] = Unit(
            doc=doc,
            kind=kind,
            mode=mode,
            status=status,
            claimed_by=claimed_by,
            claimed_at=claimed_at,
            blockers=blockers,
            outcome=outcome,
        )
    return units, documents


def load_promotions(
    map_dir: Path, errors: list[str]
) -> tuple[dict[Path, Promotion], dict[Path, Document]]:
    promotions: dict[Path, Promotion] = {}
    documents: dict[Path, Document] = {}
    directory = map_dir / "promotions"
    if not directory.is_dir():
        return promotions, documents

    for path in sorted(directory.glob("*.md")):
        if not is_within(path.resolve(), map_dir):
            errors.append(f"{path}: promotion record resolves outside the map directory")
            continue
        validate_slug(path.stem, "slice id", errors)
        doc = load_document(path, errors)
        if doc is None:
            continue
        documents[path.resolve()] = doc
        require_sections(doc, PROMOTION_SECTIONS, errors)
        status = scalar(doc.text, "Status") or ""
        source_map = scalar(doc.text, "Source map") or ""
        source_units_body = re.search(
            r"(?ms)^Source units:\s*\n(.*?)(?=^## |\Z)", doc.text
        )
        source_links = links(source_units_body.group(1)) if source_units_body else []
        blocking = scalar(doc.text, "Blocking") or ""
        approval = scalar(doc.text, "Human approval") or ""
        promoted_to_values = scalar_values(doc.text, "Promoted to")
        promoted_to = promoted_to_values[0] if len(promoted_to_values) == 1 else ""

        if status not in {"proposed", "approved", "promoted", "rejected", "superseded"}:
            errors.append(f"{path}: invalid promotion Status: {status}")
        if (path.parent / source_map).resolve() != (map_dir / "MAP.md").resolve():
            errors.append(f"{path}: Source map must resolve to ../MAP.md")
        if not source_links:
            errors.append(f"{path}: Source units must contain named links")
        if status in {"approved", "promoted"}:
            if blocking != "none":
                errors.append(f"{path}: {status} promotion requires Blocking: none")
            if approval in {"", "none", "pending"}:
                errors.append(f"{path}: {status} promotion requires Human approval")
        if len(promoted_to_values) != 1:
            errors.append(f"{path}: requires exactly one 'Promoted to:' field")
        elif status == "promoted" and not valid_promoted_to(promoted_to):
            errors.append(
                f"{path}: promoted Status requires exactly one kebab-case run id or "
                "canonical /.recursive/deliveries/<delivery-id>/spec.md pointer"
            )
        elif status != "promoted" and promoted_to != "none":
            errors.append(f"{path}: non-promoted Status requires Promoted to: none")

        promotions[path.resolve()] = Promotion(
            doc=doc,
            status=status,
            source_units=tuple((path.parent / target).resolve() for _, target in source_links),
            blocking=blocking,
            human_approval=approval,
            promoted_to=promoted_to,
        )
    return promotions, documents


def validate_cycles(units: dict[Path, Unit], errors: list[str]) -> None:
    visiting: set[Path] = set()
    visited: set[Path] = set()

    def visit(path: Path, chain: list[Path]) -> None:
        if path in visiting:
            start = chain.index(path)
            cycle = " -> ".join(item.stem for item in chain[start:] + [path])
            errors.append(f"blocker cycle: {cycle}")
            return
        if path in visited or path not in units:
            return
        visiting.add(path)
        chain.append(path)
        for blocker in units[path].blockers:
            visit(blocker, chain)
        chain.pop()
        visiting.remove(path)
        visited.add(path)

    for path in units:
        visit(path, [])


def validate_map(map_dir: Path) -> tuple[dict[Path, Unit], list[str]]:
    map_dir = map_dir.resolve()
    errors: list[str] = []
    validate_slug(map_dir.name, "map id", errors)
    map_path = map_dir / "MAP.md"
    map_doc = None
    if not is_within(map_path.resolve(), map_dir):
        errors.append(f"{map_path}: map document resolves outside the map directory")
    else:
        map_doc = load_document(map_path, errors)
    units, unit_docs = load_units(map_dir, errors)
    promotions, promotion_docs = load_promotions(map_dir, errors)
    documents = {**unit_docs, **promotion_docs}
    if map_doc is not None:
        documents[map_doc.path.resolve()] = map_doc
        require_sections(map_doc, MAP_SECTIONS, errors)
        status = scalar(map_doc.text, "Status") or ""
        if status not in {"active", "complete", "stopped"}:
            errors.append(f"{map_doc.path}: invalid map Status: {status}")
        validate_map_date(map_doc, "Created", errors)
        validate_map_date(map_doc, "Updated", errors)

        validate_local_links(map_dir, documents, errors)

        for section_name, allowed_root in (
            ("Decisions so far", (map_dir / "units").resolve()),
            ("Candidate slices", (map_dir / "promotions").resolve()),
        ):
            for label, target in links(section(map_doc.text, section_name) or ""):
                resolved = validate_named_link(
                    map_doc.path, label, target, map_dir, documents, errors
                )
                if resolved is not None and resolved.parent != allowed_root:
                    errors.append(f"{map_doc.path}: {section_name} link points outside its owner directory")
                if (
                    section_name == "Decisions so far"
                    and resolved in units
                    and units[resolved].status != "resolved"
                ):
                    errors.append(
                        f"{map_doc.path}: Decisions so far may index only resolved units: {label}"
                    )

    for unit in units.values():
        blocker_value = scalar(unit.doc.text, "Blocked by") or ""
        for label, target in links(blocker_value):
            resolved = validate_named_link(
                unit.doc.path, label, target, map_dir, documents, errors
            )
            if resolved is not None and resolved.is_file() and resolved not in units:
                errors.append(f"{unit.doc.path}: blocker must reference a discovery unit")

    for promotion in promotions.values():
        source_body = re.search(
            r"(?ms)^Source units:\s*\n(.*?)(?=^## |\Z)", promotion.doc.text
        )
        for label, target in links(source_body.group(1) if source_body else ""):
            resolved = validate_named_link(
                promotion.doc.path, label, target, map_dir, documents, errors
            )
            if resolved is not None:
                unit = units.get(resolved)
                if unit is None and resolved.is_file():
                    errors.append(f"{promotion.doc.path}: source must reference a discovery unit")
                elif (
                    unit is not None
                    and promotion.status in {"approved", "promoted"}
                    and unit.status != "resolved"
                ):
                    errors.append(f"{promotion.doc.path}: approved source unit is not resolved: {unit.doc.title}")

    validate_cycles(units, errors)
    return units, errors


def frontier(units: dict[Path, Unit]) -> list[Unit]:
    result = []
    for unit in units.values():
        if unit.status != "open" or unit.claimed_by != "none":
            continue
        if all(units.get(blocker) is not None and units[blocker].status == "resolved" for blocker in unit.blockers):
            result.append(unit)
    return sorted(result, key=lambda item: item.doc.path.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "frontier"))
    parser.add_argument("map_dir", type=Path)
    args = parser.parse_args(argv)

    units, errors = validate_map(args.map_dir)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.command == "validate":
        print(f"valid: {args.map_dir}")
    else:
        root = args.map_dir.resolve()
        for unit in frontier(units):
            print(f"{unit.doc.title}\t{unit.doc.path.resolve().relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
