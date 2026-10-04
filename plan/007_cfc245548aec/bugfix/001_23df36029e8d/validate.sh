#!/usr/bin/env bash
# validate.sh — comprehensive project validation for voice-typing (Rev 2 + bugfix delta)
#
# Phases (only those that exist in this codebase):
#   1. Lint        — ruff check (the repo's linter; .ruff_cache/ present, no other lint config)
#   2. Type check  — N/A (no mypy/pyright config exists — reported, not failed)
#   3. Format      — N/A (no formatter adopted: no [tool.ruff] format config; ruff check IS the gate)
#   4. Unit tests  — the fast CUDA-free pytest set (AGENTS.md: test_feed_audio/test_daemon/
#                    test_recorder_host load real CUDA models and are excluded from the fast gate)
#   5. E2E probes  — daemon-level user-journey simulation driving the REAL daemon + REAL
#                    StreamingOutput engine with the PRODUCTION event ordering (every child
#                    partial is dispatched by the host reader as ('partial') THEN ('speech') —
#                    see daemon._build_callbacks._partial / recorder_host._child_on_speech),
#                    plus a live ControlServer over a real AF_UNIX socket, the config contract,
#                    and voicectl client exit codes.
#
# SAFETY (AGENTS.md): every non-trivial command runs under an inner GNU `timeout` with a
# generous outer harness timeout. No daemon is ever run in the foreground; the ControlServer
# probes bind a socket inside a bounded mktemp dir and tear it down via an EXIT trap. No
# CUDA model is ever loaded (unit-style doubles only). No scratch file exceeds a few KB.
#
# Output: per-phase PASS/FAIL + a final verdict line "VALIDATION: PASS|FAIL (N issue probes)".

set -u
cd "$(dirname "$0")"

PY=.venv/bin/python
PYTEST=.venv/bin/pytest
RUFF=""
for cand in .venv/bin/ruff /home/dustin/.local/bin/ruff ruff; do
    if command -v "$cand" >/dev/null 2>&1; then RUFF="$cand"; break; fi
done

PASS_COUNT=0
FAIL_COUNT=0
phase() { printf '\n=== %s ===\n' "$1"; }
note_fail() { FAIL_COUNT=$((FAIL_COUNT+1)); printf 'FAIL: %s\n' "$1"; }
note_pass() { PASS_COUNT=$((PASS_COUNT+1)); printf 'PASS: %s\n' "$1"; }

# ---------------------------------------------------------------- Phase 1: lint
phase "Phase 1: Lint (ruff check)"
if [ -n "$RUFF" ]; then
    if timeout 120 "$RUFF" check voice_typing tests >/tmp/voice-typing-validate-ruff.log 2>&1; then
        note_pass "ruff check clean"
    else
        note_fail "ruff check reported issues:"
        tail -20 /tmp/voice-typing-validate-ruff.log
    fi
    rm -f /tmp/voice-typing-validate-ruff.log
else
    printf 'SKIP: ruff not found\n'
fi

# ---------------------------------------------------- Phase 2/3: type / format
phase "Phase 2: Type checking"
printf 'N/A: no mypy/pyright configuration exists in this repo (skipped by design)\n'

phase "Phase 3: Style/format checking"
printf 'N/A: no formatter gate configured (no [tool.ruff]/ruff.toml; ruff check is the lint gate)\n'

# ------------------------------------------------------- Phase 4: unit tests
phase "Phase 4: Unit tests (fast CUDA-free set)"
FAST_TESTS="tests/test_config.py tests/test_context_prompt_refresh.py tests/test_control_socket.py \
tests/test_cuda_check.py tests/test_feedback.py tests/test_key_listener.py tests/test_prompt_engine.py \
tests/test_streaming.py tests/test_streaming_core.py tests/test_streaming_commit.py \
tests/test_streaming_freeze.py tests/test_systemd_unit.py tests/test_textproc.py \
tests/test_typing_backends.py tests/test_voicectl.py"
if timeout 600 "$PYTEST" $FAST_TESTS -q >/tmp/voice-typing-validate-pytest.log 2>&1; then :; fi
if grep -qE "^([0-9]+ passed|.*[0-9]+ passed)" /tmp/voice-typing-validate-pytest.log \
   && ! grep -qE "[0-9]+ failed|ERROR" /tmp/voice-typing-validate-pytest.log; then
    note_pass "fast unit suite: $(grep -oE '[0-9]+ passed.*' /tmp/voice-typing-validate-pytest.log | head -1)"
