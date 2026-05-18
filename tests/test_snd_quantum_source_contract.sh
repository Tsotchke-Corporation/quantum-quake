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
stream = (root / "tools/quake_graphics_stream.sh").read_text(encoding="utf-8")


def require(text, needle, label):
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle}")


for needle in [
    "typedef struct {",
    "vec3_t source_origin;",
    "vec3_t listener_origin;",
    "vec3_t listener_forward;",
    "vec3_t listener_right;",
    "float distance_attenuation;",
    "float pan_dot;",
    "} snd_quantum_source_spatial_t;",
    "qboolean S_QuantumPostMixMode(void);",
    "qboolean S_QuantumSourceMode(void);",
    "void S_QuantumSourceBeginFrame(void);",
    "const snd_quantum_source_spatial_t *spatial",
    "void S_QuantumSourceNote(int entnum, int entchannel, const char *name,",
    "void S_QuantumProcessSource(portable_samplepair_t *sourcebuffer, int count,",
    "void S_QuantumSourceEndFrame(void);",
]:
    require(header, needle, "source-mode header contract")

for needle in [
    "quantum_source_mode = S_QuantumSourceMode();",
    "S_QuantumSourceBeginFrame();",
    "SND_BuildQuantumSourceSpatial(ch, &qge_spatial);",
    "S_QuantumSourceNote(ch->entnum, ch->entchannel,",
    "ch->sfx->name, &qge_spatial);",
    "S_QuantumProcessSource(qge_sourcebuffer, count,",
    "&qge_spatial);",
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
    "audio_source_remainder_block",
    "audio_source_spatial",
    "qa_source_spatial_hash",
    "qa_record_source_spatial_probe",
    "QGE audio source owner=audio_source",
    "source_count=%d",
    "processed_blocks=%d",
    "processed_samples=%d",
    "skipped_blocks=%d",
    "dry_fallback_blocks=%d",
    "fallback_runtime=%d",
    "fallback_short=%d",
    "fallback_invalid=%d",
    "fallback_remainder=%d",
    "last_fallback=%s",
    "spatial_sources=%d",
    "source_origin=(%.1f,%.1f,%.1f)",
    "listener_origin=(%.1f,%.1f,%.1f)",
    "listener_forward=(%.2f,%.2f,%.2f)",
    "listener_right=(%.2f,%.2f,%.2f)",
    "distance=%.1f pan=%.3f attenuation=%.3f",
    "spatial_volumes=%d/%d/%d",
    "clipping=%d",
    "transducer_ms=%.3f",
    "QGE_MEASURE_AUDIO_BLOCK",
    "QGE_OBSERVE_AUDIO_MIX",
    "measurement.entropy_offset = spatial_hash;",
    "\"audio_source\"",
    "\"audio_source_frame\"",
]:
    require(quantum, needle, "source telemetry contract")

for needle in [
    "sound_quantum_mode=\"${QGE_STREAM_SND_QUANTUM:-1}\"",
    "sound_quantum_mode=\"$(normalize_nonnegative_int \"$sound_quantum_mode\" 1)\"",
    "\"snd_quantum\": $sound_quantum_mode",
    "echo \"snd_quantum $sound_quantum_mode\"",
    "-e '/QGE audio source/p'",
    "snd_quantum=$sound_quantum_mode",
    "Sound quantum mode: $sound_quantum_mode",
]:
    require(stream, needle, "stream source-mode audio contract")

print("snd_quantum source ownership contract: PASSED")
PY
