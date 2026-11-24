#!/usr/bin/env python3
"""Interactive text encoder/decoder for Termux and standard Python."""

from __future__ import annotations

import base64
import binascii
import os
import re
import select
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

try:
    import termios
except ImportError:  # non-POSIX platforms
    termios = None

TAG_BASE = 0xE0000
TAG_BEGIN = 0xE0001
TAG_CANCEL = 0xE007F
TAG_PREFIX = "how"
OUTPUT_DIR = Path("output")


class UserCancelled(Exception):
    pass


def drain_pending(timeout: float = 0.3) -> str:
    """Collect text that arrived right after the first line (multiline paste).

    The wait starts only after the first line was submitted, so typing speed
    is never limited. Canonical mode is switched off for the drain so a last
    pasted line without a trailing newline is also readable.
    """
    if termios is None or not sys.stdin.isatty():
        return ""

    fd = sys.stdin.fileno()
    try:
        saved = termios.tcgetattr(fd)
        raw = termios.tcgetattr(fd)
    except termios.error:
        return ""

    raw[3] &= ~termios.ICANON
    raw[6][termios.VMIN] = 1
    raw[6][termios.VTIME] = 0

    chunks = []
    try:
        termios.tcsetattr(fd, termios.TCSANOW, raw)
        while select.select([fd], [], [], timeout)[0]:
            data = os.read(fd, 65536)
            if not data:
                break
            chunks.append(data)
    except OSError:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)

    return b"".join(chunks).decode("utf-8", errors="replace")


