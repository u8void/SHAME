import re
import logging
from dataclasses import dataclass, field
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Marker lines are matched whole-line (after stripping surrounding whitespace) so both
# this project's native "<<<<" / "====" / ">>>>" style AND the more common Aider-style
# "<<<<<<< SEARCH" / "=======" / ">>>>>>> REPLACE" style are accepted. A small model is
# far more likely to default to the labeled Aider style from its own training data than
# to reliably follow an unfamiliar bare-caret convention, so both must work.
_OPEN_RE = re.compile(r'^\s*<{3,}[^\n]*$')
_SEP_RE = re.compile(r'^\s*={3,}[^\n]*$')
_CLOSE_RE = re.compile(r'^\s*>{3,}[^\n]*$')
_FENCE_RE = re.compile(r'^\s*```\w*\s*$')


@dataclass
class PatchBlockResult:
    search_preview: str
    applied: bool
    match_kind: str  # "exact" | "fuzzy" | "failed" | "empty" | "malformed"
    reason: str = ""


@dataclass
class PatchOutcome:
    code: str
    blocks_found: int = 0
    blocks_applied: int = 0
    blocks_failed: int = 0
    results: List[PatchBlockResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.blocks_found > 0 and self.blocks_failed == 0


def _preview(text: str, limit: int = 60) -> str:
    text = " ".join(text.split())
    return (text[:limit] + "…") if len(text) > limit else (text or "(empty)")


def _strip_outer_fence(text: str) -> str:
    """If the model wrapped the ENTIRE patch (all blocks) in one markdown code fence,
    drop just that outer fence. Fences belonging to an individual SEARCH or REPLACE
    side are left alone and handled per-block in _strip_fence_lines."""
    lines = text.splitlines()
    if len(lines) >= 2 and _FENCE_RE.match(lines[0]) and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1])
    return text


def _strip_fence_lines(lines: List[str]) -> List[str]:
    lines = list(lines)
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return lines


def _trim_blank_edges(lines: List[str]) -> List[str]:
    lines = list(lines)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _split_blocks(patch_text: str) -> Tuple[List[Tuple[List[str], List[str]]], int]:
    """
    Parse patch_text into a list of (search_lines, replace_lines) tuples.

    Tolerant of the mistakes a small model actually makes:
      - either marker convention above, with or without a trailing label word
      - a missing closing '>>>' marker (end-of-text is treated as an implicit close,
        since that's exactly what happens when the model just stops generating)
      - multiple blocks back to back in a single response
      - a new block opening before the previous one ever found its '====' separator
        (the broken one is discarded and parsing resumes cleanly from the new marker)

    Returns (blocks, malformed_count) where malformed_count is the number of opened
    blocks that were discarded because no '====' separator was ever found for them.
    """
    lines = patch_text.splitlines()
    blocks: List[Tuple[List[str], List[str]]] = []
    malformed = 0
    i, n = 0, len(lines)

    while i < n:
        if not _OPEN_RE.match(lines[i]):
            i += 1
            continue

        i += 1
        search_lines: List[str] = []
        found_sep = False
        while i < n:
            if _SEP_RE.match(lines[i]):
                found_sep = True
                i += 1
                break
            if _OPEN_RE.match(lines[i]):
                break  # a new block started before this one closed its search side
            search_lines.append(lines[i])
            i += 1

        if not found_sep:
            malformed += 1
            continue  # re-check the current line (may itself be a fresh '<<<' open)

        replace_lines: List[str] = []
        while i < n and not _CLOSE_RE.match(lines[i]) and not _OPEN_RE.match(lines[i]):
            replace_lines.append(lines[i])
            i += 1
        if i < n and _CLOSE_RE.match(lines[i]):
            i += 1

        blocks.append((search_lines, replace_lines))

    return blocks, malformed


def apply_patch(original_code: str, patch_text: str) -> PatchOutcome:
    """
    Applies one or more SEARCH/REPLACE blocks to original_code.

    Each block is matched independently: an exact substring match is tried first,
    falling back to fuzzy whitespace-agnostic line matching. A block that matches
    neither is SKIPPED (left unapplied) rather than aborting the whole patch — one
    bad excerpt shouldn't throw away every other correct edit in the same turn.
    Every outcome (applied or not) is reported back in `results` instead of only
    being logged, so callers can surface failures instead of silently no-op'ing.
    """
    text = _strip_outer_fence(patch_text.strip())
    raw_blocks, malformed = _split_blocks(text)

    code = original_code
    outcome = PatchOutcome(code=code)
    outcome.blocks_found = len(raw_blocks) + malformed

    def _normalize(s: str) -> str:
        return " ".join(s.split())

    for search_lines, replace_lines in raw_blocks:
        s_lines = _trim_blank_edges(search_lines)
        r_lines = _strip_fence_lines(replace_lines)
        search_block = "\n".join(s_lines)
        replace_block = "\n".join(r_lines)
        preview = _preview(search_block)

        if not s_lines:
            outcome.blocks_failed += 1
            outcome.results.append(
                PatchBlockResult(preview, False, "empty", "the SEARCH side was empty")
            )
            continue

        if search_block in code:
            code = code.replace(search_block, replace_block, 1)
            outcome.blocks_applied += 1
            outcome.results.append(PatchBlockResult(preview, True, "exact"))
            continue

        code_lines = code.splitlines()
        norm_search = [_normalize(l) for l in s_lines]
        matched = False
        for i in range(len(code_lines) - len(s_lines) + 1):
            if all(
                _normalize(code_lines[i + j]) == norm_search[j]
                for j in range(len(s_lines))
            ):
                code_lines = code_lines[:i] + r_lines + code_lines[i + len(s_lines):]
                code = "\n".join(code_lines)
                matched = True
                break

        if matched:
            outcome.blocks_applied += 1
            outcome.results.append(PatchBlockResult(preview, True, "fuzzy"))
        else:
            outcome.blocks_failed += 1
            outcome.results.append(
                PatchBlockResult(
                    preview, False, "failed", "couldn't find that text in the file"
                )
            )
            logger.warning(f"[Patcher] SEARCH block did not match anything: {preview!r}")

    if malformed:
        outcome.blocks_failed += malformed
        outcome.results.append(
            PatchBlockResult(
                "(unterminated block)",
                False,
                "malformed",
                "a block was opened but never had a '====' separator",
            )
        )
        logger.warning(f"[Patcher] {malformed} unterminated patch block(s) discarded.")

    if outcome.blocks_found == 0:
        logger.warning("[Patcher] No SEARCH/REPLACE blocks found in patch text.")

    outcome.code = code
    return outcome
