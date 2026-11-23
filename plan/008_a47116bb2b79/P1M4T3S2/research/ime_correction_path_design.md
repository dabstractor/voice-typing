# Research — P1.M4.T3.S2: the correction path (one atomic range replacement) in `ImeTarget.show()`

**Task shape:** S1 (insert path, in flight) lands `show()` with the branch
`if not span.startswith(self._last_applied_span): REFUSED "correction not implemented (P1.M4.T3.S2)"`.
**THIS task replaces that refusal with the real correction** — and per the item contract the
deliverable is the **full `show()`** (insert branch preserved verbatim in behavior + correction
branch added). The HOST half is already landed: `ime_host.py:_show` (:172-200) sends
`delete_surrounding_text(before, 0)` + `commit_string(text)` + `commit(dones)` in ONE commit cycle
whenever `before>0`.

---

## §1. The landed surfaces this task consumes (anchors, verified live)

| Surface | Anchor | What it provides |
|---|---|---|
| Host `_show` replace half | `ime_host.py:172-200` | `before>0` ⇒ ONE atomic commit: delete_surrounding_text(before,0) → commit_string(text) → commit(dones). applied = compositor `done` (dones increment) within `SHOW_CONFIRM_WAIT`; wire-send Exception ⇒ `unknown` (never retry); not-activated ⇒ `refused`. |
| `SHOW_CONFIRM_WAIT` | `ime_host.py:38` | Currently `0.5`; **S1's Task 3 lowers it to 0.22** (receiver-side verdict must precede the caller's 250 ms give-up). This task only RECORDS it — S1 owns the edit. |
| `FieldBinding` | `target.py:48-59` | `im_handle, cursor_bytes, anchor_bytes, pre_caret, revision` (frozen dataclass; the AcquireResult.handle). |
| `recheck(binding, inserted_bytes)` | `target.py:101-125` | ONE fresh verify pull; refuses on: no reply / deactivated / no surrounding text / selection present / **caret != binding.cursor_bytes + inserted_bytes** / pre-caret region no longer startswith `pre_caret` (adjacent user text touched). Returns `(ok, reason, rev)`. **Signature is T2.S1's, test-pinned — do NOT change.** |
| `to_bytes_span` / `binding_caret_after` | `target.py:127-133` | units plumbing (UTF-8 bytes). |
| S1's show() state + constants | (S1 PRP, in flight) | `_binding/_last_applied_span/_inserted_bytes/last_reason`; `_SHOW_TIMEOUT_S=0.25`, `_COMMIT_CAP_BYTES=4000`; state advances ONLY on APPLIED; ALL SHOW_FIELDS + `before` on every request. |
| `ShowResult`/`rendered_equal` | `bulk_delivery.py:77-89, 220+` | APPLIED/UNCHANGED/REFUSED/UNKNOWN; render-equal = spacing-only comparison (consume, never reimplement). |
| `protocol.SHOW_FIELDS` | `protocol.py:40, 79-93` | session/utterance/seq/expected_revision/text REQUIRED on every show; `before` rides free. |
| Controller (caller, read-only) | `bulk_controller.py:289-297, 408, 443, 617, 688` | `_expected_revision` seeded from AcquireResult.revision at acquire; **+1 ONLY on applied** (:443); refused/unknown stop delivery. The adapter must NEVER advance state on a non-applied result. |
| Test fake | `tests/test_ime_target.py:21-53` | `_FakeProc` records `(cmd, timeout, fields)`, scripted replies (None = dead); `_verify(text, cursor, anchor, ...)` reply helper; `_acquired()` fixture helper. |

## §2. Protocol/evidence facts (do not re-derive — PRD §4.2sexies R.2)

- **delete_surrounding_text units = UTF-8 BYTES** (vendored input-method-unstable-v2 XML: uint byte
  positions; `target.py` docstring pins `units = TargetUnits.UTF8_BYTES`). `before` counts bytes
  backward from the CURRENT CURSOR; `after=0`.
- **Commit evaluation order is preedit-replace → delete-surrounding → insert-commit** within ONE
  commit(serial) — the delete+insert is atomic to the field.
- **Proven byte-exact on a 1024-byte span** (im-lab, GTK4 Gtk.Entry): ONE atomic commit corrects a
  whole 1024 B span exactly; GTK decomposes it internally into 1–2 `changed` signals within one
  commit cycle — EXPECTED, not a defect; frame-level single-edit verification is **G3's** concern
  (P1.M4.T5.S1), NOT this task's.
- **Correction reach is bounded by OWNERSHIP, never size** (user decision 2026-11-19): any OWNED
  dictation text may be replaced provided it is imperceptible. The owned range is exactly
  `_last_applied_span` (everything this acquisition committed at the caret).
- **26–40 ms cmd→field; IM commits generate ZERO key events** (delivery cannot self-trigger the T4
  takeover listener).
- **foot/kitty silently ignore `delete_surrounding_text`** (insert-only over IM) — a correction sent
  to such a field yields no `done`?? NO — the compositor still cycles `done` (commit protocol);
  the field merely doesn't apply the delete. That mismatch is invisible to the host's
  dones-increment confirmation ⇒ **G3's per-field-class matrix owns detecting it** (field-class rows
  report insert-only). This adapter's defense is the acquire-time `surrounding_text` support +
  G3. Recorded as residual risk (§5).

## §3. The pinned correction algorithm (this task's design)

