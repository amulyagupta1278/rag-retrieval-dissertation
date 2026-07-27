# Relevance Grading — Instructions

**Task:** grade 114 short text passages · **Time:** about 1.5–2.5 hours · **Software needed:** a web browser

You do not need any background in this project. Everything you need is below.

---

## 1. What you're doing

A search system was asked 34 questions about Indian government welfare schemes. For each
question it returned passages ("chunks") from official scheme documents. Some are useful,
many are not — that's expected.

**Your job:** for each of 114 passages, decide how well it answers its question.

You are the *second* reader. Someone graded these before you, and their grades are hidden
from you on purpose. We compare the two sets afterwards to measure how reliable the
grading is. **So grade independently.** Don't try to guess what anyone else said. If you
disagree with what you imagine the first grader thought, that's fine — disagreement is
information, not error.

---

## 2. Setup

1. Open the folder you were sent.
2. Double-click **`GRADING_DASHBOARD.html`**.
3. It opens in your browser. Nothing installs, nothing uploads, no internet needed.

Your work **saves automatically in the browser** as you go. You can close the tab and come
back later — but **use the same browser on the same computer**, or the saved work won't be
there.

> Do **not** open the file `regrade_provenance_sealed_seed42.json`. That contains the first
> grader's answers. Opening it invalidates the whole exercise.

---

## 3. What's on screen

Each row shows three things:

| Panel | What it is | Do you judge it? |
|---|---|---|
| **Question** | what was asked | no |
| **Reference answer** (blue bar) | the known-correct answer | **no — this is your yardstick** |
| **Candidate chunk** | passage the system returned | **YES — this is what you grade** |

The reference answer is already verified correct. Never assess it. Use it as the standard
you measure the chunk against.

### The only question you're answering

> **Does this chunk contain the fact stated in the reference answer?**

---

## 4. The grades

| | When to use it |
|---|---|
| **2** | The chunk **states the fact**. The reference answer could be written from this passage alone. |
| **1** | The chunk is about the **right scheme and topic**, but the specific fact is **not there**. Useful context, doesn't answer. |
| **0** | **Wrong scheme**, or irrelevant, or misleading. |
| **U** | Genuinely impossible to judge. **Use very rarely** — every U has to be resolved later by hand. |

### Worked example

> **Question:** What annual hospitalisation cover does AB-PMJAY provide per family?
> **Reference:** AB-PMJAY provides cashless cover of ₹5 lakh per family per year.

- Chunk from **AB-PMJAY** saying *"₹5 lakh per family per year for secondary and tertiary
  hospitalisation"* → states the fact → **2**
- Chunk from **AB-PMJAY** explaining how to register and get an e-card → right scheme,
  no figure → **1**
- Chunk from **Pradhan Mantri Awas Yojana (housing)** → wrong scheme → **0**

---

## 5. Four traps — please read, these cause most errors

### Trap 1 — the fact is buried

Grade on **whether the fact is present**, not on what the chunk is *mostly* about.

A passage can be 90% about loan amounts and subsidies, and still contain one sentence
giving the answer. **That's a 2.** Long official documents bury key facts in the middle of
dense paragraphs constantly.

**→ Before grading, press `Ctrl+F` (`Cmd+F` on Mac) and search the chunk for the key
number or term from the reference answer.** Much faster and more reliable than reading.

### Trap 2 — collapsed text

Long chunks are cut off with a **"Show full chunk ▾"** link. The answer may be below the
fold. **Always expand long chunks before grading.**

### Trap 3 — well-written but wrong scheme

Every chunk is polished official government text. Fluency tells you nothing about
relevance. A beautifully written passage about pension schemes, returned for a housing
question, is a **0**.

### Trap 4 — near-identical scheme names

These are **different schemes**. Check the **Source:** line under each chunk.

- `Pradhan Mantri **Awaas** Yojana - **Gramin**` (rural housing) — note the double "a"
- `Pradhan Mantri **Awas** Yojana - **Urban**` (urban housing)
- `Pradhan Mantri Ujjwala Yojana` vs `Pradhan Mantri Ujjwala Yojana **2.0**`
- PMKVY 4.0 **Short-Term Training** vs **Recognition Of Prior Learning** vs **Special Projects**

A real near-miss from this data: a housing document contains "25 lakh/Unit". A health
question asks about "₹5 lakh cover". The digits overlap; the schemes don't. **Always
confirm the source document matches the scheme in the question.**

---

## 6. How to grade fast

Grade with the keyboard — you never need the mouse:

| Key | Action |
|---|---|
| `2` `1` `0` `U` | assign that grade, then **auto-advance** to the next row |
| `→` / `←` | next / previous row without grading |
| `Ctrl+F` / `Cmd+F` | search inside the chunk |

Other controls:

- **Left sidebar** — all 114 rows as coloured dots. Click any to jump. Grey = ungraded.
- **Next ungraded** (top) — skips to the first row you haven't done.
- **Rationale box** — optional, one line. Worth filling in when a call was close; it helps
  whoever reviews disagreements later.
- **Progress counter** (top right) — `graded/114`, then a colour breakdown.

Changed your mind? Click the row in the sidebar and press a different key. It overwrites.

---

## 7. Multi-part questions

A few questions ask about two or three schemes at once — *"How do three programmes address
rural housing, clean cooking, and food security?"*

A chunk will usually cover only **one** of those parts. Suggested approach:

- Chunk clearly states one component's mechanism → **2**
- Chunk is from a relevant scheme but doesn't state any component's mechanism → **1**
- Chunk is from none of the named schemes → **0**

Whatever you decide, **be consistent across all such questions**, and note your reasoning
in the rationale box the first time you hit one.

---

## 8. When you're finished

1. Check the counter reads **114/114**.
2. Click **Export CSV** (top right).
3. It downloads **`regrade_package_seed42_COMPLETED.csv`** — usually to your Downloads folder.
4. Send that file back.

If you export early it still works, but it will warn you how many rows are blank.

---

## 9. Common questions

**I'm not sure between two grades.**
Pick the lower one and write why in the rationale box. Borderline cases get reviewed by
hand later — that's what the second pass is for.

**The chunk starts mid-sentence.**
Normal. Documents were split into fixed-size pieces. Judge what's in front of you.

**Two rows look nearly identical.**
Also normal — overlapping passages from the same document. Grade each on its own.

**Can I use `U` when unsure?**
Please don't. `U` means *structurally impossible* to judge — e.g. the chunk is empty or
corrupted. "I'm uncertain" is not a `U`; make a call and note it.

**I lost my work.**
It saves per-browser, per-computer. If you switched browsers it won't carry over. Export
regularly if you're worried — you can re-import nothing, so keep the exported file safe.

**Should I look anything up online?**
No. Judge only the text shown. If the chunk doesn't say it, it isn't there.

---

## 10. Before you start — please record

Send these back along with the CSV:

- Your name
- Date(s) you did the grading
- Roughly how long it took
- Anything that confused you or any questions where the rubric felt wrong

This gets documented alongside the data.

**Thank you — careful work here directly determines the quality of the results.**
