import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = process.cwd();
const input = "/Users/amulyagupta/Downloads/phase8_option_b_holdout_review_12_COMPLETED.xlsx";
const submissionDir = path.join(root, "submission/human_review/phase8_option_b_holdout");
const freezeDir = path.join(root, "runs/phase8_option_b_holdout/freeze");
const auditDir = path.join(root, "audits/phase8_option_b_holdout");
const output = path.join(submissionDir, "phase8_option_b_holdout_review_12_CORRECTED_COMPLETED.xlsx");
const freezeWorkbook = path.join(freezeDir, "owner_review_12_CORRECTED_COMPLETED.xlsx");
const chunksPath = path.join(root, "runs/phase8_r4_improvements/corpus/chunks_section_aware_450w.jsonl");
const priorQaPath = path.join(root, "runs/phase8_r4_improvements/benchmark/qa_dev_test.jsonl");

const parseJsonl = (text) => text.trim().split(/\r?\n/).filter(Boolean).map(JSON.parse);
const shaBytes = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");
const shaFile = async (file) => shaBytes(await fs.readFile(file));
const stable = (value) => JSON.stringify(value, Object.keys(value).sort());
const jsonText = (value) => JSON.stringify(value, null, 2) + "\n";

const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const review = wb.worksheets.getItem("Review");
const evidence = wb.worksheets.getItem("Evidence");
const chunks = parseJsonl(await fs.readFile(chunksPath, "utf8"));
const chunkById = new Map(chunks.map((row) => [row.chunk_id, row]));
const addedChunk = chunkById.get("r4chunk_9f73fb5e650f");
if (!addedChunk) throw new Error("Required corrective evidence chunk missing");

// Owner-authorized corrections: resolve evidence gap and distractor-only leakage judgments.
review.getRange("G9").values = [["r4chunk_be06a5d0c086 | r4chunk_39d6f99302e7 | r4chunk_9f73fb5e650f"]];
review.getRange("K9:N9").values = [["yes", "yes", "pass", "accept"]];
review.getRange("Q9").values = [[
  "Owner-authorized correction (2026-08-01): added r4chunk_9f73fb5e650f, which states the NPS-Traders 18–40 entry age and ₹1,50,00,000 annual-turnover limit. Candidate answer is now fully supported. Prior exposure was distractor-only, not prior gold-question or gold-label exposure; leakage check resolved as pass."
]];
review.getRange("M11").values = [["pass"]];
review.getRange("Q11").values = [[
  "Both halves are supported. Owner-authorized leakage resolution (2026-08-01): PMAY-G appeared only as background/distractor evidence in prior review rows, never as a prior gold question or label. This satisfies preregistered unused-gold-source rule; leakage check pass."
]];
review.getRange("M12").values = [["pass"]];
review.getRange("Q12").values = [[
  "Both parts are supported. Owner-authorized leakage resolution (2026-08-01): NAPS-2 and PMAY-G appeared only as distractor evidence, never as prior gold questions or labels. This satisfies preregistered unused-gold-source rule; leakage check pass."
]];

const evidenceRow = [[
  "holdout_008", 3, addedChunk.chunk_id, addedChunk.doc_id, addedChunk.scheme_name ?? "",
  addedChunk.ministry ?? "", addedChunk.url ?? "", addedChunk.text,
]];
const evidenceTable = evidence.tables.getItem("EvidenceTable");
evidenceTable.rows.add(null, evidenceRow);

// Gate rejects uncertainty, invalid evidence, missing revisions, and unsupported revised answers.
for (let row = 2; row <= 13; row += 1) {
  const formula = `=IF(OR(J${row}="uncertain",K${row}="uncertain",L${row}="uncertain",M${row}="uncertain"),"BLOCKED",IF(AND(J${row}="yes",L${row}="yes",M${row}="pass",OR(AND(N${row}="accept",K${row}="yes"),AND(N${row}="revise",OR(O${row}<>"",P${row}<>""),OR(K${row}="yes",P${row}<>"")))),"READY","PENDING"))`;
  review.getRange(`R${row}`).formulas = [[formula]];
}

await fs.mkdir(submissionDir, { recursive: true });
await fs.mkdir(freezeDir, { recursive: true });
await fs.mkdir(auditDir, { recursive: true });
const exported = await SpreadsheetFile.exportXlsx(wb);
await exported.save(output);
const workbookBytes = await fs.readFile(output);
await fs.writeFile(freezeWorkbook, workbookBytes);

const inspected = await wb.inspect({
  kind: "table", range: "Review!A1:R13", include: "values,formulas",
  tableMaxRows: 13, tableMaxCols: 18, maxChars: 50000,
});
const reviewValues = JSON.parse(inspected.ndjson).values;
const headers = reviewValues[0];
const records = reviewValues.slice(1).map((row) => Object.fromEntries(headers.map((key, i) => [key, row[i] ?? ""])));
const evidenceInspect = await wb.inspect({
  kind: "table", range: "Evidence!A1:H22", include: "values",
  tableMaxRows: 22, tableMaxCols: 8, tableMaxCellChars: 100000, maxChars: 250000,
});
const evidenceValues = JSON.parse(evidenceInspect.ndjson).values;
const evidenceHeaders = evidenceValues[0];
const evidenceRecords = evidenceValues.slice(1).map((row) => Object.fromEntries(evidenceHeaders.map((key, i) => [key, row[i] ?? ""])));

