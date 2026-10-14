# doc-to-audio

Right-click a `.pdf`, `.docx`, `.txt` or `.md` file in Windows Explorer → **Show more options** → **Convert to audio (Ava)** → pick a speed (normal, 1.25x, 1.5x, 2x). An MP3 appears next to the original and a notification pops up when it's done.

- Voice: Microsoft's online `en-US-AvaMultilingualNeural` via [edge-tts](https://github.com/rany2/edge-tts) (needs internet).
- Cleans text before reading: drops repeated PDF headers/footers, page numbers and URLs; rejoins hyphenated and broken lines; strips Markdown syntax.
- Select several files at once: they're all converted in one window.
- Scanned (image-only) PDFs have no text and are reported as an error.

## Install / uninstall

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1    # per-user, no admin needed
powershell -ExecutionPolicy Bypass -File uninstall.ps1
```
