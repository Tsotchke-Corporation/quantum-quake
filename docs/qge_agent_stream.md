# QGE Agent Media Stream

`tools/quake_graphics_stream.sh` writes a project-local stream directory for
agent-side inspection while the game is running.

Default location:

```text
diagnostics/agent_stream/<timestamp>/
```

The directory is intentionally simple and tail-friendly:

- `manifest.json`: current stream contract, capture path, render settings, and
  audio/video/log locations.
- `events.ndjson`: append-only runtime events such as stream start, video frame,
  audio raw, trace done, and stream done.
- `video/frames/frame_###.png`: copied screenshots as they are produced.
- `video/frame_count.txt`: current number of mirrored frames, updated as frames
  arrive.
- `video/latest_frame.txt`: path to the newest mirrored frame, updated as frames
  arrive.
- `audio/quake_mix_s16le.raw`: post-QGE mixed stereo PCM when sound is enabled.
- `audio/quake_mix_s16le.json`: audio metadata including sample rate, format,
  channels, and sample pair count.
- `logs/quantum_quake.log`: runtime console log mirrored into the stream.
- `logs/open.log`: LaunchServices notes for macOS `open` mode.
- `qge_agent_stream_icc_evidence.jsonl`: ICC-native runtime events for the
  manifest, video frame, raw audio, audio metadata, and completion signal.

The stream script prints:

```text
QGE_AGENT_STREAM <dir>
QGE_AGENT_VIDEO_FRAME <index> <png>
QGE_AGENT_STREAM_DONE <dir>
```

In macOS `open` launch mode the harness keeps `open -W` in the foreground, but
now runs a side watcher that tails the game log and mirrors screenshots into the
agent stream while the app is still running. Consumers should follow
`events.ndjson` or `video/latest_frame.txt` rather than waiting for
`QGE_AGENT_STREAM_DONE`.

Audio capture requires the game sound system to run:

```sh
QGE_STREAM_SOUND=1 bash tools/quake_graphics_stream.sh
```

The raw audio format is signed 16-bit little-endian stereo PCM. Consumers should
read `audio/quake_mix_s16le.json` for the sample rate before playback or
conversion.
