import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const repo = process.cwd();
const chunksPath = path.join(repo, "runs/phase8_r4_improvements/corpus/chunks_section_aware_450w.jsonl");
const qaPath = path.join(repo, "runs/phase8_r4_improvements/benchmark/qa_dev_test.jsonl");
const outDir = path.join(repo, "submission/human_review/phase8_option_b_holdout");
const outPath = path.join(outDir, "phase8_option_b_holdout_review_12.xlsx");

const parseJsonl = (text) => text.trim().split(/\r?\n/).filter(Boolean).map(JSON.parse);
const chunks = parseJsonl(await fs.readFile(chunksPath, "utf8"));
const priorQa = parseJsonl(await fs.readFile(qaPath, "utf8"));
const chunkById = new Map(chunks.map((row) => [row.chunk_id, row]));
const priorSourceDocs = new Set(priorQa.flatMap((row) => row.source_doc_ids));

const candidates = [
  {
    id: "holdout_001", category: "exact_match", difficulty: "easy",
    question: "What monthly nutritional-support payment does Nikshay Poshan Yojana provide to each notified tuberculosis patient?",
    answer: "Nikshay Poshan Yojana provides ₹1,000 per month to each notified tuberculosis patient for nutritional support.",
    chunks: ["r4chunk_eff90d218b78"], rationale: "Direct benefit lookup from an unused scheme document."
  },
  {
    id: "holdout_002", category: "exact_match", difficulty: "easy",
    question: "What government stipend support is available per apprentice per month under NAPS-2?",
    answer: "The Government of India provides up to 25% of the stipend paid by the establishment, capped at ₹1,500 per apprentice per month.",
    chunks: ["r4chunk_ff865c03eb94"], rationale: "Direct amount lookup from an unused scheme document."
  },
  {
    id: "holdout_003", category: "terminology_heavy", difficulty: "easy",
    question: "What does ABVKY stand for?",
    answer: "Atal Beemit Vyakti Kalyan Yojana.",
    chunks: ["r4chunk_edb59203a74e"], rationale: "Acronym expansion stated in source."
  },
  {
    id: "holdout_004", category: "terminology_heavy", difficulty: "easy",
    question: "In maternal healthcare, what does SUMAN stand for?",
    answer: "Surakshit Matritva Aashwasan.",
    chunks: ["r4chunk_a0900cbfdc60"], rationale: "Acronym expansion stated in source."
  },
  {
    id: "holdout_005", category: "paraphrase", difficulty: "medium",
    question: "Must an eligible family complete a separate enrollment process before receiving PM-JAY coverage?",
    answer: "No. PM-JAY is entitlement-based; families identified by the government through rural deprivation or urban occupational criteria are entitled without a separate enrollment process.",
    chunks: ["r4chunk_9aa3758f45fd"], rationale: "Natural-language reformulation of source FAQ."
  },
  {
    id: "holdout_006", category: "paraphrase", difficulty: "medium",
    question: "How does PMAY-G determine which rural households should receive housing assistance?",
    answer: "PMAY-G uses housing-deprivation parameters from SECC 2011 and then has the identified households verified by Gram Sabhas, subject to the scheme's exclusion and prioritization rules.",
    chunks: ["r4chunk_368521c6253d"], rationale: "Paraphrases beneficiary-selection procedure."
  },
  {
    id: "holdout_007", category: "entity_relation", difficulty: "medium",
    question: "How are JSSK and SUMAN related through free maternal and newborn healthcare at public facilities?",
    answer: "Both provide free maternal and newborn healthcare at public facilities. JSSK specifies free delivery including caesarean section, diagnostics, drugs, diet, transport, and care for sick newborns or infants; SUMAN guarantees zero-cost, respectful maternal and newborn services including antenatal care, delivery, postnatal care, drugs, diagnostics, blood, and transport.",
    chunks: ["r4chunk_c13b4f76aa50", "r4chunk_a0900cbfdc60"], rationale: "Connects two unused schemes through explicit shared services."
  },
  {
    id: "holdout_008", category: "entity_relation", difficulty: "medium",
    question: "How are Pradhan Mantri Shram Yogi Maan-dhan and the National Pension Scheme for Traders and Self-Employed Persons related through pension design?",
    answer: "Both are voluntary contributory social-security schemes under the Ministry of Labour and Employment that target workers aged 18–40, use matching government contributions, and promise an assured ₹3,000 monthly pension after age 60. Their target groups differ: unorganised workers with monthly income up to ₹15,000 versus small traders and self-employed persons subject to an annual-turnover limit.",
    chunks: ["r4chunk_be06a5d0c086", "r4chunk_39d6f99302e7"], rationale: "Connects two unused pension schemes while preserving target-group distinction."
  },
  {
    id: "holdout_009", category: "multi_hop", difficulty: "hard",
    question: "Compare the beneficiary conditions and cash support provided by Nikshay Poshan Yojana and Atal Beemit Vyakti Kalyan Yojana.",
    answer: "Nikshay Poshan Yojana supports tuberculosis patients notified on or after 1 April 2018 and registered on NIKSHAY with ₹1,000 per month for nutrition. ABVKY supports eligible insured persons who become unemployed, providing 50% of average daily earnings for up to 90 days, subject to insurable-employment and contribution conditions.",
    chunks: ["r4chunk_eff90d218b78", "r4chunk_edb59203a74e"], rationale: "Requires combining eligibility and benefit evidence across two documents."
  },
  {
    id: "holdout_010", category: "multi_hop", difficulty: "hard",
    question: "How do PMAY-G and PM-JAY both use SECC information, and what different need does each scheme address?",
    answer: "Both use Socio-Economic and Caste Census information to identify eligible households. PMAY-G uses housing-deprivation parameters, followed by Gram Sabha verification, to address rural housing need; PM-JAY uses rural deprivation and urban occupational criteria to provide cashless secondary and tertiary hospital coverage to poor and vulnerable families.",
    chunks: ["r4chunk_368521c6253d", "r4chunk_3d71412d8768", "r4chunk_78112568b17a"], rationale: "Requires joining identification method and programme purpose across two documents."
  },
  {
    id: "holdout_011", category: "synthesis", difficulty: "hard",
    question: "Answer both parts from the evidence: (1) What does NAPS-2 seek to promote and what stipend support does it provide? (2) What housing assistance does PMAY-G provide in plain and hilly or difficult areas?",
    answer: "(1) NAPS-2 promotes apprenticeship training through partial stipend support, ecosystem capacity building, and stakeholder advocacy; government support is up to 25% of stipend, capped at ₹1,500 per apprentice per month. (2) PMAY-G provides ₹1,20,000 per unit in plain areas and ₹1,30,000 per unit in hilly, difficult, and specified IAP areas.",
    chunks: ["r4chunk_b25e704a8a61", "r4chunk_ff865c03eb94", "r4chunk_048f6a378d02"], rationale: "Two-part synthesis across separate unused programmes."
  },
  {
    id: "holdout_012", category: "synthesis", difficulty: "hard",
    question: "Answer both parts from the evidence: (1) How can a SUMAN beneficiary register a grievance, and what resolution period is stated? (2) Who qualifies for Nikshay Poshan Yojana and what monthly benefit is provided?",
    answer: "(1) A SUMAN grievance can be registered through the 104 toll-free helpline, SUMAN web portal, or facility helpdesk; time-bound resolution is within 21 days. (2) Tuberculosis patients notified on or after 1 April 2018 and registered on NIKSHAY qualify for ₹1,000 per month in nutritional support.",
    chunks: ["r4chunk_8f6ba9951c7e", "r4chunk_eff90d218b78"], rationale: "Two-part synthesis across maternal-health and TB-support evidence."
  },
];

