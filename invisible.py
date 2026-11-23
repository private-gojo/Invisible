#!/usr/bin/env python3
"""Interactive text encoder/decoder for Termux and standard Python."""

from __future__ import annotations

import base64
import binascii
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

TAG_BASE = 0xE0000
TAG_BEGIN = 0xE0001
TAG_CANCEL = 0xE007F
TAG_PREFIX = "how"
OUTPUT_DIR = Path("output")


class UserCancelled(Exception):
    pass


def read_multiline(prompt: str) -> str:
    print(f"\n{prompt}")
    print("Enter .END on a line by itself to finish.")
    lines = []

    while True:
        try:
            line = input()
        except EOFError:
            raise UserCancelled

        if line == ".END":
            break
        lines.append(line)

    value = "\n".join(lines)
    if not value:
        raise ValueError("Input cannot be empty.")
    return value


def encode_tags(value: str) -> str:
    allowed = set("\n\r\t")
    for char in value:
        if not (0x20 <= ord(char) <= 0x7E or char in allowed):
            raise ValueError(
                "Unicode Tags mode accepts printable ASCII, newline, "
                "carriage return, and tab only. Use Base64 for Unicode text."
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
    message = read_multiline("Enter your message:")
    print("\nEncoding:")
    print("[1] Unicode Tags (experimental)")
    print("[2] Base64")
    choice = input("Select [1-2]: ").strip()

    if choice == "1":
        encoded = encode_tags(message)
        decoded = decode_tags(encoded)
        label = "Unicode Tags"
    elif choice == "2":
        encoded = encode_base64(message)
        decoded = decode_base64(encoded)
        label = "Base64"
    else:
        print("Invalid encoding choice.")
        return

    if decoded != message:
        raise RuntimeError("Round-trip verification failed. Output was not delivered.")

    print(f"\n{label} output:")
    print(encoded)
    print("\nRound-trip verification: PASS")
    deliver(encoded, timestamped_name("encoded"))


def decode_flow() -> None:
    payload = read_multiline("Paste encoded payload:")
    print("\nPayload format:")
    print("[1] Unicode Tags")
    print("[2] Base64")
    choice = input("Select [1-2]: ").strip()

    if choice == "1":
        decoded = decode_tags(payload)
    elif choice == "2":
        decoded = decode_base64(payload)
    else:
        print("Invalid format choice.")
        return

    print("\nDecoded message:")
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