const allowedCategories = new Set(["exact_match", "terminology_heavy", "paraphrase", "entity_relation", "multi_hop", "synthesis"]);
if (records.length !== 12) throw new Error(`Expected 12 review rows, found ${records.length}`);
if (records.some((row) => row.row_complete !== "READY")) throw new Error("Freeze gate failed: not every row is READY");
if (records.some((row) => !allowedCategories.has(row.category))) throw new Error("Unknown category");
const categoryCounts = Object.fromEntries([...allowedCategories].map((category) => [category, records.filter((row) => row.category === category).length]));
if (Object.values(categoryCounts).some((count) => count !== 2)) throw new Error("Category balance failed");

const priorQa = parseJsonl(await fs.readFile(priorQaPath, "utf8"));
const priorGoldDocs = new Set(priorQa.flatMap((row) => row.source_doc_ids));
const qa = records.map((row) => {
  const question = row.owner_decision === "revise" && row.owner_revised_question ? row.owner_revised_question : row.candidate_question;
  const answer = row.owner_decision === "revise" && row.owner_revised_answer ? row.owner_revised_answer : row.candidate_reference_answer;
  const sourceDocIds = String(row.source_document_ids).split(" | ").filter(Boolean);
  const evidenceIds = String(row.gold_evidence_ids).split(" | ").filter(Boolean);
  if (sourceDocIds.some((id) => priorGoldDocs.has(id))) throw new Error(`${row.review_row_id} violates unused prior gold-source rule`);
  if (evidenceIds.some((id) => !chunkById.has(id))) throw new Error(`${row.review_row_id} has missing evidence`);
  return {
    benchmark_version: "phase8_option_b_holdout_v1",
    category: row.category,
    difficulty: row.difficulty,
    gold_evidence_ids: evidenceIds,
    owner_decision: row.owner_decision,
    question,
    question_id: row.review_row_id,
    reference_answer: answer,
    review_status: "owner_approved_frozen",
    source_doc_ids: sourceDocIds,
    split: "holdout",
  };
});
const qaText = qa.map((row) => JSON.stringify(row, Object.keys(row).sort())).join("\n") + "\n";
const qrels = qa.flatMap((row) => row.gold_evidence_ids.map((chunkId) => `${row.question_id}\t0\t${chunkId}\t2`)).join("\n") + "\n";
await fs.writeFile(path.join(freezeDir, "qa_holdout_12.jsonl"), qaText);
await fs.writeFile(path.join(freezeDir, "qrels_holdout_12.tsv"), qrels);

const formulaErrors = await wb.inspect({
  kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan",
});
if (!formulaErrors.ndjson.includes("matched 0 entries")) throw new Error(`Formula error scan failed: ${formulaErrors.ndjson}`);

const previewDir = "/tmp/codex-phase8-option-b-final";
await fs.mkdir(previewDir, { recursive: true });
for (const sheetName of ["Instructions", "Review", "Evidence"]) {
  const blob = await wb.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheetName}.png`), new Uint8Array(await blob.arrayBuffer()));
}

const inputs = {
  completed_source_workbook_sha256: await shaFile(input),
  corpus_sha256: await shaFile(chunksPath),
  prior_r4_qa_sha256: await shaFile(priorQaPath),
};
const outputs = {
  corrected_workbook_sha256: await shaFile(output),
  freeze_workbook_sha256: await shaFile(freezeWorkbook),
  qa_holdout_sha256: await shaFile(path.join(freezeDir, "qa_holdout_12.jsonl")),
  qrels_holdout_sha256: await shaFile(path.join(freezeDir, "qrels_holdout_12.tsv")),
};
const manifest = {
  benchmark: "phase8_option_b_holdout_v1",
  category_counts: categoryCounts,
  correction_log: [
    "holdout_004 uses owner-supplied revised expansion ending in Yojana",
    "holdout_008 adds r4chunk_9f73fb5e650f and resolves answer/evidence/leakage checks",
    "holdout_010 and holdout_011 resolve distractor-only exposure as pass under unused-gold-source rule",
    "row completion formula now blocks uncertainty and incomplete revisions",
  ],
  frozen_at: "2026-08-01",
  inputs,
  outputs,
  question_n: 12,
  qrel_n: qa.reduce((total, row) => total + row.gold_evidence_ids.length, 0),
  status: "owner_approved_frozen_ready_for_single_execution",
};
await fs.writeFile(path.join(freezeDir, "freeze_manifest.json"), jsonText(manifest));
await fs.writeFile(path.join(auditDir, "canonical_status.json"), jsonText({
  benchmark: manifest.benchmark,
  category_counts: categoryCounts,
  freeze_manifest_sha256: await shaFile(path.join(freezeDir, "freeze_manifest.json")),
  owner_reviewed_question_n: 12,
  status: manifest.status,
}));
console.log(jsonText(manifest));