for (const candidate of candidates) {
  candidate.evidence = candidate.chunks.map((id) => {
    const row = chunkById.get(id);
    if (!row) throw new Error(`Missing evidence chunk: ${id}`);
    return row;
  });
  candidate.sourceDocs = [...new Set(candidate.evidence.map((row) => row.doc_id))];
  if (candidate.sourceDocs.some((id) => priorSourceDocs.has(id))) {
    throw new Error(`Candidate ${candidate.id} uses prior R4 gold-source document`);
  }
}

const workbook = Workbook.create();
const instructions = workbook.worksheets.add("Instructions");
const review = workbook.worksheets.add("Review");
const evidence = workbook.worksheets.add("Evidence");
const lists = workbook.worksheets.add("Lists");
workbook.comments.setSelf({ displayName: "Amulya Gupta" });

instructions.showGridLines = false;
instructions.getRange("A1:H1").merge();
instructions.getRange("A1").values = [["Phase 8 Option B — Independent Holdout Owner Review"]];
instructions.getRange("A1:H1").format = { fill: "#17324D", font: { bold: true, color: "#FFFFFF", size: 16 }, rowHeight: 30 };
const instructionRows = [
  ["Status", "DRAFT — no retrieval or generation may run before owner review and freeze."],
  ["Scope", "12 candidate questions; exactly 2 per category. All source documents were unused as gold sources in the prior 100-question R4 benchmark."],
  ["Owner task", "Complete yellow columns on Review sheet. Use yes/no/uncertain for three validity checks, pass/fail/uncertain for leakage check, and accept/revise/reject for overall decision."],
  ["Revision rule", "If decision is revise, enter revised question and/or revised reference answer. Do not edit protected candidate, source-document, or evidence-ID columns."],
  ["Freeze gate", "All 12 decisions complete; no uncertain values; exactly 2 accepted/revised questions per category; protected fields unchanged; deterministic hashes recorded."],
  ["Claim boundary", "Before freeze these rows are candidates only. After untouched execution, report holdout separately from pilot and exploratory R4 metrics."],
];
instructions.getRange(`A3:B${2 + instructionRows.length}`).values = instructionRows;
instructions.getRange("A3:A8").format = { fill: "#DCE6F1", font: { bold: true, color: "#17324D" }, verticalAlignment: "top" };
instructions.getRange("B3:B8").format = { wrapText: true, verticalAlignment: "top" };
instructions.getRange("A3:B8").format.borders = { preset: "outside", style: "thin", color: "#AAB7C4" };
instructions.getRange("A:A").format.columnWidth = 20;
instructions.getRange("B:B").format.columnWidth = 110;
instructions.getRange("3:8").format.rowHeight = 45;