```python
# Inside show(), AFTER the not-acquired and zero-diff guards:
owned = self._last_applied_span                      # everything we own at the caret
owned_bytes = len(owned.encode("utf-8"))             # UTF-8 bytes (astral char = 4)
if span.startswith(owned):     # INSERT path — S1's branch, unchanged behavior
    delta = span[len(owned):]
    ... recheck(binding, inserted_bytes=self._inserted_bytes) ...
    ... cap on len(delta.encode()) ... request(text=delta, before=0)
    ... on APPLIED: _last_applied_span = span; _inserted_bytes += delta_bytes
else:                           # CORRECTION path — THIS TASK: one atomic range replacement
    ok, reason, _rev = self.recheck(binding, inserted_bytes=owned_bytes)   # caret at END of owned text
    if not ok: REFUSED f"recheck: {reason}"                                # NO request
    if not self._owned_region_intact(binding, owned): REFUSED "owned region diverged"   # NO request
    if len(span.encode("utf-8")) > _COMMIT_CAP_BYTES:
        REFUSED f"unchunkable correction {span_bytes}B > {_COMMIT_CAP_BYTES}B cap"     # NO request
    r = request("show", timeout=_SHOW_TIMEOUT_S, <ALL SHOW_FIELDS>, text=span, before=owned_bytes)
    # on APPLIED: _last_applied_span = span; _inserted_bytes = len(span.encode())   # SET, not +=
```

**Why these guards, in this order:**

1. **`recheck(binding, inserted_bytes=owned_bytes)`** — the delete counts BACKWARD from the caret,
   so the caret must sit exactly at `binding.cursor_bytes + owned_bytes` (end of our range) or the
   delete would eat user text. recheck also proves activation, no selection, and that user text
   BEFORE our point is intact (`pre_caret` prefix check).
2. **`_owned_region_intact(binding, owned)`** (NEW private helper, ~8 lines) — ONE extra verify
   pull; asserts the fresh snapshot's byte slice `[cursor_bytes, cursor_bytes+owned_bytes)` equals
   `owned.encode()`. This makes "verified-owned-range replacement" LITERAL: we delete a range whose
   CURRENT content we have re-read and confirmed is ours. Refuses on snapshot missing/truncated
   past the range end. recheck's signature stays untouched (T2.S1 fence) — the second pull is
   correction-only (inserts pay nothing).
3. **Cap on the FULL corrected span** (> 4000 B ⇒ REFUSED "unchunkable") — a correction can never
   be chunked (N chunks = N visible edits = event-count-law violation); the item's contract says
   refuse with a reason. The delete side carries only a count — no wire cost.
4. **`_inserted_bytes = span_bytes` (SET) on an applied correction** — the field must always equal
   "UTF-8 bytes of the currently-owned span" (recheck's caret arithmetic depends on it). For
   extensions `+= delta` ≡ `= span_bytes`, so this stays consistent with S1's insert branch.
5. **Extension fast-path preserved** — pure extensions keep S1's `before=0` + delta-only commit
   (cheaper, no delete, no second verify pull). Corrections (any non-extension span: rewrite,
   shrink, prefix change) take the full-replacement path. Reach is bounded by ownership — the whole
   owned range is replaced in ONE commit regardless of how much differs.
6. **State advances ONLY on APPLIED** — same rule as S1; the controller +1s expected_revision only
   on applied, so a stale advance desyncs it (double-delivery class).
7. **expected_revision guard** — pass-through (SHOW_FIELDS) + a local regression guard:
   `expected_revision < binding.revision` ⇒ REFUSED "revision regression" (the controller seeds
   from the acquire revision and only +1s — anything lower is a desynced/stale caller). Compatible
   with S1's tests (they pass acquire-revision-or-higher).

**Residual risks (documented, NOT this task's to fix):**
- Same-length in-region edits between our verify and the commit: closed by T4's physical-keypress
  takeover + the one-writer rule; the `_owned_region_intact` pull narrows the window to ~ms.
- insert-only field classes (foot/kitty) applying commit_string but dropping the delete: G3's
  matrix rows (P1.M4.T5) own detection/reporting; the adapter cannot see it (compositor still
  acks with a done).
- Frame-level single-edit visibility: G3 (P1.M4.T5.S1).

## §4. Test matrix (appended to tests/test_ime_target.py; reuse _FakeProc/_verify/_acquired)

not-acquired → REFUSED "not acquired" no request · zero-diff exact → UNCHANGED · render-equal
spacing-only → UNCHANGED · revision regression → REFUSED no request · **extension regression
(S1)**: request text=delta before=0 · **prefix-divergent correction**: ONE request
before=owned_bytes text=FULL span → applied → state=span, _inserted_bytes=len(span.encode()) ·
**shrink correction** (span shorter than owned) · **correction-after-correction** (before =
bytes of the first corrected span) · **UTF-8**: owned with an astral char (😀 = 4 B) → before
counts 4 B · recheck caret-moved on correction → REFUSED "recheck: caret moved" NO show request ·
**owned region diverged** (verify text where our range differs) → REFUSED NO request ·
unchunkable (4001-B differing span) → REFUSED cap NO request · reply None/unknown/refused →
UNKNOWN/UNKNOWN/REFUSED with state NOT advanced · after a refused correction, a retry recomputes
before vs the last APPLIED span (state-not-advanced pin) · correction path sends exactly ONE show
request + the verify pulls (call-count pin).

## §5. Scope fences

IN: `voice_typing/ime/target.py` (the full `show()` + `_owned_region_intact` + the revision-regression
guard); `tests/test_ime_target.py` (APPEND); optional `tests/ime_correction_lab.py` (env-gated).
OUT (fenced): `ime_host.py` (S1 owns SHOW_CONFIRM_WAIT; `_show` untouched), `protocol.py`,
`wlwire.py`, `manager.py`, `bulk_delivery.py`, `bulk_controller.py` (read-only), T3.S3
finalize/leave/cancel, T4 takeover, daemon/feedback/ctl/config, tools/im-lab.
