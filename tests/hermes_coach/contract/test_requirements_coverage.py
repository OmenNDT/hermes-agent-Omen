from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parents[3]
PROPOSAL = ROOT / "docs" / "hermes-coach-product-proposal.md"
TRACE = ROOT / "docs" / "hermes-coach-requirements-traceability.md"
REQUIREMENTS_MAP = ROOT / "hermes_coach" / "requirements_map.yaml"


def _load_map() -> dict:
    return yaml.safe_load(REQUIREMENTS_MAP.read_text(encoding="utf-8"))


def _section(text: str, title: str) -> str:
    match = re.search(
        rf"^## {re.escape(title)}\s*$\n(.*?)(?=^## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, f"Missing section: {title}"
    return match.group(1)


def _extract_ids(text: str, prefix: str, digits: int | None = None) -> list[str]:
    suffix = rf"\d{{{digits}}}" if digits else r"[A-Z][A-Z0-9-]*"
    return re.findall(rf"^\| `({re.escape(prefix)}{suffix})`", text, re.MULTILINE)


def test_requirements_map_matches_canonical_proposal_fingerprint() -> None:
    data = _load_map()
    actual = hashlib.sha256(PROPOSAL.read_bytes()).hexdigest()

    assert data["proposal"]["path"] == "docs/hermes-coach-product-proposal.md"
    assert data["proposal"]["sha256"] == actual


def test_all_proposal_headings_have_exactly_one_source_allocation() -> None:
    data = _load_map()
    headings = re.findall(r"^#{1,6} (.+)$", PROPOSAL.read_text(encoding="utf-8"), re.MULTILINE)
    expected_ids = [f"SRC-{index:03d}" for index in range(len(headings))]

    assert len(headings) == 112
    assert list(data["sources"]) == expected_ids
    assert len(set(data["sources"])) == len(expected_ids)
    for source_id, allocation in data["sources"].items():
        assert allocation["heading_index"] == int(source_id.removeprefix("SRC-"))
        assert allocation["traceability_row"] == source_id
        assert allocation["heading"] == headings[allocation["heading_index"]]
        assert re.fullmatch(r"HC-[A-Z-]+", allocation["family"])
        assert allocation["source_path"]
        assert allocation["architecture"]
        assert allocation["phases"]
        assert set(allocation["phases"]) <= set(range(1, 8))
        assert allocation["production"]
        assert allocation["verification"]


def test_source_and_acceptance_ids_match_traceability_catalogs() -> None:
    data = _load_map()
    trace = TRACE.read_text(encoding="utf-8")
    source_catalog = _section(trace, "Machine-Verifiable Heading Coverage Index")
    acceptance_catalog = _section(trace, "Acceptance-Criteria Allocation")

    assert set(data["sources"]) == set(_extract_ids(source_catalog, "SRC-", 3))
    assert set(data["acceptance_criteria"]) == set(_extract_ids(acceptance_catalog, "AC-", 2))
    assert len(data["acceptance_criteria"]) == 58

    source_rows = {}
    for line in source_catalog.splitlines():
        match = re.match(r"^\| `(SRC-\d{3})` \|", line)
        if match:
            columns = [column.strip() for column in line.split("|")]
            family_match = re.search(r"HC-[A-Z-]+", columns[3])
            assert family_match
            source_rows[match.group(1)] = {
                "source_path": columns[2],
                "family": family_match.group(),
                "architecture": [item.strip() for item in columns[4].split(";")],
            }
    for source_id, expected in source_rows.items():
        allocation = data["sources"][source_id]
        assert allocation["source_path"] == expected["source_path"]
        assert allocation["family"] == expected["family"]
        assert allocation["architecture"] == expected["architecture"]


def test_all_referenced_bundles_exist_in_the_traceability_catalog() -> None:
    data = _load_map()
    trace = TRACE.read_text(encoding="utf-8")
    production = set(_extract_ids(_section(trace, "Production File Bundles"), "P-"))
    verification = set(_extract_ids(_section(trace, "Verification File Bundles"), "T-"))

    assert set(data["production_bundles"]) == production
    assert set(data["verification_bundles"]) == verification
    assert len(production | verification) == 33

    for allocation in [*data["sources"].values(), *data["acceptance_criteria"].values()]:
        assert set(allocation["production"]) <= production
        assert set(allocation["verification"]) <= verification


def test_phase_one_source_scope_is_complete_and_partitioned() -> None:
    data = _load_map()
    phase = data["phase_1"]
    required = set(phase["required_sources"])
    scenario = set(phase["scenario_sources"])
    contract_only = set(phase["contract_only_sources"])
    expected = {
        *(f"SRC-{index:03d}" for index in range(0, 62)),
        *(f"SRC-{index:03d}" for index in range(70, 76)),
        *(f"SRC-{index:03d}" for index in range(87, 95)),
        *(f"SRC-{index:03d}" for index in range(96, 112)),
    }

    assert required == expected
    assert scenario.isdisjoint(contract_only)
    assert scenario | contract_only == required


def test_phase_two_scope_and_evidence_match_every_phase_two_allocation() -> None:
    data = _load_map()
    phase = data["phase_2"]
    expected_sources = {
        source_id
        for source_id, allocation in data["sources"].items()
        if 2 in allocation["phases"]
    }
    expected_acceptance = {
        acceptance_id
        for acceptance_id, allocation in data["acceptance_criteria"].items()
        if 2 in allocation["phases"]
    }

    assert set(phase["required_sources"]) == expected_sources
    assert set(phase["acceptance_ids"]) == expected_acceptance
    assert set(phase["production_bundles"]) <= set(data["production_bundles"])
    assert set(phase["verification_bundles"]) <= set(data["verification_bundles"])
    for relative_path in (*phase["production_files"], *phase["verification_files"]):
        assert (ROOT / relative_path).is_file(), relative_path


def test_phase_three_scope_and_evidence_match_every_phase_three_allocation() -> None:
    data = _load_map()
    phase = data["phase_3"]
    expected_sources = {
        source_id
        for source_id, allocation in data["sources"].items()
        if 3 in allocation["phases"]
    }
    expected_acceptance = {
        acceptance_id
        for acceptance_id, allocation in data["acceptance_criteria"].items()
        if 3 in allocation["phases"]
    }

    assert set(phase["required_sources"]) == expected_sources
    assert set(phase["acceptance_ids"]) == expected_acceptance
    assert set(phase["production_bundles"]) <= set(data["production_bundles"])
    assert set(phase["verification_bundles"]) <= set(data["verification_bundles"])
    for relative_path in (*phase["production_files"], *phase["verification_files"]):
        assert (ROOT / relative_path).is_file(), relative_path


def test_phase_four_scope_and_evidence_match_every_phase_four_allocation() -> None:
    data = _load_map()
    phase = data["phase_4"]
    expected_sources = {
        source_id
        for source_id, allocation in data["sources"].items()
        if 4 in allocation["phases"]
    }
    expected_acceptance = {
        acceptance_id
        for acceptance_id, allocation in data["acceptance_criteria"].items()
        if 4 in allocation["phases"]
    }

    assert set(phase["required_sources"]) == expected_sources
    assert set(phase["acceptance_ids"]) == expected_acceptance
    assert set(phase["production_bundles"]) <= set(data["production_bundles"])
    assert set(phase["verification_bundles"]) <= set(data["verification_bundles"])
    for relative_path in (*phase["production_files"], *phase["verification_files"]):
        assert (ROOT / relative_path).is_file(), relative_path


@pytest.mark.parametrize("phase_key", ["phase_3", "phase_4"])
def test_an_in_progress_phase_declares_its_progress_honestly(phase_key: str) -> None:
    """A partial phase must not read as finished evidence."""
    phase = _load_map()[phase_key]

    assert phase["status"] in {"in-progress", "completed"}
    if phase["status"] == "in-progress":
        assert phase["completed_steps"]