else
    note_fail "fast unit suite reported failures:"
    tail -25 /tmp/voice-typing-validate-pytest.log
fi
rm -f /tmp/voice-typing-validate-pytest.log

# --------------------------------------------------------- Phase 5: E2E probes
phase "Phase 5: E2E user-journey probes (daemon + engine + control socket + CLI)"

SCRATCH="$(mktemp -d /tmp/voice-typing-validate.XXXXXX)"
trap 'rm -rf "$SCRATCH"' EXIT INT TERM

timeout 300 "$PY" - "$SCRATCH" <<'PYEOF'
import json
import os
import socket
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.getcwd())
SCRATCH = sys.argv[1]

from voice_typing import daemon as daemon_mod
from voice_typing import streaming, textproc
from voice_typing.config import VoiceTypingConfig

results = []


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS: " if ok else "FAIL: ") + name + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------- doubles ----

class FB:
    def __init__(self):
        self.partials, self.finals, self.notifies, self.phases = [], [], [], []

    def update_partial(self, t): self.partials.append(t)
    def record_final(self, t): self.finals.append(t)
    def notify(self, m): self.notifies.append(m)
    def set_listening(self, b): pass
    def set_phase(self, p): self.phases.append(p)
    def set_mode(self, m): pass
    def set_models_loaded(self, b): pass
    def snapshot(self): return {}


class BE:
    def __init__(self):
        self.calls = []

    def type_text(self, t): self.calls.append(("type", t))
    def press_backspace(self, n): self.calls.append(("bs", n))


class Host:
    """Host-shaped double: text() blocks like the real child; cancel() mimics the
    audio-discarding cancel that makes the child emit the MARKED sentinel final."""

    def __init__(self):
        self.mic = []
        self.cancel_called = False
        self.aborts = 0
        self.text_cb = None

    @property
    def is_alive(self): return True
    @property
    def pid(self): return 4242
    @property
    def device(self): return {"device": "cpu", "compute_type": "int8", "model": "tiny.en"}
    def spawn(self, timeout=180.0): return True
    def set_microphone(self, on): self.mic.append(on)
    def abort(self): self.aborts += 1
    def stop(self): pass
    def set_prompt(self, t): pass
    def text(self, on_final):
        self.text_cb = on_final
        # block "forever" like the real child; tests never rely on return
        time.sleep(30)
        return ""
    def cancel(self):
        self.cancel_called = True
        # the real child unblocks text() and relays the MARKED sentinel final:
        cb = self.text_cb
        if cb is not None:
            self.text_cb = None
            threading.Thread(target=cb, args=("",), daemon=True).start()
    def consume_cancel_mark(self):
        was = self.cancel_called
        self.cancel_called = False
        return was


def make_daemon(cfg=None, backend=None, host=None):
    cfg = cfg or VoiceTypingConfig()
    fb = FB()
    be = backend or BE()
    h = host or Host()
    d = daemon_mod.VoiceTypingDaemon(
        cfg, fb, recorder_host=h, backend=be,
        mic_prober=lambda: (True, None),
    )
    return d, fb, be, h


def feed_partial(d, text):
    """One child stabilized partial, dispatched EXACTLY as the host reader does:
    ('partial', text) THEN the paired ('speech', {}) — see _build_callbacks._partial."""
    d._on_partial(text)
    d._touch_speech()


def typed_text(be):
    return "".join(c[1] for c in be.calls if c[0] == "type")


