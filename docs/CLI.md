# Glimio CLI

The `glimio` command is a first-class interface to the application. It can be used without starting FastAPI or the Angular interface. The CLI imports only `seance` and its core dependencies; `fastapi`, `uvicorn`, `python-multipart`, and the frontend toolchain are needed only by the Web edition.

## Install

From the repository root:

```console
python -m pip install -e '.[cli]'
```

For Web as well, install its separate dependencies:

```console
python -m pip install -e '.[web]'
```

Optional AI providers remain separate source-install extras (`.[diarization]`, `.[separation]`) or can be installed in a packaged build with `glimio providers install ID`. Models and native executables remain independent resources; see [PROVIDERS.md](PROVIDERS.md) and [MODELS.md](MODELS.md).

## Main workflows

```console
glimio --help
glimio record --auto-process
glimio import ./meeting.mp4 --import-action process
glimio transcribe ./seances/2026-10-24_12-00-00
glimio summarize ./seances/2026-10-24_12-00-00
glimio process ./seances/2026-10-24_12-00-00
```

`import` creates the same session layout as Web import, preserves detected streams/channels separately, and optionally starts transcription or the full pipeline. FFmpeg and ffprobe must be available for import.

## Library and audio tracks

```console
glimio sessions list
glimio sessions list --query "budget" --filter transcript
glimio sessions show 2026-10-24_12-00-00
glimio sessions rename 2026-10-24_12-00-00 "Project meeting"
glimio sessions settings show 2026-10-24_12-00-00
glimio sessions settings save 2026-10-24_12-00-00 --file settings.json
glimio sessions audio list 2026-10-24_12-00-00
glimio sessions audio disable 2026-10-24_12-00-00 audio_import-ch2.wav
glimio sessions audio enable 2026-10-24_12-00-00 audio_import-ch2.wav
glimio sessions audio delete 2026-10-24_12-00-00 audio_import-ch2.wav --yes
```

Set `GLIMIO_DIRECTORY` to override the session root or pass `--directory` to individual library commands. The library is never recursively traversed outside its configured root. Rename/delete/audio edits are refused when the shared persistent job history indicates work is active for the session. `--yes` is required for destructive non-interactive calls.

## Transcripts and summaries

```console
glimio artifacts show 2026-10-24_12-00-00 transcript
glimio artifacts show 2026-10-24_12-00-00 summary --output ./summary.md
glimio artifacts save-summary 2026-10-24_12-00-00 --file ./summary-edited.md --revision 123456:789
```

`artifacts show` writes to stdout by default. Use `--json` with `sessions show` to obtain metadata and file information. Summary editing observes the same stale-revision check as the Web API; `--force` explicitly bypasses it.

## Intelligent cross-session search

```console
glimio search "Which decisions were made about the launch?"
glimio search "budget" --session 2026-10-24_12-00-00 --top-k 6
glimio search --list
glimio search --show 20261024T120000-abcdef12
glimio search --synthesize 20261024T120000-abcdef12 --excerpts 1,3 --output ./answer.md
glimio search "budget" --synthesize-results --output ./answer.md
```

Search reads local summaries and transcripts using the same retrieval and synthesis code as the Web app. Each CLI search is saved in the Glimio data directory under `searches/`, so it can be reviewed or synthesized again later. `--excerpts` selects original source numbers; the saved retrieval remains intact, and the chosen excerpts are renumbered only within the new synthesis so citations remain valid. AI synthesis requires a working configured text-generation provider and its binary/model.

## Providers, preferences, jobs, devices

```console
glimio providers list
glimio providers info speechbrain-ecapa
glimio providers install speechbrain-ecapa
glimio providers doctor --json
glimio preferences show --json
glimio preferences save --file preferences.json
glimio jobs list
glimio jobs show JOB_ID
glimio jobs cancel JOB_ID
glimio jobs clear
glimio devices --json
```

Preferences and persistent job history use the same SQLite database as Web (normally `.glimio/glimio.sqlite3`, or a directory set with `GLIMIO_DATA_DIR`). `jobs cancel` delegates to the running Web worker at `http://127.0.0.1:8765` by default because the current live queue and cancellation signals are owned by that running process. Set `GLIMIO_WEB_URL` or pass `--web-url` to choose a different endpoint. Reading and clearing finished persisted history does not require Web.

## Dependency boundary

- `seance.core` owns the shared library, file mutations, local search/retrieval, synthesis, persistence, preference storage, job history and device discovery.
- `seance.cli_commands` translates terminal arguments to those use cases; `seance.cli` owns processing/recording command line options.
- `web.app` owns HTTP validation, live queue lifecycle and SSE presentation, and calls the same core services for library mutations, search, persistence and device discovery.
- `.[cli]` adds no Web dependencies. `.[web]` adds FastAPI, Uvicorn and multipart upload support. Heavy provider packages stay in provider-specific optional extras or the managed provider runtime.

The current Web worker remains a process-local live queue; cancellation of a running Web job therefore requires the Web process to be reachable. CLI processing commands run synchronously in the CLI process and can be interrupted with Ctrl+C.
