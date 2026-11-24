# Invisible

Interactive CLI that hides ASCII text inside invisible Unicode Tag characters, and decodes it back. Built for Termux, works on any Python 3.8+.

The visible text of an encoded message is just `how`. The real message is attached as invisible characters right after it.

## Features

- Encode any pasted text into Unicode Tags: common Unicode is converted to ASCII, the rest is escaped, nothing makes it fail
- Decode Unicode Tags payloads, with Base64 as a fallback for decode
- Typing and multiline paste both work, no terminator needed
- Clipboard input (`c`) for very long messages
- Round-trip check before any encoded output is delivered
- Output to terminal, clipboard (Termux:API), file, or clipboard + file

## Requirements

- Python 3.8 or newer
- Optional: Termux:API app + `termux-api` package (clipboard copy and the `c` input shortcut)

## Installation

### Termux (Android)

```sh
pkg update && pkg upgrade -y
pkg install -y python git
```

Optional, for clipboard support:

```sh
pkg install -y termux-api
```

Also install the **Termux:API** app (same source as your Termux, e.g. F-Droid). Without the app, the `termux-api` package alone will not work.

Get the code:

```sh
git clone https://github.com/private-gojo/Invisible.git
cd Invisible
```

### Linux / macOS / Windows

Requires Python 3.8+ and git:

```sh
git clone https://github.com/private-gojo/Invisible.git
cd Invisible
```

No third-party Python packages are needed. On Windows, the multiline paste auto-detect is skipped (single-line typing and `c` still work if a clipboard tool is available).

## Run

```sh
python invisible.py
```

Run it from inside the repo folder. Saved files go to `./output/` relative to where you run it.

## How to use

Main menu:

```
[1] Encode
[2] Decode
[3] Exit
```

### Encode

1. Choose `1`.
2. Type or paste your message, then press Enter.
   - Multiline paste is detected automatically.
   - If the paste had no final newline, you will see `(Paste received. Press Enter to continue)`. Press Enter once.
   - Enter `c` to use the clipboard contents instead (best for long messages).
3. The tool prints the encoded result and `Round-trip verification: PASS`.
4. Choose how to deliver it:

```
[1] Terminal only
[2] Clipboard
[3] Save to file
[4] Clipboard + file
```

Copy the result (option `2` or `4`, or select it manually) and send it where you want. Only `how` will be visible.

Any text is accepted. Unicode Tags can only carry ASCII, so before encoding the tool cleans the message and prints a `Note:` for each change:

- Smart quotes, dashes, `...`, bullets, arrows and accents (`ñ` becomes `n`) are converted to plain ASCII.
- Zero-width characters and stray control characters are removed.
- Anything else (emoji, Japanese, etc.) is escaped as `\u{HEX}`, for example `🔥` becomes `\u{1F525}`. The receiving side sees that escape as plain text; Decode turns it back into the real character.

### Decode

1. Choose `2`.
2. Paste the encoded text (type `c` to read it from the clipboard).
3. The decoded message is printed (`\u{HEX}` escapes are turned back into characters), and you can deliver it the same way as above.

Decode expects a payload that starts with `how` followed by the hidden characters and ends with the cancel tag. If it does not look like a Tags payload, it is tried as Base64 instead.

## Output files

Files are saved to `output/` with a timestamp:

- `encoded_YYYYMMDD_HHMMSS.txt`
- `decoded_YYYYMMDD_HHMMSS.txt`

The folder contents are git-ignored.

## Limits and known behavior

- **Long messages:** each hidden character takes 2 UTF-16 units / 4 UTF-8 bytes, and apps or AI input limits may count or tokenize them heavily. Very long hidden messages may be cut off or ignored by the receiving app.
- **Terminal line limit:** a single typed or pasted line over roughly 4096 characters is truncated by the terminal itself. Use `c` (clipboard) for anything longer.
- **Platform stripping:** messaging apps may remove or normalize Unicode Tag characters. Encoding is experimental and not a guarantee of invisible transport.
- **Escapes:** a message that literally contains text like `\u{41}` will be shown as `A` after Decode.
- **Decode is strict:** extra text around the payload, a trailing space, or a missing marker will make decode fail.
- Base64 is an encoding, not encryption. Anyone can decode it.
