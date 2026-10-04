"""P1.M1.T2.S1 — cuda_check single-model contract (Rev 2 §4.2ter/§4.2quater).

cuda_check resolves exactly {device, compute_type, model}: ONE model (the small
model) serves BOTH realtime partials and finals. CUDA path = small.en /
float32 / cuda; the PRD §4.4 CPU fallback = tiny.en / int8 / cpu, applied
REGARDLESS of any caller-supplied defaults. All tests here are HERMETIC: the
probes (is_cuda_available / _cuda_device_count / _torch_cuda_available /
_ctranslate2_version) are monkeypatched — a real ctranslate2/torch import is
never triggered in-process (AGENTS.md: heavy CUDA loads are minutes).

Run: timeout 600 .venv/bin/python -m pytest tests/test_cuda_check.py -q
"""
import subprocess
import sys

from voice_typing import cuda_check


def test_cuda_defaults_is_three_key_single_model():
    assert set(cuda_check.CUDA_DEFAULTS) == {"device", "compute_type", "model"}
    assert cuda_check.CUDA_DEFAULTS == {
        "device": "cuda",
        "compute_type": "float32",
        "model": "small.en",
    }


def test_cpu_fallback_is_three_key_single_model():
    assert set(cuda_check.CPU_FALLBACK) == {"device", "compute_type", "model"}
    assert cuda_check.CPU_FALLBACK == {
        "device": "cpu",
        "compute_type": "int8",
        "model": "tiny.en",
    }


def test_resolve_cuda_returns_fresh_copy_of_defaults(monkeypatch):
    monkeypatch.setattr(cuda_check, "is_cuda_available", lambda: True)
    r = cuda_check.resolve_device_and_models()
    assert r == cuda_check.CUDA_DEFAULTS and r is not cuda_check.CUDA_DEFAULTS
    r["model"] = "mutated"  # caller may mutate freely
    assert cuda_check.CUDA_DEFAULTS["model"] == "small.en"


def test_resolve_cpu_returns_fallback_regardless_of_defaults(monkeypatch):
    monkeypatch.setattr(cuda_check, "is_cuda_available", lambda: False)
    custom = {"device": "cuda", "compute_type": "float32", "model": "base.en"}
    assert cuda_check.resolve_device_and_models(custom) == cuda_check.CPU_FALLBACK
    assert cuda_check.resolve_device_and_models() == cuda_check.CPU_FALLBACK


def test_resolve_custom_defaults_pass_through_on_cuda(monkeypatch):
    monkeypatch.setattr(cuda_check, "is_cuda_available", lambda: True)
    custom = {"device": "cuda", "compute_type": "float32", "model": "base.en"}
    assert cuda_check.resolve_device_and_models(custom) == custom


def test_main_cuda_prints_verdict_and_single_model_line(monkeypatch, capsys):
    monkeypatch.setattr(
        cuda_check, "_cuda_device_count",
        lambda: (1, "1 cuda device(s) visible to ctranslate2"),
    )
    monkeypatch.setattr(cuda_check, "_torch_cuda_available", lambda: True)
    monkeypatch.setattr(cuda_check, "_ctranslate2_version", lambda: "4.x-test")
    rc = cuda_check._main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "ctranslate2_version=4.x-test" in out and "cuda_device_count=1" in out
    assert "VERDICT=cuda-ok" in out
    assert "resolved: device=cuda compute_type=float32 model=small.en" in out
    assert "final_model" not in out and "realtime_model" not in out  # the collapse


def test_main_cpu_verdict_exit_1_and_tiny_en(monkeypatch, capsys):
    monkeypatch.setattr(
        cuda_check, "_cuda_device_count",
        lambda: (0, "no CUDA-capable device/driver visible to ctranslate2"),
    )
    monkeypatch.setattr(cuda_check, "_torch_cuda_available", lambda: False)
    rc = cuda_check._main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "VERDICT=cpu-fallback-required" in out
    assert "resolved: device=cpu compute_type=int8 model=tiny.en" in out


def test_module_import_stays_cuda_free():
    # Hermetic: a fresh interpreter must be able to import the module without
    # ever loading ctranslate2 (the import stays lazy inside _cuda_device_count).
    code = (
        "import sys, voice_typing.cuda_check; "
        "sys.exit(0 if 'ctranslate2' not in sys.modules else 1)"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
