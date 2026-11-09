# Security

diga hears your microphone, sees your keyboard and types into other apps, so security reports
are taken seriously.

**Reporting.** Please use [a private security advisory](https://github.com/r-ms/diga/security/advisories/new)
rather than a public issue. Expect a first answer within a week.

**What diga does and does not do**

- Audio and text stay on your Mac. After the models are downloaded diga makes no network
  requests; there are no accounts and no telemetry.
- The microphone is open only while you hold the key or a long dictation is running.
- The keyboard tap is listen-only and reacts to the right ⌘ alone; other keys are not recorded.
- Logs written to a file (when started at login) leave out what you dictated.
- Models whose code runs when they load (GigaAM uses `trust_remote_code`) are pinned to a
  reviewed commit in [`models.py`](src/diga/models.py).