def wait_until(pred, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


# ============================================================================
# Journey 1 — PRD acceptance #1/#11 (BUG-001 fix): a blocklist-rejected final
# must NOT silence the rest of the armed session; the next utterance types.
# ============================================================================
d, fb, be, host = make_daemon()
d.start()
feed_partial(d, "Hello world")
d.on_final("Hello world")            # commits + types
typed_before = typed_text(be)
d.on_final("Thank you.")             # blocklist hallucination -> rejected final
froze = d._stream.frozen
feed_partial(d, "The next real sentence")   # next utterance (partial+speech pair)
feed_partial(d, "The next real sentence rocks")
d.on_final("The next real sentence rocks")
ok = ("next real sentence" in typed_text(be)) and len(typed_text(be)) > len(typed_before)
record("BUG-001 regression: rejected final does not kill the session (next utterance types)", ok,
       f"frozen_after_reject={froze}, typed={typed_text(be)!r}")
record("BUG-001 regression: user cue emitted on rejected final",
       any("filtered hallucination" in n for n in fb.notifies), f"notifies={fb.notifies!r}")

# ============================================================================
# Journey 2 — PRD Backspace-cancel (BUG-002 fix): after cancel, the re-said
# sentence streams live (partials type before the commit).
# ============================================================================
d, fb, be, host = make_daemon()
d.start()
feed_partial(d, "the quick brown")
n_before_cancel = sum(1 for c in be.calls if c[0] == "type")
d.cancel()
typed_at_cancel = typed_text(be)
# re-said sentence: three partial+speech pairs, NO commit yet
feed_partial(d, "the quick brown fox")
feed_partial(d, "the quick brown fox jumps")
feed_partial(d, "the quick brown fox jumps over")
live_typed = sum(1 for c in be.calls if c[0] == "type") > n_before_cancel
record("BUG-002 regression: re-said sentence types live after cancel", live_typed,
       f"typed_after_cancel={typed_text(be)[len(typed_at_cancel):]!r}")
# ...and the cancelled fragment was actually rewound (compensation backspace)
bs = [c for c in be.calls if c[0] == "bs"]
record("BUG-002 regression: cancel rewinds the pending tail", len(bs) >= 1, f"bs_calls={bs!r}")

# ============================================================================
# Journey 3 — BUG-003 fix: user-keypress frozen commit keeps the separator.
# ============================================================================
eng = streaming.StreamingOutput(BE(), FB(), True, append_space=True)
eb, ef = eng._backend, eng._feedback
eng.on_partial("Hello world"); eng.commit("Hello world"); eng.reset_boundary()
eng.on_partial("the quick")
eng.note_user_keypress()             # non-Backspace keypress over a pending tail
eng.commit("the quick")              # frozen absorb + trailing space
eng.reset_boundary()                 # lifts the per-utterance freeze
eng.on_partial("New sentence")
screen = "".join(c[1] for c in eb.calls if c[0] == "type")
ok = "quick new sentence" in screen and "quicknew" not in screen
record("BUG-003 regression: frozen commit appends the separator (no glued words)", ok,
       f"screen={screen!r}")

# ============================================================================
# Journey 4 — PRD acceptance #4 (BUG-004 fix): nothing typed while toggled off.
# ============================================================================
d, fb, be, host = make_daemon()
d.start()
feed_partial(d, "hello there")
n_typed_while_listening = len(be.calls)
d.stop()
assert not d.is_listening()
d._on_partial("stray words")         # stale partial lands after the disarm
d.on_final("stray final")            # stale final lands after the disarm
ok = len(be.calls) == n_typed_while_listening
record("BUG-004 regression: stale partial AND final after stop type nothing", ok,
       f"calls_during_disarm={be.calls[n_typed_while_listening:]!r}")

# ============================================================================
# Journey 5 — BUG-007 fix: stop right after a cancel must not drain ~5s.
# (Run the real run() loop in a thread so _text_in_flight/text() wiring is live.)
# ============================================================================
d, fb, be, host = make_daemon()
loop = threading.Thread(target=d.run, daemon=True)
loop.start()
d.start()
wait_until(lambda: host.text_cb is not None, 2.0)   # run loop entered text()
feed_partial(d, "scratch this")
d.cancel()
ok = wait_until(lambda: not d._cancel_suppress_final and not d._final_pending, 2.0)
pending = d._final_pending
record("BUG-007 regression: cancelled sentinel clears _final_pending (stop is immediate)",
       ok and not pending, f"suppressed={d._cancel_suppress_final}, final_pending={pending}")
d._shutdown.set()
host.aborts += 0  # loop thread unwinds via _shutdown between text() sleeps (daemon thread anyway)

# ============================================================================
# Journey 6 — BUG-008 fix: mid-sentence capitalized partials extend (no churn).
# ============================================================================
eng = streaming.StreamingOutput(BE(), FB(), True)
eb = eng._backend
eng.commit("and then he said")       # committed without terminal punctuation
eng.reset_boundary()
for p in ["Hello there", "Hello there friend", "Hello there friend how"]:
    eng.on_partial(p)
bs_calls = [c for c in eb.calls if c[0] == "bs"]
record("BUG-008 regression: case-guarded tail extends on capitalized partials",
       len(bs_calls) == 0, f"bs_calls={bs_calls!r}, typed={[c[1] for c in eb.calls]!r}")

# ============================================================================
# Journey 7 — NEW PROBE: the user-keypress freeze (PRD rule 5, "never type over
# the user's cursor") vs the paired speech event that EVERY partial fires.
# ============================================================================
d, fb, be, host = make_daemon()
d.start()
feed_partial(d, "hello wor")         # tail typed
eng_frozen_then = None
d.note_user_keypress()               # user presses a key over the pending tail
frozen_after_keypress = d._stream.frozen
feed_partial(d, "hello world")       # next partial pair (mirror-only, then resume)
still_frozen = d._stream.frozen
feed_partial(d, "hello world again") # ...and the one after
typed_after_keypress = typed_text(be)
# The freeze is supposed to hold until this utterance's commit; if the paired
# speech event already lifted it, the engine types over the user's edit.
ok = still_frozen or ("again" not in typed_after_keypress)
record("NEW: user-keypress freeze survives subsequent partials (PRD rule 5)", ok,
       f"frozen_after_keypress={frozen_after_keypress}, frozen_after_next_partial={still_frozen}, "
       f"typed={typed_after_keypress!r}")

# ============================================================================
# Journey 8 — NEW PROBE: stray partials after a rejected final lift the
# session freeze the daemon claims survives "until genuinely-new speech".
# ============================================================================
d, fb, be, host = make_daemon()
d.start()
feed_partial(d, "real words")
d.on_final("Real words")
d.on_final("Thank you.")             # rejected -> session freeze + boundary
frozen_after_reject = d._stream.frozen
feed_partial(d, "thank you")         # stray partial pair of the hallucination
feed_partial(d, "thank you")         # ...and one more
typed_after_strays = typed_text(be)
ok = "thank you" not in typed_after_strays
record("NEW: stray hallucination partials after a rejected final stay untyped", ok,
       f"frozen_after_reject={frozen_after_reject}, frozen_after_stray_pair={d._stream.frozen}, "
       f"typed={typed_after_strays!r}")

# ============================================================================
# Journey 9 — config contract (BUG-006 fix + documented fail-fast behavior).
# ============================================================================
ok_table = VoiceTypingConfig.from_toml({"asr": {"language": "en"}, "output": {"streaming": True}})
record("BUG-006 regression: valid config loads", ok_table.asr.language == "en")
try:
    VoiceTypingConfig.from_toml({"outpt": {"backend": "ydotool"}})
    record("BUG-006 regression: unknown top-level table rejected", False, "no exception raised")
except TypeError:
    record("BUG-006 regression: unknown top-level table rejected", True)
try:
    VoiceTypingConfig.from_toml({"output": {"bakend": "ydotool"}})
    record("unknown key inside a known table rejected", False, "no exception raised")
except TypeError:
    record("unknown key inside a known table rejected", True)
record("config.toml in repo root loads", VoiceTypingConfig.from_toml_file("config.toml") is not None)

# ============================================================================
# Journey 10 — live control socket protocol (BUG-005 fix + PRD §4.2(3)).
# ============================================================================
sock_path = os.path.join(SCRATCH, "control.sock")


class StubDaemon:
    def is_listening(self): return False
    def status_snapshot(self):
        return {"ok": True, "listening": False, "phase": "idle", "partial": ""}
    def toggle(self): return self.status_snapshot()
    def start(self): return self.status_snapshot()
    def stop(self): return self.status_snapshot()
    def cancel(self): return {"ok": True, "listening": False}
    def request_shutdown(self): pass


srv = daemon_mod.ControlServer(StubDaemon(), socket_path=sock_path)
srv.start()


def roundtrip(payload, expect_reply=True, timeout_s=5.0):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout_s)
    s.connect(sock_path)
    if payload is not None:
        s.sendall(payload)
    try:
        line = s.makefile("r").readline()
        return line
    finally:
        s.close()


