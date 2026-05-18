#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$repo_root" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
mix = (root / "quake/Quake/snd_mix.c").read_text(encoding="utf-8")
quantum = (root / "quake/Quake/snd_quantum.c").read_text(encoding="utf-8")
header = (root / "quake/Quake/snd_quantum.h").read_text(encoding="utf-8")


def require(text, needle, label):
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle}")


for needle in [
    "qboolean S_QuantumPostMixMode(void);",
    "qboolean S_QuantumSourceMode(void);",
    "void S_QuantumSourceBeginFrame(void);",
    "void S_QuantumSourceNote(int entnum, int entchannel, const char *name);",
    "void S_QuantumProcessSource(portable_samplepair_t *sourcebuffer, int count,",
    "void S_QuantumSourceEndFrame(void);",
]:
    require(header, needle, "source-mode header contract")

for needle in [
    "quantum_source_mode = S_QuantumSourceMode();",
    "S_QuantumSourceBeginFrame();",
    "S_QuantumSourceNote(ch->entnum, ch->entchannel, ch->sfx->name);",
    "S_QuantumProcessSource(qge_sourcebuffer, count,",
    "SND_AddSourceBuffer(qge_sourcebuffer, count,",
    "S_QuantumSourceEndFrame();",
    "if (S_QuantumPostMixMode())",
    "\\\"quantum_owner\\\": ",
    "\\\"source_ownership\\\": %s",
]:
    require(mix, needle, "mixer source path")

for needle in [
    "return snd_quantum_enable.value >= 0.5f &&",
    "snd_quantum_enable.value < 1.5f;",
    "return snd_quantum_enable.value >= 1.5f;",
    "audio_source_dry_fallback",
    "audio_source_short_block",
    "audio_source_invalid_block",
    "QGE audio source owner=audio_source",
    "source_count=%d",
    "processed_blocks=%d",
    "processed_samples=%d",
    "skipped_blocks=%d",
    "dry_fallback_blocks=%d",
    "clipping=%d",
    "transducer_ms=%.3f",
    "QGE_MEASURE_AUDIO_BLOCK",
    "QGE_OBSERVE_AUDIO_MIX",
    "\"audio_source\"",
    "\"audio_source_frame\"",
]:
    require(quantum, needle, "source telemetry contract")

print("snd_quantum source ownership contract: PASSED")
PY
