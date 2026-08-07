#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const source = path.join(root, "submission/human_review/phase8_r4/phase8_r4_generation_human_review_100_BLINDED.csv");
const outDir = path.join(root, "outputs/phase9_h5");
const outPath = path.join(outDir, "phase9_h5_claim_review_150_DRAFT.xlsx");

const csvText = await fs.readFile(source, "utf8");
const imported = await Workbook.fromCSV(csvText, { sheetName: "Source" });
const sourceSheet = imported.worksheets.getItem("Source");
const sourceRows = sourceSheet.getUsedRange(true).values;
const header = sourceRows[0].map(v => String(v ?? "").replace(/^\uFEFF/, ""));
const idx = Object.fromEntries(header.map((name, i) => [name, i]));
const required = ["review_row_id", "blinded_request_id", "question", "reference_answer", "evidence_E01", "evidence_E02", "evidence_E03", "generated_answer", "model_abstained", "model_abstention_reason", "cited_evidence_ids"];
for (const name of required) if (!(name in idx)) throw new Error(`missing source column: ${name}`);

const records = sourceRows.slice(1).filter(row => row[idx.blinded_request_id]).map((row, i) => ({
  answer_slot_id: `H5A${String(i + 1).padStart(3, "0")}`,
  protected_status: "READY_EXISTING_R4",
  blinded_request_id: String(row[idx.blinded_request_id]),
  question: String(row[idx.question] ?? ""),
  reference_answer: String(row[idx.reference_answer] ?? ""),
  evidence_E01: String(row[idx.evidence_E01] ?? ""),
  evidence_E02: String(row[idx.evidence_E02] ?? ""),
  evidence_E03: String(row[idx.evidence_E03] ?? ""),
  generated_answer: String(row[idx.generated_answer] ?? ""),
  model_abstained: String(row[idx.model_abstained] ?? ""),
  model_abstention_reason: String(row[idx.model_abstention_reason] ?? ""),
  cited_evidence_ids: String(row[idx.cited_evidence_ids] ?? ""),
}));
if (records.length !== 100) throw new Error(`expected 100 existing records, found ${records.length}`);
for (let i = 100; i < 150; i++) records.push({
  answer_slot_id: `H5A${String(i + 1).padStart(3, "0")}`,
  protected_status: "PENDING_GENERATION",
  blinded_request_id: `PENDING_H5_${String(i + 1).padStart(3, "0")}`,
  question: "PENDING: ten additional locked-test questions × five systems",
  reference_answer: "",
  evidence_E01: "",
  evidence_E02: "",
  evidence_E03: "",
  generated_answer: "",
  model_abstained: "",
  model_abstention_reason: "",
  cited_evidence_ids: "",
});

const wb = Workbook.create();
const instructions = wb.worksheets.add("Instructions");
const revA = wb.worksheets.add("Reviewer A");
const revB = wb.worksheets.add("Reviewer B");
const adjudication = wb.worksheets.add("Adjudication");
for (const sheet of [instructions, revA, revB, adjudication]) sheet.showGridLines = false;

instructions.getRange("A1:B1").merge();
instructions.getRange("A1").values = [["H5 Claim-Level Faithfulness Review — 150-slot Draft"]];
instructions.getRange("A1:B1").format = { fill: "#16324F", font: { bold: true, color: "#FFFFFF", size: 16 }, rowHeight: 32, verticalAlignment: "center" };
const notes = [
  ["Status", "DRAFT — 100 existing answers ready; 50 additional generations pending. Do not start scoring until all 150 rows show READY_FROZEN."],
  ["Blinding", "Reviewer sheets intentionally omit system ID and retrieval metrics."],
  ["Claim unit", "Count each externally verifiable factual assertion once. Split compound claims when components can differ in support."],
  ["Fully supported", "Evidence directly supports complete claim."],
  ["Partially supported", "Evidence supports only part of claim or requires material inference."],
  ["Unsupported", "Evidence does not support claim."],
  ["Contradicted", "Evidence conflicts with claim."],
  ["Primary score", "(fully supported + 0.5 × partially supported) / total verifiable claims."],
  ["Completion", "Set review_status=COMPLETE only after counts reconcile exactly to total claims."],
  ["Adjudication", "Required when reviewers disagree on total claims or faithfulness ratio by more than 0.10."],
];
instructions.getRange(`A3:B${notes.length + 2}`).values = notes;
instructions.getRange("A3:A12").format = { fill: "#D9EAF7", font: { bold: true, color: "#16324F" }, verticalAlignment: "top" };
instructions.getRange("B3:B12").format = { wrapText: true, verticalAlignment: "top" };
instructions.getRange("A3:B12").format.borders = { insideHorizontal: { style: "thin", color: "#D0D7DE" }, outside: { style: "thin", color: "#9AA7B2" } };
instructions.getRange("A:A").format.columnWidth = 22;
instructions.getRange("B:B").format.columnWidth = 96;

