# Research note — P1.M4.T4.S1 (takeover detection + revocation + mutation-time re-checks)

**Task**: complete the takeover half of the IM-v2 adapter (R.5) — "takeover-complete adapter ready for G3"
(P1.M4.T5 consumes it). INPUT contract = P1.M4.T3.S3 PRP (finalize/leave/cancel, Implementing in parallel).

## 1. The landed seams this task builds on (verified live)

- `voice_typing/ime/ime_host.py` (271 ln) — `on_event` ALREADY forwards every event as JSONL:
  `done`, `activate`, `deactivate`, `surrounding_text` (bytes/cursor/anchor/head), `grab_key`
  (key=args[2], state=args[3]), `unavailable`, and `keymap|modifiers|repeat_info|content_type|
  text_change_cause` (args[:4]). **BUT the host NEVER calls `grab_keyboard`** — `self.grab=0`,
  nothing sets it; `_leave` releases it *if held*. So today zero `grab_key` events flow: the grab
  must be ENGAGED for takeover detection to have a feed.
- `voice_typing/ime/wlwire.py` (227 ln) — `grab_keyboard` (new_id) is in the REQUESTS table;
  `zwp_input_method_keyboard_grab_v2.release` too; key event kinds `uuuu` (time, key, state, serial);
  keymap fd is CLOSED immediately (no keymap kept — we match raw keycodes).
- `voice_typing/ime/manager.py` (432 ln) — `ImeProcess.on_event` forwards ALL event dicts (the T4
  feed, docstring says so); `on_delivery_state` fires only unsupported/fault; callbacks run on the
  reader thread, exception-guarded; `request()` never retries.
- `voice_typing/ime/target.py` (262 ln) — `recheck()` is the existing MUTATION-TIME re-check (fresh
  verify pull, never mutates): refuses `ime deactivated` / `user selection present` / `caret moved`
  / `adjacent text changed`; `leave()` (S3) clears the binding → every later mutating call REFUSES
  "not acquired". Host `_leave` releases the grab. So **revocation composes with leave()** — the
  T3.S3 PRP itself says: "takeover revocation composes with leave() (binding cleared) and the
  closed-set; the adapter is COMPLETE — takeover is the remaining half."
- `voice_typing/bulk_controller.py` (858 ln) — `stop(leave=True)` (writer join 5 s, runner
  shutdown(wait=False), late-result discard, `target.leave()` exactly once, never masks the stop
  reason), `_stop_locked(reason)`, `_fire_on_stopped()`, `_process_next` (the mutation-time
  dispatch). No takeover hook exists yet.
