# Prefetch results — voice-typing STT models

**Recorded:** 2026-07-06  •  **Run as:** `.venv/bin/python -m voice_typing.prefetch`
**Cache root:** `~/.cache/huggingface/hub` (default; faster-whisper reads this)

## Per-repo result

| short name | repo_id | snapshot path | model.bin size | status |
|---|---|---|---|---|
| distil-large-v3 | Systran/faster-distil-whisper-large-v3 | `/home/dustin/.cache/huggingface/hub/models--Systran--faster-distil-whisper-large-v3/snapshots/c3058b475261292e64a0412df1d2681c06260fab` | 1512927867 bytes (1.4 GiB) | ok |
| small.en | Systran/faster-whisper-small.en | `/home/dustin/.cache/huggingface/hub/models--Systran--faster-whisper-small.en/snapshots/d1d751a5f8271d482d14ca55d9e2deeebbae577f` | 483545366 bytes (461.1 MiB) | ok |
| tiny.en | Systran/faster-whisper-tiny.en | `/home/dustin/.cache/huggingface/hub/models--Systran--faster-whisper-tiny.en/snapshots/0d3d19a32d3338f10357c0889762bd8d64bbdeba` | 75537502 bytes (72.0 MiB) | ok |
| large-v3-turbo | mobiuslabsgmbh/faster-whisper-large-v3-turbo | `/home/dustin/.cache/huggingface/hub/models--mobiuslabsgmbh--faster-whisper-large-v3-turbo/snapshots/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf` | 1617884929 bytes (1.5 GiB) | ok |

## Summary (from the run)

```
=== summary ===
core ok:    ['distil-large-v3', 'small.en', 'tiny.en']
core FAIL:  (none)
opt  ok:    ['large-v3-turbo']
opt  warn:  (none)
total model.bin bytes cached: 3.4 GiB
exit=0
```

## Full run output

```
voice-typing model prefetch
cache: ~/.cache/huggingface/hub (default — faster-whisper reads it)

=== [distil-large-v3] Systran/faster-distil-whisper-large-v3 ===
Fetching 7 files:   0%|          | 0/7 [00:00<?, ?it/s]Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
Fetching 7 files:  14%|█▍        | 1/7 [00:00<00:04,  1.48it/s]Fetching 7 files:  57%|█████▋    | 4/7 [01:35<01:17, 25.82s/it]Fetching 7 files: 100%|██████████| 7/7 [01:35<00:00, 13.68s/it]
    -> /home/dustin/.cache/huggingface/hub/models--Systran--faster-distil-whisper-large-v3/snapshots/c3058b475261292e64a0412df1d2681c06260fab
    model.bin: 1.4 GiB

=== [small.en] Systran/faster-whisper-small.en ===
Fetching 6 files:   0%|          | 0/6 [00:00<?, ?it/s]Fetching 6 files:  17%|█▋        | 1/6 [00:00<00:02,  2.42it/s]Fetching 6 files:  33%|███▎      | 2/6 [00:01<00:02,  1.51it/s]Fetching 6 files:  67%|██████▋   | 4/6 [00:39<00:24, 12.30s/it]Fetching 6 files: 100%|██████████| 6/6 [00:39<00:00,  6.62s/it]
    -> /home/dustin/.cache/huggingface/hub/models--Systran--faster-whisper-small.en/snapshots/d1d751a5f8271d482d14ca55d9e2deeebbae577f
    model.bin: 461.1 MiB

=== [tiny.en] Systran/faster-whisper-tiny.en ===
Fetching 6 files:   0%|          | 0/6 [00:00<?, ?it/s]Fetching 6 files:  17%|█▋        | 1/6 [00:00<00:03,  1.52it/s]Fetching 6 files:  67%|██████▋   | 4/6 [00:08<00:04,  2.25s/it]Fetching 6 files: 100%|██████████| 6/6 [00:08<00:00,  1.42s/it]
    -> /home/dustin/.cache/huggingface/hub/models--Systran--faster-whisper-tiny.en/snapshots/0d3d19a32d3338f10357c0889762bd8d64bbdeba
    model.bin: 72.0 MiB

=== [large-v3-turbo] mobiuslabsgmbh/faster-whisper-large-v3-turbo ===
Fetching 7 files:   0%|          | 0/7 [00:00<?, ?it/s]Fetching 7 files:  14%|█▍        | 1/7 [00:00<00:03,  1.78it/s]Fetching 7 files:  29%|██▊       | 2/7 [00:00<00:02,  2.16it/s]Fetching 7 files:  57%|█████▋    | 4/7 [03:00<02:49, 56.36s/it]Fetching 7 files: 100%|██████████| 7/7 [03:00<00:00, 25.74s/it]
    -> /home/dustin/.cache/huggingface/hub/models--mobiuslabsgmbh--faster-whisper-large-v3-turbo/snapshots/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf
    model.bin: 1.5 GiB

=== summary ===
core ok:    ['distil-large-v3', 'small.en', 'tiny.en']
core FAIL:  (none)
opt  ok:    ['large-v3-turbo']
opt  warn:  (none)
total model.bin bytes cached: 3.4 GiB
exit=0
```

Note: the unauthenticated-download warning is informational only (public, ungated repos — no `HF_TOKEN` needed, per research §5). The full download took ~6 minutes on this host.

## Meaning for the daemon (P1.M4.T1.S1)

- All CORE repos cached → `AudioToTextRecorder(model=final_model, realtime_model_type=realtime_model)` construction is instant (no download). cuda_check.py's CUDA path (distil-large-v3 + small.en) and CPU-fallback path (small.en + tiny.en) are both satisfied.
- turbo ok: the approved substitute is also local — if distil-large-v3 ever runs poorly, the daemon can switch to large-v3-turbo with no network.

## Idempotency check

- A re-run of `.venv/bin/python -m voice_typing.prefetch` completes in seconds (measured: 7s; etags match, no re-download) — safe for install.sh (P1.M6.T1.S1) to re-invoke.