const reviewHeaders = ["answer_slot_id", "protected_status", "blinded_request_id", "question", "reference_answer", "evidence_E01", "evidence_E02", "evidence_E03", "generated_answer", "model_abstained", "model_abstention_reason", "cited_evidence_ids", "reviewer_id", "total_verifiable_claims", "fully_supported_claims", "partially_supported_claims", "unsupported_claims", "contradicted_claims", "faithfulness_ratio", "hallucination_count", "review_status", "reviewer_notes"];
const protectedRows = records.map(r => [r.answer_slot_id, r.protected_status, r.blinded_request_id, r.question, r.reference_answer, r.evidence_E01, r.evidence_E02, r.evidence_E03, r.generated_answer, r.model_abstained, r.model_abstention_reason, r.cited_evidence_ids]);

function buildReviewer(sheet, reviewerLabel) {
  sheet.getRange("A1:V1").values = [reviewHeaders];
  sheet.getRange("A1:V1").format = { fill: "#16324F", font: { bold: true, color: "#FFFFFF" }, wrapText: true, rowHeight: 34, verticalAlignment: "center" };
  sheet.getRange("A2:L151").values = protectedRows;
  sheet.getRange("M2:M151").values = records.map(() => [reviewerLabel]);
  sheet.getRange("N2:R151").values = records.map(() => [null, null, null, null, null]);
  sheet.getRange("S2").formulas = [["=IF(N2>0,(O2+0.5*P2)/N2,\"\")"]];
  sheet.getRange("S2:S151").fillDown();
  sheet.getRange("T2").formulas = [["=IF(N2>0,Q2+R2,\"\")"]];
  sheet.getRange("T2:T151").fillDown();
  sheet.getRange("U2:U151").values = records.map(() => ["NOT_STARTED"]);
  sheet.getRange("V2:V151").values = records.map(() => [""]);
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(3);
  sheet.getRange("A2:L151").format = { fill: "#F3F6F8", verticalAlignment: "top", wrapText: true };
  sheet.getRange("M2:V151").format = { fill: "#FFF8E1", verticalAlignment: "top", wrapText: true };
  sheet.getRange("N2:R151").dataValidation = { rule: { type: "whole", operator: "between", formula1: 0, formula2: 100 } };
  sheet.getRange("U2:U151").dataValidation = { rule: { type: "list", values: ["NOT_STARTED", "IN_PROGRESS", "COMPLETE", "NO_VERIFIABLE_CLAIMS"] } };
  sheet.getRange("S2:S151").format.numberFormat = "0.000";
  sheet.getRange("A1:V151").format.borders = { insideHorizontal: { style: "thin", color: "#E3E8EC" }, outside: { style: "thin", color: "#AAB5BF" } };
  const widths = [13,20,22,35,35,42,42,42,42,12,28,18,14,12,12,12,12,12,14,12,16,30];
  widths.forEach((w, i) => sheet.getRangeByIndexes(0, i, 151, 1).format.columnWidth = w);
  sheet.getRange("B102:B151").format = { fill: "#FDE2E1", font: { bold: true, color: "#8B1E1E" } };
}
buildReviewer(revA, "REVIEWER_A");
buildReviewer(revB, "REVIEWER_B");

