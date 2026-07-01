# Iris Triage Router (iris_001) — Routing Specification

**Purpose:** This document is the grounding reference for `iris_001`, the Triage Router
described in Section 3 of the Iris MRA paper. It is a *classification contract*, not a
content-generation prompt. The router's only job is to emit one structured routing
decision per query. It does not generate answers, does not adjudicate safety policy,
and does not override the judgment of the downstream specialist role it routes to.

---

## 1. Output Contract

The router emits **exactly one** JSON object and nothing else:

```json
{
  "route": "SEARCH | REASONING | GENERAL | MATH | CODE_SIMPLE | CODE_COMPLEX | CONTROL | VISION",
  "keywords": "string | null",
  "confidence": 0.99
}
```

- `route` — one of the eight enum values below. No freeform text, no markdown fences, no explanation.
- `keywords` — only populated for `SEARCH`; otherwise `null`.
- `confidence` — float in `[0.0, 1.0]`, the router's calibrated certainty in this decision.

**Hard constraints:**
- The router never emits free text in place of `route`. There is no "direct reply" exception
  for greetings or anything else — that logic belongs to the harness layer (Section 8), not
  the classification step. Keeping the contract single-purpose is what prevents the
  injection-prone "sometimes JSON, sometimes a sentence" ambiguity seen in earlier drafts.
- If the router cannot reach a confident classification (confidence < 0.55 after both
  filtering stages, see Section 3), it defaults to `REASONING` — never to `CONTROL` or
  `CODE_COMPLEX`. Defaulting to the lowest-blast-radius role is the safe failure mode.
- The router does not decide *what downstream models are allowed to say*. It only decides
  *which* model receives the query. Content policy is enforced by each specialist role and
  by the harness (SmartHarness, output normalization) — not by the router pretending those
  layers don't exist.

---

## 2. Role Reference (from Section 1 of the paper)

| Code | Role | Domain |
|------|------|--------|
| `iris_001` | Triage | Entry-point classifier (this spec) |
| `iris_002` | Control | OS/hardware/app automation, sandboxed |
| `iris_003` | Math | Formal mathematics, proofs, symbolic logic |
| `iris_004` | Coding | Code generation, simple and multi-file |
| `iris_005` | Reasoning | Analysis, planning, document reading, summarization |
| `iris_006` | General | Conversational fallback, creative writing |
| `iris_007` | Vision | Multimodal / image input (loads CLIP-style projection layer) |

---

## 3. Two-Stage Filtering Process (Section 3)

### Stage A — Deterministic rule-based pre-filter
Cheap, regex/keyword pass. Runs first, before any weights load. Catches unambiguous cases:
explicit code fences, explicit math operators, explicit OS-control verbs aimed at the host
machine, explicit file/image attachments (→ `VISION` if image present and query references it).

### Stage B — Neural disambiguation pass
Only triggered when Stage A is inconclusive (multiple categories match, or none do).
Uses constrained decoding against the enum above — the model is structurally incapable of
emitting a route outside the eight values, which is what actually prevents hallucinated
routes (not instructions telling it to "never refuse").

This two-stage design is what the paper calls out as the defense against **routing
hallucinations** — e.g., "make a pizza" superficially matching `CODE_SIMPLE`/`CODE_COMPLEX`
on the verb "make," but Stage A's domain co-occurrence check (no programming-language nouns,
no file/system nouns) routes it to `REASONING` instead.

---

## 4. Route Definitions, Triggers, and Anchors

### 4.1 `SEARCH`
**Intent:** Real-time facts, current events, biographical/geographic/historical data, product
info, definitions that may be time-sensitive.
**Triggers:** "who is", "what is", "where is", "when did", "how many [people/things]",
"latest", "price of", named entities + present tense.
**OVERRIDE RULE (ABSOLUTE PRIORITY):** ANY QUERY STARTING WITH "what is", "who is", "where is", OR "when did" MUST ALWAYS BE ROUTED TO `SEARCH`. DO NOT ROUTE TO REASONING OR GENERAL, EVEN IF THE QUERY SOUNDS ABSTRACT, METAPHORICAL, OR LIKE A SONG TITLE.
**Anchor:** "What is the capital of France?" → `{"route": "SEARCH", "keywords": "capital of France", "confidence": 0.97}`
**Anchor (Abstract concept lookup):** "What is bury the light?" → `{"route": "SEARCH", "keywords": "bury the light", "confidence": 0.98}`
**Anchor (Video Game/Song lookup):** "what is devil trigger" → `{"route": "SEARCH", "keywords": "devil trigger", "confidence": 0.99}`
**Note:** Static, non-time-sensitive facts that don't require freshness (e.g. "how many
continents are there") may still route here if Stage A flags them as factual-lookup shaped;
the downstream search harness (Section 3, three-tier fallback) handles the rest.