const headers = [
  "review_row_id", "category", "difficulty", "candidate_question", "candidate_reference_answer",
  "source_document_ids", "gold_evidence_ids", "construction_rationale", "prior_gold_source_check",
  "owner_question_valid", "owner_answer_valid", "owner_evidence_complete", "owner_leakage_check",
  "owner_decision", "owner_revised_question", "owner_revised_answer", "owner_notes", "row_complete"
];
const reviewRows = candidates.map((c) => [
  c.id, c.category, c.difficulty, c.question, c.answer, c.sourceDocs.join(" | "), c.chunks.join(" | "),
  c.rationale, "PASS — unused prior gold source", "", "", "", "", "", "", "", "", ""
]);
review.getRange(`A1:R${reviewRows.length + 1}`).values = [headers, ...reviewRows];
review.getRange("A1:R1").format = { fill: "#17324D", font: { bold: true, color: "#FFFFFF" }, wrapText: true, rowHeight: 36 };
review.getRange("A2:I13").format = { fill: "#F2F5F8", verticalAlignment: "top", wrapText: true };
review.getRange("J2:Q13").format = { fill: "#FFF2CC", verticalAlignment: "top", wrapText: true };
review.getRange("R2:R13").formulas = candidates.map((_, i) => [`=IF(AND(J${i + 2}<>\"\",K${i + 2}<>\"\",L${i + 2}<>\"\",M${i + 2}<>\"\",N${i + 2}<>\"\",IF(N${i + 2}=\"revise\",OR(O${i + 2}<>\"\",P${i + 2}<>\"\"),TRUE)),\"COMPLETE\",\"PENDING\")`]);
review.getRange("R2:R13").format = { fill: "#E2F0D9", font: { bold: true }, horizontalAlignment: "center" };
review.getRange("J2:L13").dataValidation = { rule: { type: "list", values: ["yes", "no", "uncertain"] } };
review.getRange("M2:M13").dataValidation = { rule: { type: "list", values: ["pass", "fail", "uncertain"] } };
review.getRange("N2:N13").dataValidation = { rule: { type: "list", values: ["accept", "revise", "reject"] } };
review.getRange("R2:R13").conditionalFormats.add("containsText", { text: "PENDING", format: { fill: "#F4CCCC", font: { color: "#9C0006", bold: true } } });
review.getRange("R2:R13").conditionalFormats.add("containsText", { text: "COMPLETE", format: { fill: "#D9EAD3", font: { color: "#274E13", bold: true } } });
review.freezePanes.freezeRows(1);
review.freezePanes.freezeColumns(3);
review.getRange("A:A").format.columnWidth = 16;
review.getRange("B:C").format.columnWidth = 18;
review.getRange("D:E").format.columnWidth = 52;
review.getRange("F:H").format.columnWidth = 34;
review.getRange("I:I").format.columnWidth = 25;
review.getRange("J:N").format.columnWidth = 18;
review.getRange("O:Q").format.columnWidth = 40;
review.getRange("R:R").format.columnWidth = 15;
review.getRange("2:13").format.rowHeight = 96;
review.tables.add("A1:R13", true, "HoldoutReviewTable").style = "TableStyleMedium2";