try:
    line = roundtrip(b"\n")
    ok = bool(line.strip())
    record("BUG-005 regression: empty request line gets a reply", ok, f"reply={line!r}")
    line = roundtrip(b"not json at all\n")
    ok = '"ok": false' in line and "malformed JSON" in line
    record("malformed JSON gets an error reply", ok, f"reply={line!r}")
    line = roundtrip(b"[1,2,3]\n")
    record("non-object JSON rejected", '"ok": false' in line, f"reply={line!r}")
    line = roundtrip(json.dumps({"cmd": "bogus"}).encode() + b"\n")
    record("unknown command rejected", "unknown command" in line and '"ok": false' in line,
           f"reply={line!r}")
    line = roundtrip(json.dumps({"cmd": "status"}).encode() + b"\n")
    record("status command works over the wire", '"listening": false' in line, f"reply={line!r}")
finally:
    srv.stop()
    try:
        os.unlink(sock_path)
    except OSError:
        pass

# ============================================================================
# Journey 11 — voicectl client exit codes against a live server (PRD §4.8).
# ============================================================================
env_dir = os.path.join(SCRATCH, "voice-typing")
os.makedirs(env_dir, exist_ok=True)          # voicectl resolves $XDG_RUNTIME_DIR/voice-typing/control.sock
sock2 = os.path.join(env_dir, "control.sock")
srv2 = daemon_mod.ControlServer(StubDaemon(), socket_path=sock2)
srv2.start()
env = dict(os.environ, XDG_RUNTIME_DIR=SCRATCH,
           PYTHONPATH=os.getcwd())