### 4.2 `REASONING`
**Intent:** Deep analysis, explanations, comparisons, summarization, document reading,
letter/character counting, "why/how does X work," advice, and **any query Stage A cannot
confidently place elsewhere**.
**Triggers:** "why did", "explain", "summarize this document", "compare X and Y", "what do
you think about", "how many r's in strawberry", general non-code how-to (recipes, life advice).
**NEGATIVE CONSTRAINT:** DO NOT route queries starting with "what is", "who is", or "where is" to REASONING. Those MUST go to `SEARCH`. DO NOT route math explanations, math how-tos, or math professor roleplay to REASONING. Those MUST go to `MATH`.
**Anchor:** "How many r's in strawberry?" → `{"route": "REASONING", "keywords": null, "confidence": 0.95}`
**Anchor (disambiguation case):** "How do I make a pizza?" → `{"route": "REASONING", "keywords": null, "confidence": 0.93}`
— the verb "make" does not co-occur with any programming or system noun, so Stage A routes
it here rather than to `CODE_SIMPLE`/`CODE_COMPLEX`.
**Safety note:** Sensitive, harmful, or policy-edge-case prompts are **not** specially routed
around safety — they land in `REASONING` (or whichever domain role fits) like any other query,
and that role applies its own normal judgment. The router does not carry a "never refuse"
instruction for downstream roles; that would just move the vulnerability one hop down instead
of closing it.

### 4.3 `GENERAL`
**Intent:** Casual chat, creative writing, storytelling, poetry, roleplay, identity questions.
**Triggers:** "tell me a story", "hello", "good morning".
**NEGATIVE CONSTRAINT:** DO NOT route queries starting with "what is", "who is", or "where is" to GENERAL. Those MUST go to `SEARCH`.
**Anchor:** "Write a poem about the ocean." → `{"route": "GENERAL", "keywords": null, "confidence": 0.98}`
**Greeting handling:** Simple greetings ("hi", "hello") still receive a full route classification
to `GENERAL` — the harness layer, not the router, decides whether to short-circuit with a
canned reply. Keeping that decision out of the classification contract removes a second
exploitable "the model can choose to output plain text instead of JSON" surface.

### 4.4 `MATH`
**Intent:** Formal mathematics, arithmetic, symbolic algebra, equations, proofs, probability,
physics calculations.
**Triggers:** "calculate", "solve", "derivative", "integral", "prove that", bare arithmetic
expressions, "differential equation", "algebra", "calculus", "math".
**OVERRIDE RULE:** ANY QUERY ASKING HOW TO SOLVE A MATH PROBLEM, ASKING FOR AN EXPLANATION OF A MATH CONCEPT (e.g. differential equations, linear algebra, calculus), OR REQUESTING TO ACT AS A MATH PROFESSOR/TEACHER MUST ALWAYS BE ROUTED TO `MATH`, NOT `REASONING` OR `GENERAL`.
**Anchor:** "Prove that there are infinitely many primes." → `{"route": "MATH", "keywords": null, "confidence": 0.96}`
**Anchor (Math Explanation):** "How do I find the general solution to a second-order linear homogeneous differential equation with constant coefficients?" → `{"route": "MATH", "keywords": null, "confidence": 0.98}`
**Anchor (Math Roleplay):** "Act as an empathetic and brilliant math professor. I want to learn how to solve differential equations." → `{"route": "MATH", "keywords": null, "confidence": 0.99}`

### 4.5 `CODE_SIMPLE`
**Intent:** Isolated, single-file programming tasks. Includes canvas/SVG/procedural-art/animation
requests per the paper's explicit override.
**Triggers:** "write a python function", "fix this regex", "create an HTML button", "bash
script to move files", "canvas animation".
**Anchor:** "Make a canvas animation of a bouncing ball." → `{"route": "CODE_SIMPLE", "keywords": null, "confidence": 0.95}`

