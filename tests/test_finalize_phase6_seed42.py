from __future__ import annotations

import csv
import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/finalize_phase6_seed42.py"
SPEC = importlib.util.spec_from_file_location("finalize_phase6_seed42", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_owner_adjudication_hash_and_contract() -> None:
    approval = json.loads(
        (ROOT / "audits/phase6_seed42/owner_adjudication_approval.json").read_text()
    )
    owner = ROOT / approval["final_adjudication_csv"]
    assert MODULE.sha256_file(owner) == approval["final_adjudication_csv_sha256"]
    assert all(approval["reconstruction_contract"].values())


def test_owner_rows_match_seed42_sample_and_first_pass() -> None:
    first = {
        row["display_id"]: row
        for row in MODULE.read_csv(
            ROOT / "runs/v2/phase6_blind_judging_package/owner_judging_package.csv",
            MODULE.FIRST_PASS_FIELDS,
        )
    }
    sample = {
        row["display_id"]: row
        for row in MODULE.read_csv(
            ROOT / "runs/v2/phase6_regrade_package_seed42/regrade_package_seed42.csv",
            (
                "display_id",
                "query_id",
                "question",
                "reference_answer",
                "chunk_id",
                "source_document_title",
                "candidate_chunk",
                "second_relevance_grade",
                "second_rationale",
            ),
        )
    }
    owner = MODULE.read_csv(
        ROOT
        / "outputs/019f9e9c-e14b-7b51-87af-e2cfca5b2a6e"
        / "phase6_adjudication_final/phase6_owner_adjudication_14_FINAL.csv",
        MODULE.ADJUDICATION_FIELDS,
    )
    assert len(owner) == 14
    assert Counter(row["final_grade"] for row in owner) == Counter({"1": 3, "2": 11})
    for row in owner:
        assert row["display_id"] in sample
        assert row["first_pass_grade"] == first[row["display_id"]]["relevance_grade"]
        assert row["second_pass_grade"] != row["first_pass_grade"]
        assert row["owner_rationale"].strip()
        for field in MODULE.PROTECTED_FIELDS:
            assert row[field] == sample[row["display_id"]][field]


def test_kappa_hand_computed() -> None:
    first = [0, 0, 1, 1, 2, 2]
    second = [0, 0, 1, 2, 1, 2]
    assert MODULE.kappa(first, second, quadratic=False) == pytest.approx(0.5)
    assert MODULE.kappa(first, second, quadratic=True) == pytest.approx(0.75)


def test_frozen_seed42_outputs_are_internally_consistent() -> None:
    labels_path = ROOT / "data/v2/pilot/labels/phase6_final_human_labels_seed42.csv"
    qrels_path = (
        ROOT
        / "data/v2/pilot/qrels/pilot-qa-v2-final-pooled-phase6-seed42-owner-adjudicated.tsv"
    )
    manifest_path = ROOT / "audits/phase6_seed42/freeze/freeze_manifest.json"
    if not (labels_path.exists() and qrels_path.exists() and manifest_path.exists()):
        pytest.skip("seed-42 freeze command has not run yet")
    labels = MODULE.read_csv(labels_path, MODULE.FINAL_LABEL_FIELDS)
    qrels = [line.split("\t") for line in qrels_path.read_text().splitlines()]
    assert len(labels) == len(qrels) == 755
    assert Counter(row["final_relevance_grade"] for row in labels) == Counter(
        {"0": 572, "1": 89, "2": 94}
    )
    assert Counter(row["label_source"] for row in labels) == Counter(
        {
            "owner_first_pass_unsampled_seed42": 641,
            "owner_regrade_agreement_seed42": 100,
            "owner_adjudication_seed42": 14,
        }
    )
    expected = sorted(
        (row["query_id"], "0", row["chunk_id"], row["final_relevance_grade"])
        for row in labels
    )
    assert [tuple(row) for row in qrels] == expected
    manifest = json.loads(manifest_path.read_text())
    assert manifest["historical_seed123_artifacts_modified"] is False
    for path, digest in manifest["code_hashes"].items():
        assert MODULE.sha256_file(ROOT / path) == digest
    for path, digest in manifest["outputs"].items():
        assert MODULE.sha256_file(ROOT / path) == digest
