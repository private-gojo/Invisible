# Invisible

Interactive CLI for encoding and decoding text using Unicode Tags and Base64.

## Features

- Interactive multiline message input
- Unicode Tag encoding
- Base64 encoding
- Decode support
- Round-trip validation before output
- Clipboard copy through Termux:API when available
- Save encoded output to a file

## Requirements

- Python 3.8 or newer
- Optional: Termux:API for clipboard integration

## Run

```sh
python invisible.py
```

## Notes

Unicode Tag characters may be removed or normalized by messaging apps and other platforms. This encoding is experimental and is not a guarantee of invisible transport.

Base64 is an encoding format, not encryption. Anyone can decode it.