- `voice_typing/key_listener.py:50-56` — `_MODIFIER_KEYCODES` frozenset (LEFT/RIGHT CTRL/ALT/…):
  bare modifier presses are NOT user typing (the arm chord's own keys) — the lineage to mirror
  stdlib-pure (key_listener needs evdev; the ime package must stay stdlib-only).

## 2. The R.2/R.5 evidence (im-lab rows O/O2 + d2 map :189 — do not re-derive)

- **Row O (grab-takeover)**: `grab` → keymap event arrives; `xdotool key b` → `grab_key`
  (keycode 48) reaches the adapter **while the field stays untouched** (cseq unchanged).
  ⇒ the grab CONSUMES keys — they do NOT reach the app. Load-bearing consequences:
  (a) the grab may be held ONLY while an acquisition is live; (b) releasing it AT THE TARGET is
  the non-negotiable half of revocation (a daemon-side flag alone would leave the user's keyboard
  swallowed); (c) the one keypress that triggers revocation is itself consumed (inherent, matches
  R.5 "any ordinary physical key … revokes the handle").
- **Row O2 (grab-no-self-trigger)**: `insert` during the grab → field changed, grab_key count
  UNCHANGED. ⇒ IM commits generate ZERO key events — delivery cannot self-trigger HALT (pinned).
- `commit_string`/`delete_surrounding_text` never emit key events (R.2 table) — same fact.
- Surrounding_text + `text_change_cause` both flow (cause: input_method=0 / other=1 per the
  vendored XML) — our own commits are distinguishable from user edits by cause AND by the
  accounting rule (cursor == binding.cursor_bytes + inserted_bytes).

## 3. Design decisions (from the contract's LOGIC + evidence)

1. **Host gains an explicit `grab` request** (new REQUEST_CMDS entry; handler sends
   `grab_keyboard` + sets `self.grab`; release stays in `_leave`). Additive — does NOT touch S2's
   acquire or S3's cancel regions (both in flight / just landed). Engage right after acquire
   succeeds; hold for the acquisition's lifetime.
2. **Daemon-side detector = a NEW pure module** `voice_typing/ime/takeover.py` (stdlib-only,
   no Wayland, no evdev — mirrors bulk purity rules): `feed(ev:dict) -> reason|None` policy:
   - `grab_key`: modifier-only keycodes never revoke (mirror `_MODIFIER_KEYCODES` as literal ints);
     non-modifier press → **chord match first**: key==KEY_D(32) AND down-mods ⊇ {ALT,SUPER}
     (covers BOTH §4.10 binds: Ctrl+Alt+Super+D and Alt+Super+D — Super+Alt ⊆ Ctrl+Super+Alt) ⇒
     ignored ("the arming chord is ignored, NOT a blanket grace window" — no 1.5 s timer like
     legacy §4.2quater Rev 3); otherwise → revoke `user key <code>`. Modifier DOWN/UP transitions
     maintain the down-set (never revoke).
   - `surrounding_text`: divergent from the accounting expectation (cursor ≠ expected, or
     anchor ≠ cursor) and not attributable to our own commit (cause cycle = input_method) ⇒
     revoke (`caret moved` / `selection present`). Matching our accounting ⇒ benign.
     **No surrounding_text event at all ⇒ nothing happens** — pointer motion alone is not an
     edit (it generates no IM event); a click that matters surfaces as deactivate or a
     divergent surrounding_text.
   - `deactivate` ⇒ revoke (`deactivated` — focus/tab/pane switch, target death).
   - `unavailable`/child death ⇒ manager already emits unsupported/fault; the wiring treats it
     as revocation (no double-emission).
   - Synthetic events cannot leave modifiers held: we never synthesize key events; modifier-only
     presses never revoke so release-mid-hold is safe (pinned by test).
3. **Revocation action = leave-at-target + halt**: `target.leave()` (releases the grab AT THE
   compositor + clears the binding → later ops REFUSE "not acquired") + controller halt through
   the existing stop machinery with ONE recorded reason. A `TakeoverWatch` helper (in takeover.py)
   binds proc.on_event → detector → callback; unit-testable with fakes; daemon wiring is M6.T2.
4. **Mutation-time re-checks**: two layers, both already half-exist — (a) event-driven revoke (new,
   fast path); (b) `show()/finalize()/cancel()`'s existing `recheck()` fresh-verify stays the
   backstop for ops already past the detector (queued op that lost the field refuses "not
   acquired"/"recheck: …" — S3's contract). No post-takeover mutation can occur: binding cleared
   + writer drained (late-result discard path).

## 4. Tests + gates

- NEW `tests/test_ime_takeover.py` (pure): detector matrix (chord ignored incl. Super+Alt+D lite,
  modifier-only ignored, ordinary key revokes, caret/selection divergence revokes, own-cause
  benign, deactivate revokes, no-event no-op), watch wiring (fake proc + fake target + fake
  controller: exactly-one leave, halt reason recorded, no request after revoke), controller
  halt_for_takeover (queue drained, stop reason, idempotent).
- EVOLVE `tests/test_ime_host.py` (append `grab` handler cases: grab → grab_keyboard sent,
  leave releases, keymap→grab_key forwarding), `tests/test_ime_protocol.py` (vocab + validation),
  `tests/test_bulk_controller.py` (append takeover halt).
- Full re-run (T3.S3's success command): `timeout 180 .venv/bin/python -m pytest
  tests/test_ime_takeover.py tests/test_ime_host.py tests/test_ime_protocol.py
  tests/test_ime_target.py tests/test_ime_wlwire.py tests/test_ime_manager.py
  tests/test_bulk_delivery.py tests/test_bulk_controller.py tests/test_g2_bulk_gate.py -q`
  + `ruff check`/`format`. All pure-python (no compositor) — safe, fast.
- OPTIONAL env-gated lab `tests/ime_takeover_lab.py` (`IME_TAKEOVER_LAB=1`, disposable desktop
  only — mirrors ime_finalize_lab.py / rows O/O2): grab → xdotool key → revoked + grab released
  (subsequent keys reach the field again) + chord ignored + commit no-self-trigger.

## 5. Parallel-conflict discipline (T3.S3 is Implementing NOW)

Shared files: `protocol.py` (S3 lifts the cancel reservation; S1 adds `grab` to REQUEST_CMDS —
different lines), `ime_host.py` (S3 adds `_cancel`; S1 adds `_grab` — different dispatch arms),
`tests/test_ime_host.py` (S3 replaces `test_cancel_reserved` + appends; S1 APPENDS grab cases —
no overlap). `target.py`: S1 does NOT touch it (revocation composes with S3's leave() — zero
edit needed) — the safest split. All appends, no shared hunks.

## 6. Keycodes (stdlib-pure constants; mirror key_listener/_MODIFIER_KEYCODES + Linux input.h)

KEY_D=32; LCTRL=29 RCTRL=97 LALT=56 RALT=100 LSHIFT=42 RSHIFT=54 CAPSLOCK=58 NUMLOCK=69
SCROLLLOCK=70 LSUPER/META=125 RSUPER=126. (Lab saw keycode 48 = KEY_B — row O's probe key.)