const adjHeaders = ["answer_slot_id", "protected_status", "blinded_request_id", "reviewer_A_ratio", "reviewer_B_ratio", "absolute_difference", "adjudication_required", "final_total_claims", "final_fully_supported", "final_partially_supported", "final_unsupported", "final_contradicted", "final_faithfulness_ratio", "adjudicator_id", "adjudication_status", "adjudication_notes"];
adjudication.getRange("A1:P1").values = [adjHeaders];
adjudication.getRange("A1:P1").format = { fill: "#16324F", font: { bold: true, color: "#FFFFFF" }, wrapText: true, rowHeight: 34 };
adjudication.getRange("A2:C151").values = records.map(r => [r.answer_slot_id, r.protected_status, r.blinded_request_id]);
adjudication.getRange("D2").formulas = [["='Reviewer A'!S2"]]; adjudication.getRange("D2:D151").fillDown();
adjudication.getRange("E2").formulas = [["='Reviewer B'!S2"]]; adjudication.getRange("E2:E151").fillDown();
adjudication.getRange("F2").formulas = [["=IF(AND(D2<>\"\",E2<>\"\"),ABS(D2-E2),\"\")"]]; adjudication.getRange("F2:F151").fillDown();
adjudication.getRange("G2").formulas = [["=IF(OR('Reviewer A'!N2<>'Reviewer B'!N2,F2>0.1),\"YES\",\"NO\")"]]; adjudication.getRange("G2:G151").fillDown();
adjudication.getRange("H2:L151").values = records.map(() => [null, null, null, null, null]);
adjudication.getRange("M2").formulas = [["=IF(H2>0,(I2+0.5*J2)/H2,\"\")"]]; adjudication.getRange("M2:M151").fillDown();
adjudication.getRange("N2:P151").values = records.map(() => ["", "PENDING", ""]);
adjudication.getRange("H2:L151").dataValidation = { rule: { type: "whole", operator: "between", formula1: 0, formula2: 100 } };
adjudication.getRange("O2:O151").dataValidation = { rule: { type: "list", values: ["PENDING", "COMPLETE", "NO_VERIFIABLE_CLAIMS"] } };
adjudication.getRange("D2:F151").format.numberFormat = "0.000";
adjudication.getRange("M2:M151").format.numberFormat = "0.000";
adjudication.freezePanes.freezeRows(1); adjudication.freezePanes.freezeColumns(3);
adjudication.getRange("A2:G151").format = { fill: "#F3F6F8", wrapText: true };
adjudication.getRange("H2:P151").format = { fill: "#FFF8E1", wrapText: true };
adjudication.getRange("A1:P151").format.borders = { insideHorizontal: { style: "thin", color: "#E3E8EC" }, outside: { style: "thin", color: "#AAB5BF" } };
const aw = [13,20,22,14,14,14,18,14,14,14,14,14,16,16,18,32];
aw.forEach((w, i) => adjudication.getRangeByIndexes(0, i, 151, 1).format.columnWidth = w);

await fs.mkdir(outDir, { recursive: true });
const preview = await wb.render({ sheetName: "Instructions", range: "A1:B12", scale: 1.4, format: "png" });
await fs.writeFile(path.join(outDir, "phase9_h5_instructions_preview.png"), new Uint8Array(await preview.arrayBuffer()));
const reviewerPreview = await wb.render({ sheetName: "Reviewer A", range: "A1:V8", scale: 0.8, format: "png" });
await fs.writeFile(path.join(outDir, "phase9_h5_reviewer_preview.png"), new Uint8Array(await reviewerPreview.arrayBuffer()));
const reviewerBPreview = await wb.render({ sheetName: "Reviewer B", range: "A1:V8", scale: 0.8, format: "png" });
await fs.writeFile(path.join(outDir, "phase9_h5_reviewer_b_preview.png"), new Uint8Array(await reviewerBPreview.arrayBuffer()));
const adjudicationPreview = await wb.render({ sheetName: "Adjudication", range: "A1:P10", scale: 0.9, format: "png" });
await fs.writeFile(path.join(outDir, "phase9_h5_adjudication_preview.png"), new Uint8Array(await adjudicationPreview.arrayBuffer()));
const check = await wb.inspect({ kind: "table", sheetId: "Reviewer A", range: "A1:V5", include: "values,formulas", tableMaxRows: 5, tableMaxCols: 22 });
await fs.writeFile(path.join(outDir, "phase9_h5_inspect.ndjson"), check.ndjson);
const errors = await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 300 }, summary: "final formula error scan" });
await fs.writeFile(path.join(outDir, "phase9_h5_formula_errors.ndjson"), errors.ndjson);
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(outPath);
console.log(outPath);
