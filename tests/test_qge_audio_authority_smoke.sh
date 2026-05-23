#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/qge_audio_authority_smoke.XXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT

agent_dir="$tmpdir/agent_stream"
mkdir -p "$agent_dir/audio" "$agent_dir/logs" "$agent_dir/trace"

cat > "$agent_dir/trace/qge_trace_summary.json" <<'JSON'
{
  "runtime_evidence": {
    "single_trace_ready": true,
    "audio": {
      "ready": true,
      "source_spatial_count": 3,
      "source_frame_count": 2,
      "attenuation_pan_authority_count": 2,
      "flags": {
        "processed": true,
        "spatial": true,
        "dry_fallback": true,
        "view_entity": true
      }
    }
  }
}
JSON

cat > "$agent_dir/logs/quantum_quake.log" <<'LOG'
QGE audio source owner=audio_source source_count=1 processed_sources=1 processed_blocks=4 processed_samples=1024 skipped_blocks=0 dry_fallback_blocks=0 clipping=0 transducer_ms=3.000 last_subject=1819549431 last_source=weapons/sgun1.wav fallback_runtime=0 fallback_short=0 fallback_invalid=0 fallback_remainder=0 last_fallback=none spatial_sources=1 avg_distance=0.0 avg_abs_pan=0.000 avg_atten=1.000 attenuation_pan_sources=1 attenuation_pan_ready=1 attenuation_pan_requested=1 attenuation_pan_selected=1 attenuation_pan_fallback=0 attenuation_pan_avg_abs_delta=0.000 attenuation_pan_max_delta=0 attenuation_pan_last_classic=255/255 attenuation_pan_last_qge=255/255 attenuation_pan_last_abs_delta=0/0 attenuation_pan_last_max_delta=0 attenuation_pan_readiness=ready attenuation_pan_off_reason=none source_origin=(480.0,-352.0,92.0) listener_origin=(480.0,-352.0,110.0) listener_forward=(0.00,1.00,0.00) listener_right=(1.00,0.00,0.00) distance=0.0 pan=0.000 attenuation=1.000 spatial_volumes=255/255/255 spatial_channels=2 spatial_valid=1
QGE audio source owner=audio_source source_count=1 processed_sources=1 processed_blocks=4 processed_samples=1024 skipped_blocks=0 dry_fallback_blocks=1 clipping=0 transducer_ms=3.000 last_subject=292984781 last_source=ambience/comp1.wav fallback_runtime=0 fallback_short=0 fallback_invalid=0 fallback_remainder=1 last_fallback=audio_source_remainder_block spatial_sources=1 avg_distance=324.5 avg_abs_pan=0.000 avg_atten=0.026 attenuation_pan_sources=1 attenuation_pan_ready=0 attenuation_pan_requested=1 attenuation_pan_selected=0 attenuation_pan_fallback=1 attenuation_pan_avg_abs_delta=1.000 attenuation_pan_max_delta=1 attenuation_pan_last_classic=6/6 attenuation_pan_last_qge=6/5 attenuation_pan_last_abs_delta=0/1 attenuation_pan_last_max_delta=1 attenuation_pan_readiness=threshold attenuation_pan_off_reason=threshold source_origin=(250.0,194.0,72.0) listener_origin=(0.0,0.0,0.0) listener_forward=(0.00,0.00,0.00) listener_right=(0.00,0.00,0.00) distance=324.5 pan=0.000 attenuation=0.026 spatial_volumes=6/6/255 spatial_channels=2 spatial_valid=1
LOG

cat > "$agent_dir/manifest.json" <<JSON
{
  "audio": {
    "status": "complete",
    "raw_file": "$agent_dir/audio/quake_mix_s16le.raw",
    "metadata_file": "$agent_dir/audio/quake_mix_s16le.json",
    "bytes_file": "$agent_dir/audio/bytes.txt",
    "snd_quantum": 2,
    "snd_quantum_source_authority": 1,
    "format": "s16le",
    "bytes": 4096
  },
  "logs": {
    "runtime_log": "$agent_dir/logs/quantum_quake.log"
  },
  "trace_summary": {
    "status": "complete",
    "agent_file": "$agent_dir/trace/qge_trace_summary.json",
    "runtime_evidence_ready": 1
  }
}
JSON

python3 "$repo_root/tools/qge_audio_authority_smoke.py" \
    --agent-stream-dir "$agent_dir" --json

echo "QGE audio authority smoke contract: PASSED"
