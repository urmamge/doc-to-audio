"""Convert documents (.pdf, .docx, .txt, .md) to MP3 using the Ava neural voice.

Usage: doc_to_audio.py [--speed 1.25] FILE [FILE ...]

When several files are selected in Explorer, Windows starts one process per
file. Each process drops its file into a queue; the first one to grab the lock
becomes the worker and converts everything in the queue in a single window.
"""

import argparse
import asyncio
import msvcrt
import os
import re
import subprocess
import sys
import time
import uuid
import zipfile
from collections import Counter
from pathlib import Path
import edge_tts
from defusedxml import ElementTree

VOICE = "en-US-AvaMultilingualNeural"
SUPPORTED = {".pdf", ".docx", ".txt", ".md"}
STATE_DIR = Path(os.environ["LOCALAPPDATA"]) / "doc-to-audio"
QUEUE_DIR = STATE_DIR / "queue"
LOCK_FILE = STATE_DIR / "worker.lock"
# How long the worker waits for sibling processes to queue their files.
GATHER_SECONDS = 1.5


class NoTextError(Exception):
    pass


# ---------------------------------------------------------------- extraction

def extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    pages = [(p.extract_text() or "").splitlines() for p in PdfReader(path).pages]

    # Lines repeated at the top or bottom of most pages are headers/footers.
    edge_lines = Counter()
    for lines in pages:
        stripped = [l.strip() for l in lines if l.strip()]
        edge_lines.update(set(stripped[:2] + stripped[-2:]))
    repeated = set()
    if len(pages) >= 3:
        repeated = {l for l, n in edge_lines.items() if n >= len(pages) * 0.5}

    page_number = re.compile(r"^\s*(page\s*)?\d+(\s*(of|/)\s*\d+)?\s*$", re.I)
    kept = []
    for lines in pages:
        kept.extend(l for l in lines if l.strip() not in repeated and not page_number.match(l))
        kept.append("")
    return "\n".join(kept)


def extract_docx(path: Path) -> str:
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as z:
        root = ElementTree.fromstring(z.read("word/document.xml"))
    paragraphs = []
    for p in root.iter(f"{ns}p"):
        text = "".join(t.text or "" for t in p.iter(f"{ns}t"))
        paragraphs.append(text)
    return "\n\n".join(paragraphs)


def extract_md(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"```.*?```", "", text, flags=re.S)           # code blocks
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)            # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)        # links -> text
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)   # headings
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)        # bullets
    text = re.sub(r"[*_`~]+", "", text)                         # emphasis
    # Headings and list items read better as separate sentences.
    return re.sub(r"\n(?=\S)", "\n\n", text)


def extract(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_pdf(path)
    if ext == ".docx":
        return extract_docx(path)
    if ext == ".md":
        return extract_md(path)
    return path.read_text(encoding="utf-8", errors="replace")


def clean(text: str) -> str:
    text = re.sub(r"https?://\S+|www\.\S+", "", text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)    # words hyphenated across lines
    paragraphs = re.split(r"\n\s*\n", text)
    # Join lines broken mid-paragraph.
    paragraphs = [re.sub(r"\s*\n\s*", " ", p).strip() for p in paragraphs]
    paragraphs = [re.sub(r"[ \t]+", " ", p) for p in paragraphs if p]
    return "\n\n".join(paragraphs)


# ------------------------------------------------------------------- speech

def output_path(src: Path, speed: float) -> Path:
    suffix = "" if speed == 1 else f" ({speed:g}x)"
    out = src.with_name(f"{src.stem}{suffix}.mp3")
    n = 2
    while out.exists():
        out = src.with_name(f"{src.stem}{suffix} ({n}).mp3")
        n += 1
    return out


async def synthesize(text: str, out: Path, speed: float, label: str) -> None:
    rate = f"+{round((speed - 1) * 100)}%"
    communicate = edge_tts.Communicate(text, VOICE, rate=rate)
    total, spoken, last_shown = len(text), 0, -1
    tmp = out.with_suffix(".mp3.part")
    try:
        with open(tmp, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif "Boundary" in chunk["type"]:
                    spoken += len(chunk.get("text", "")) + 1
                    pct = min(99, spoken * 100 // max(total, 1))
                    if pct != last_shown:
                        print(f"\r  {label}: {pct}%", end="", flush=True)
                        last_shown = pct
        tmp.replace(out)
    finally:
        tmp.unlink(missing_ok=True)
    print(f"\r  {label}: done    ")


def convert(path: Path, speed: float, label: str) -> Path:
    if path.suffix.lower() not in SUPPORTED:
        raise ValueError(f"unsupported file type {path.suffix}")
    text = clean(extract(path))
    if not text.strip():
        hint = " (it may be a scanned PDF, which has no text to read)" if path.suffix.lower() == ".pdf" else ""
        raise NoTextError(f"no readable text found{hint}")
    out = output_path(path, speed)
    asyncio.run(synthesize(text, out, speed, label))
    return out


def notify(title: str, message: str) -> None:
    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "''")

    ps = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml('<toast><visual><binding template="ToastGeneric"><text>{esc(title)}</text><text>{esc(message)}</text></binding></visual></toast>')
$app = '{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )


# ------------------------------------------------------------- queue/worker

def enqueue(files: list[Path], speed: float) -> None:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    for f in files:
        entry = QUEUE_DIR / f"{time.time_ns()}-{uuid.uuid4().hex}.txt"
        entry.write_text(f"{speed}\n{f}", encoding="utf-8")


def take_queue() -> list[tuple[float, Path]]:
    jobs = []
    for entry in sorted(QUEUE_DIR.glob("*.txt")):
        try:
            speed, path = entry.read_text(encoding="utf-8").split("\n", 1)
            jobs.append((float(speed), Path(path)))
        except (OSError, ValueError):
            pass
        entry.unlink(missing_ok=True)
    return jobs


def run_worker() -> None:
    print("Converting to audio with Ava...\n")
    time.sleep(GATHER_SECONDS)
    done, failed, n = [], [], 0
    while True:
        jobs = take_queue()
        if not jobs:
            break
        for speed, path in jobs:
            n += 1
            label = f"[{n}] {path.name}" + ("" if speed == 1 else f" at {speed:g}x")
            try:
                done.append(convert(path, speed, label))
            except Exception as e:
                print(f"\r  {label}: FAILED - {e}")
                failed.append((path, e))

    if done:
        names = ", ".join(p.name for p in done)
        notify("Audio ready" if len(done) == 1 else f"{len(done)} audio files ready", names)
    if failed:
        notify("Audio conversion failed", ", ".join(p.name for p, _ in failed))
        input("\nSome files could not be converted. Press Enter to close.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    enqueue([f.resolve() for f in args.files], args.speed)

    # Loop so that a file queued just as the worker finished still gets picked up.
    while any(QUEUE_DIR.glob("*.txt")):
        with open(LOCK_FILE, "a+") as lock:
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                # Another window is already the worker; it will pick up our file.
                return
            try:
                run_worker()
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)

if __name__ == "__main__":
    main()
