#!/usr/bin/env python3
"""Interactive Unicode text encoder / decoder for Termux and standard Python."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

TAG_BASE = 0xE0000
TAG_BEGIN = 0xE0001
TAG_CANCEL = 0xE007F
TAG_PREFIX = "how"
V2_MAGIC = "INV2:"
OUTPUT_DIR = Path("output")


class UserCancelled(Exception):
    pass


def tag_ascii(value: str) -> str:
    return "".join(chr(TAG_BASE + ord(char)) for char in value)


def read_manual(prompt: str) -> str:
    print(f"\n{prompt}")
    print("Type one line, then press Enter. For multiline text, copy it to the clipboard first.")
    try:
        value = input("> ")
    except EOFError:
        raise UserCancelled
    if not value:
        raise ValueError("Input cannot be empty.")
    return value


def read_clipboard(prompt: str) -> str:
    command = shutil.which("termux-clipboard-get")
    if not command:
        raise ValueError(
            "Clipboard input unavailable: termux-clipboard-get was not found. "
            "Install Termux:API and the termux-api package."
        )
    try:
        result = subprocess.run(
            [command],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Clipboard read failed: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or "unknown error"
        raise ValueError(f"Clipboard read failed: {detail}")
    if not result.stdout:
        raise ValueError("Clipboard is empty.")
    print(f"\n{prompt}")
    print(f"Clipboard message loaded ({len(result.stdout)} characters).")
    return result.stdout


def read_message(prompt: str) -> str:
    try:
        return read_clipboard(prompt)
    except ValueError as exc:
        print(f"\n{exc}")
        print("Manual input fallback:")
        return read_manual(prompt)


def encode_tags(value: str, visible_prefix: str = TAG_PREFIX) -> str:
    raw = value.encode("utf-8")
    payload_hex = raw.hex()
    checksum = hashlib.sha256(raw).hexdigest()[:16]
    framed = V2_MAGIC + payload_hex + ":" + checksum
    return visible_prefix + chr(TAG_BEGIN) + tag_ascii(framed) + chr(TAG_CANCEL)


def _decode_v2(value: str) -> str:
    marker = chr(TAG_BEGIN) + tag_ascii(V2_MAGIC)
    search_from = 0
    while True:
        start = value.find(marker, search_from)
        if start < 0:
            break
        end = value.find(chr(TAG_CANCEL), start + len(marker))
        if end >= 0:
            tagged = value[start + len(chr(TAG_BEGIN)):end]
            try:
                decoded_ascii = "".join(
                    chr(ord(char) - TAG_BASE) for char in tagged
                )
                if not decoded_ascii.startswith(V2_MAGIC):
                    raise ValueError("Invalid version marker.")
                fields = decoded_ascii[len(V2_MAGIC):].split(":")
                if len(fields) != 2:
                    raise ValueError("Invalid frame structure.")
                payload_hex, checksum = fields
                if len(payload_hex) % 2 or any(
                    char not in "0123456789abcdefABCDEF" for char in payload_hex
                ):
                    raise ValueError("Invalid payload encoding.")
                if len(checksum) != 16 or any(
                    char not in "0123456789abcdef" for char in checksum
                ):
                    raise ValueError("Invalid integrity field.")
                raw = bytes.fromhex(payload_hex)
                expected = hashlib.sha256(raw).hexdigest()[:16]
                if not hmac.compare_digest(checksum, expected):
                    raise ValueError("Integrity check failed.")
                return raw.decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                search_from = start + 1
                continue
        search_from = start + 1
    raise ValueError("No valid Invisible v2 payload was found.")


def decode_legacy_tags(value: str) -> str:
    prefix = TAG_PREFIX + chr(TAG_BEGIN)
    if not value.startswith(prefix) or not value.endswith(chr(TAG_CANCEL)):
        raise ValueError("Invalid legacy Unicode Tags payload or missing markers.")
    payload = value[len(prefix):-1]
    decoded = []
    for char in payload:
        codepoint = ord(char)
        offset = codepoint - TAG_BASE
        if not (0x20 <= offset <= 0x7E or offset in (0x09, 0x0A, 0x0D)):
            raise ValueError("Legacy payload contains an unsupported Tag character.")
        decoded.append(chr(offset))
    return "".join(decoded)


def encode_base64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def decode_base64(value: str) -> str:
    try:
        raw = base64.b64decode("".join(value.split()), validate=True)
        return raw.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError(f"Invalid Base64 payload: {exc}") from exc


def decode_payload(value: str) -> tuple[str, str]:
    try:
        return _decode_v2(value), "Invisible v2"
    except ValueError:
        pass
    if value.startswith(TAG_PREFIX + chr(TAG_BEGIN)):
        return decode_legacy_tags(value), "Legacy Unicode Tags"
    return decode_base64(value), "Base64"


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
            encoding="utf-8",
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


def choose_visible_prefix() -> str | None:
    print("\nChoose visible text:")
    print("[1] Default (how)")
    print("[2] Custom")
    print("[3] Back")
    choice = input("Select [1-3, Enter=1]: ").strip() or "1"
    if choice == "1":
        return TAG_PREFIX
    if choice == "2":
        return input("Enter custom visible text (text/emoji/symbols): ")
    if choice == "3":
        return None
    raise ValueError("Invalid visible-text choice.")


def encode_flow() -> None:
    message = read_manual("Message to hide:")
    visible_prefix = choose_visible_prefix()
    if visible_prefix is None:
        print("Returned to main menu.")
        return
    encoded = encode_tags(message, visible_prefix)
    decoded, _ = decode_payload(encoded)
    if decoded != message:
        raise RuntimeError("Round-trip verification failed. Output was not delivered.")
    print("\nInvisible v2 output:")
    print(f"Visible text: {visible_prefix!r}")
    print("Hidden payload: UTF-8 bytes encoded as invisible Unicode Tag characters.")
    print("\nEncoded result:")
    print(encoded)
    print("\nRound-trip verification: PASS")
    print("Integrity check: PASS")
    deliver(encoded, timestamped_name("encoded"))


def decode_flow() -> None:
    payload = read_message("Encoded payload:")
    decoded, label = decode_payload(payload)
    print(f"\nDecoded message ({label}):")
    print("-" * 40)
    print(decoded)
    print("-" * 40)
    deliver(decoded, timestamped_name("decoded"))


def main() -> int:
    print("INVISIBLE")
    print("Interactive Unicode text encoder / decoder")
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