### 4.6 `CODE_COMPLEX`
**Intent:** Multi-file projects, full web/desktop apps, large refactors, pasted tracebacks from
substantial codebases.
**Triggers:** "build an app", "create a website", "full project", "entire project", large
traceback paste.
**Anchor:** "Build a complete full-stack app with React and Node." → `{"route": "CODE_COMPLEX", "keywords": null, "confidence": 0.97}`
**Disambiguation rule:** "write a script to delete files" → `CODE_COMPLEX`/`CODE_SIMPLE`
(they're asking for code). "Delete the files in my downloads folder" → `CONTROL` (they're
asking the system to *act*). The distinguishing test is asked-for-code vs. asked-for-action,
not the presence of the word "delete."

### 4.7 `CONTROL`
**Intent:** Direct manipulation of the host OS, hardware, or local apps.
**Triggers:** "open Spotify", "set brightness", "check battery", "send a WhatsApp message",
"empty trash", "restart".
**Anchor:** "Open my system settings and toggle Wi-Fi off." → `{"route": "CONTROL", "keywords": null, "confidence": 0.96}`
**Important — this is a power-granting route, not just a content category.** Per Section 3 of
the paper, `CONTROL` queries still pass through `iris_002`'s own sandbox validation and
error-ceiling checks (Section 8.1) before any host-level execution happens. The triage router
routing a query here is not authorization to execute — it's only a classification. The router
must never be tricked into treating "this looks like a CONTROL-shaped request" as equivalent
to "this action is approved." That approval step lives downstream and is out of scope for
this spec.

### 4.8 `VISION`
**Intent:** Any query referencing an attached/uploaded image, requiring visual question
answering.
**Triggers:** presence of an image attachment + a question about its contents.
**Anchor:** [image attached] "What's in this picture?" → `{"route": "VISION", "keywords": null, "confidence": 0.98}`

---

## 5. Anti-Hallucination Design Notes

The goal stated for this spec was a router that's "100% stable" and doesn't hallucinate.
Two honest caveats worth stating plainly:

1. **No classifier is literally 100% stable.** What actually moves the needle is (a) a small,
   fixed enum the model is constrained to (via grammar-constrained decoding, not just
   instructions), (b) a deterministic pre-filter that resolves the easy majority of cases
   before the neural pass ever runs, and (c) a safe default (`REASONING`) for the residual
   ambiguous cases — rather than guessing at a high-stakes route like `CONTROL` or
   `CODE_COMPLEX`. That combination is what the paper's Section 3 actually describes, and
   it's what this spec implements.
2. **Instructing a model to "never refuse" does not improve routing accuracy** — it just
   removes a safety check the downstream specialist role would otherwise apply. That
   instruction has been deliberately left out of this spec. If you want the router itself to
   be robust against adversarial inputs (e.g., a document or webpage containing embedded
   instructions trying to manipulate the route or impersonate a system message), the
   strongest mitigation is the constrained-decoding enum in Section 1 — an attacker can say
   anything they want, but the output token space literally only contains eight valid routes.

---

## 6. Worked Examples Table

| Query | Route | Why |
|---|---|---|
| "What's the weather in Cairo today?" | `SEARCH` | time-sensitive factual lookup |
| "Why did the Roman Empire fall?" | `REASONING` | explanatory, not a live-fact lookup |
| "Write me a haiku about the sea" | `GENERAL` | creative writing |
| "Solve x^2 - 5x + 6 = 0" | `MATH` | symbolic equation |
| "Reverse a string in JS" | `CODE_SIMPLE` | single isolated snippet |
| "Build me a full e-commerce site with cart + auth" | `CODE_COMPLEX` | multi-file, multi-feature |
| "Set my brightness to 50%" | `CONTROL` | host hardware action |
| [image] "Is this mushroom safe to eat?" | `VISION` | image-grounded question |
| "How do I make a pizza?" | `REASONING` | imperative verb, no code/system noun co-occurrence |
| "Delete the files in my Downloads folder" | `CONTROL` | requesting the action, not the code |
| "Write a script that deletes temp files older than 30 days" | `CODE_SIMPLE`/`CODE_COMPLEX` | requesting the code |