try:
    def ctl(*args):
        p = subprocess.run([sys.executable, "-m", "voice_typing.ctl", *args],
                           capture_output=True, text=True, timeout=20, env=env)
        return p.returncode, (p.stdout + p.stderr).strip()

    code, out = ctl("status")
    record("voicectl status against live daemon exits 0", code == 0, f"code={code} out={out!r}")
    code, out = ctl("frobnicate")
    record("voicectl unknown command exits 64", code == 64, f"code={code} out={out!r}")
    code, out = ctl()
    record("voicectl missing command exits 64", code == 64, f"code={code} out={out!r}")
finally:
    srv2.stop()
    try:
        os.unlink(sock2)
    except OSError:
        pass
# daemon-down path (socket dir exists, no socket): exit 2
env2 = dict(os.environ, XDG_RUNTIME_DIR=SCRATCH, PYTHONPATH=os.getcwd())
p = subprocess.run([sys.executable, "-m", "voice_typing.ctl", "status"],
                   capture_output=True, text=True, timeout=20, env=env2)
record("voicectl status with daemon down exits 2", p.returncode == 2,
       f"code={p.returncode} out={(p.stdout + p.stderr).strip()!r}")

# ============================================================================
# Journey 12 — core dictation loop end-to-end at the daemon seam (README flow).
# ============================================================================
d, fb, be, host = make_daemon()
d.start()
feed_partial(d, "Hello")
feed_partial(d, "Hello world")
d.on_final("Hello world")
d.on_final("Second sentence here")
d.stop()
screen = typed_text(be)
# The mid-sentence casing guard lowercases a fresh fragment after non-terminal
# committed text ("Hello world ") — that is documented product behavior.
ok = screen.lower().startswith("hello world ") and "second sentence here " in screen
record("core journey: arm -> stream -> commit -> second utterance -> stop", ok, f"screen={screen!r}")
record("core journey: session state resets on stop (mirror cleared)",
       d._stream.committed == "" and d._stream.tail == "")

# summary
fails = [r for r in results if not r[1]]
print(f"\nPROBE SUMMARY: {len(results) - len(fails)} passed, {len(fails)} failed")
for name, ok_, detail in fails:
    print(f"  FAILED: {name} — {detail}")
sys.exit(1 if fails else 0)
PYEOF
PROBE_RC=$?

# ------------------------------------------------------------------- verdict
printf '\n'
if [ "$FAIL_COUNT" -eq 0 ] && [ "$PROBE_RC" -eq 0 ]; then
    printf 'VALIDATION: PASS (%d checks, %d probe failures)\n' "$PASS_COUNT" 0
    exit 0
else
    printf 'VALIDATION: FAIL (lint/unit failures: %s, probe exit: %s)\n' "$FAIL_COUNT" "$PROBE_RC"
    exit 1
fi