const evidenceHeaders = ["review_row_id", "evidence_order", "chunk_id", "document_id", "scheme_name", "ministry", "source_url", "evidence_text"];
const evidenceRows = candidates.flatMap((c) => c.evidence.map((row, index) => [
  c.id, index + 1, row.chunk_id, row.doc_id, row.scheme_name ?? "", row.ministry ?? "", row.url ?? row.final_url ?? "", row.text
]));
evidence.getRange(`A1:H${evidenceRows.length + 1}`).values = [evidenceHeaders, ...evidenceRows];
evidence.getRange(`A1:H1`).format = { fill: "#17324D", font: { bold: true, color: "#FFFFFF" }, wrapText: true };
evidence.getRange(`A2:H${evidenceRows.length + 1}`).format = { verticalAlignment: "top", wrapText: true };
evidence.freezePanes.freezeRows(1);
evidence.getRange("A:F").format.columnWidth = 23;
evidence.getRange("G:G").format.columnWidth = 45;
evidence.getRange("H:H").format.columnWidth = 100;
evidence.getRange(`2:${evidenceRows.length + 1}`).format.rowHeight = 90;
evidence.tables.add(`A1:H${evidenceRows.length + 1}`, true, "EvidenceTable").style = "TableStyleMedium2";

lists.getRange("A1:C5").values = [
  ["validity", "leakage", "decision"],
  ["yes", "pass", "accept"],
  ["no", "fail", "revise"],
  ["uncertain", "uncertain", "reject"],
  ["", "", ""]
];
lists.getRange("A1:C1").format = { fill: "#17324D", font: { bold: true, color: "#FFFFFF" } };

await fs.mkdir(outDir, { recursive: true });
const previewDir = path.join(outDir, ".preview");
await fs.mkdir(previewDir, { recursive: true });
for (const sheetName of ["Instructions", "Review", "Evidence"]) {
  const blob = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheetName}.png`), new Uint8Array(await blob.arrayBuffer()));
}

const inspection = await workbook.inspect({ kind: "table", range: "Review!A1:R13", include: "values,formulas", tableMaxRows: 13, tableMaxCols: 18, maxChars: 12000 });
await fs.writeFile(path.join(previewDir, "review_inspection.ndjson"), inspection.ndjson, "utf8");
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
await fs.writeFile(path.join(previewDir, "formula_errors.ndjson"), errors.ndjson, "utf8");

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outPath);
console.log(outPath);