def read_clipboard() -> str:
    command = shutil.which("termux-clipboard-get")
    if not command:
        raise ValueError(
            "termux-clipboard-get was not found. "
            "Install Termux:API and the termux-api package."
        )

    try:
        result = subprocess.run(
            [command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError as exc:
        raise ValueError(f"Clipboard error: {exc}") from exc

    if result.returncode != 0:
        detail = result.stderr.strip() or "unknown error"
        raise ValueError(f"Clipboard error: {detail}")
    return result.stdout


def read_message(prompt: str) -> str:
    print(f"\n{prompt}")
    print("Type or paste your message, then press Enter.")
    print("Multiline paste is detected automatically. Enter 'c' to use the clipboard.")
    try:
        first = input("> ")
        if first.strip().lower() == "c":
            value = read_clipboard()
        else:
            value = first
            extra = drain_pending()
            if extra:
                value = first + "\n" + extra
                if not extra.endswith(("\n", "\r")):
                    # Pasted text had no final newline; the user's Enter is
                    # still to come, so consume it here instead of the menu.
                    input("(Paste received. Press Enter to continue) ")
    except EOFError:
        raise UserCancelled

    value = value.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    if not value.strip():
        raise ValueError("Input cannot be empty.")
    return value


PUNCT_MAP = str.maketrans(
    {
        "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
        "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
        "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
        "\u2014": "-", "\u2015": "-", "\u2212": "-",
        "\u2026": "...", "\u2022": "*", "\u00b7": "*",
        "\u2192": "->", "\u2190": "<-", "\u00d7": "x",
        "\u00a0": " ", "\u2002": " ", "\u2003": " ", "\u2009": " ",
        "\u202f": " ", "\u3000": " ",
    }
)
# Invisible helpers that carry no text of their own.
DROP_CHARS = set("\u200b\u200c\u200d\u2060\ufeff\ufe0e\ufe0f")
ESCAPE_RE = re.compile(r"\\u\{([0-9A-Fa-f]{1,6})\}")


def is_tag_safe(char: str) -> bool:
    return 0x20 <= ord(char) <= 0x7E or char in "\n\r\t"


def sanitize_for_tags(value: str) -> tuple[str, list[str]]:
    """Make any text encodable: convert common Unicode to ASCII, escape the rest.

    Returns the cleaned text and short notes describing what was changed.
    """
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    converted = 0
    dropped = 0
    escaped: list[str] = []
    out: list[str] = []

    for char in value:
        if is_tag_safe(char):
            out.append(char)
            continue
        if char in DROP_CHARS:
            dropped += 1
            continue

        mapped = char.translate(PUNCT_MAP)
        if mapped != char:
            out.append(mapped)
            converted += 1
            continue

        base = "".join(
            part
            for part in unicodedata.normalize("NFKD", char)
            if not unicodedata.combining(part)
        )
        if base and all(is_tag_safe(part) for part in base):
            out.append(base)
            converted += 1
            continue

        if ord(char) < 0x20 or ord(char) == 0x7F:
            dropped += 1  # stray control characters
            continue

        out.append("\\u{%X}" % ord(char))
        if char not in escaped:
            escaped.append(char)

    notes = []
    if converted:
        notes.append(f"{converted} character(s) converted to ASCII (quotes, dashes, accents...)")
    if dropped:
        notes.append(f"{dropped} invisible/control character(s) removed")
    if escaped:
        shown = " ".join(f"{c}=U+{ord(c):X}" for c in escaped[:10])
        more = "" if len(escaped) <= 10 else f" (+{len(escaped) - 10} more)"
        notes.append(f"{len(escaped)} unique character(s) escaped as \\u{{HEX}}: {shown}{more}")
    return "".join(out), notes


def restore_escapes(value: str) -> str:
    def repl(match: re.Match) -> str:
        codepoint = int(match.group(1), 16)
        return chr(codepoint) if codepoint <= 0x10FFFF else match.group(0)

    return ESCAPE_RE.sub(repl, value)


def encode_tags(value: str) -> str:
    for index, char in enumerate(value):
        if not is_tag_safe(char):
            raise ValueError(
                f"Character {char!r} (U+{ord(char):X}) at position {index} "
                "cannot be encoded as a Unicode Tag."
            )

    payload = "".join(chr(TAG_BASE + ord(char)) for char in value)
    return TAG_PREFIX + chr(TAG_BEGIN) + payload + chr(TAG_CANCEL)


def decode_tags(value: str) -> str:
    prefix = TAG_PREFIX + chr(TAG_BEGIN)
    if not value.startswith(prefix) or not value.endswith(chr(TAG_CANCEL)):
        raise ValueError("Invalid Unicode Tags payload or missing markers.")

    payload = value[len(prefix):-1]
    decoded = []

    for char in payload:
        codepoint = ord(char)
        if not (TAG_BASE + 0x20 <= codepoint <= TAG_BASE + 0x7E):
            if codepoint not in (TAG_BASE + 0x0A, TAG_BASE + 0x0D, TAG_BASE + 0x09):
                raise ValueError("Payload contains an unsupported Tag character.")
        decoded.append(chr(codepoint - TAG_BASE))

    return "".join(decoded)


def encode_base64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def decode_base64(value: str) -> str:
    try:
        raw = base64.b64decode("".join(value.split()), validate=True)
        return raw.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError(f"Invalid Base64 payload: {exc}") from exc


def copy_clipboard(value: str) -> bool:
    command = shutil.which("termux-clipboard-set")
    if not command:
        print("Clipboard unavailable: termux-clipboard-set was not found.")
        print("Install Termux:API and the termux-api package to enable it.")
        return False

    try:
        result = subprocess.run(
            [command],
            input=value,
            text=True,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        print(f"Clipboard error: {exc}")
        return False

    if result.returncode != 0:
        detail = result.stderr.strip() or "unknown error"
        print(f"Clipboard error: {detail}")
        return False

    print("Copied to clipboard.")
    return True


def save_output(value: str, filename: str) -> bool:
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / filename
        path.write_text(value, encoding="utf-8")
        print(f"Saved: {path}")
        return True
    except OSError as exc:
        print(f"File save error: {exc}")
        return False


def deliver(value: str, filename: str) -> None:
    print("\nOutput method:")
    print("[1] Terminal only")
    print("[2] Clipboard")
    print("[3] Save to file")
    print("[4] Clipboard + file")

    choice = input("Select [1-4]: ").strip()
    if choice == "1":
        return
    if choice in ("2", "4"):
        copy_clipboard(value)
    if choice in ("3", "4"):
        save_output(value, filename)
    if choice not in ("1", "2", "3", "4"):
        print("Invalid choice. Output remains available in the terminal.")


def timestamped_name(prefix: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{stamp}.txt"


def encode_flow() -> None:
    raw_message = read_message("Enter your message:")
    message, notes = sanitize_for_tags(raw_message)
    for note in notes:
        print(f"Note: {note}")
    if not message.strip():
        raise ValueError("Nothing left to encode after cleanup.")

    encoded = encode_tags(message)
    decoded = decode_tags(encoded)

    if decoded != message:
        raise RuntimeError("Round-trip verification failed. Output was not delivered.")

    print(f"\nHidden length: {len(message)} characters")
    print("\nUnicode Tags output:")
    print("Visible text: how")
    print("Hidden payload: attached as invisible Unicode Tag characters.")
    print("\nEncoded result:")
    print(encoded)
    print("\nRound-trip verification: PASS")
    deliver(encoded, timestamped_name("encoded"))


def decode_flow() -> None:
    payload = read_message("Paste encoded payload:")

    if payload.startswith(TAG_PREFIX + chr(TAG_BEGIN)):
        decoded = restore_escapes(decode_tags(payload))
        label = "Unicode Tags"
    else:
        decoded = decode_base64(payload)
        label = "Base64"

    print(f"\nDecoded message ({label}):")
    print("-" * 40)
    print(decoded)
    print("-" * 40)
    deliver(decoded, timestamped_name("decoded"))


def main() -> int:
    print("INVISIBLE")
    print("Interactive text encoder / decoder")

    while True:
        print("\n[1] Encode")
        print("[2] Decode")
        print("[3] Exit")
        choice = input("Select [1-3]: ").strip()

        try:
            if choice == "1":
                encode_flow()
            elif choice == "2":
                decode_flow()
            elif choice == "3":
                print("Bye.")
                return 0
            else:
                print("Invalid choice.")
        except (ValueError, UserCancelled) as exc:
            if isinstance(exc, UserCancelled):
                print("\nInput cancelled.")
            else:
                print(f"\nError: {exc}")
        except KeyboardInterrupt:
            print("\nInterrupted.")
            return 130


if __name__ == "__main__":
    sys.exit(main())
