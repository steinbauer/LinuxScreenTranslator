#!/usr/bin/env python3
"""Extract translatable strings and compile catalogues.

Written in plain Python so contributors do not need the gettext tools
installed just to build a translation.

    python3 tools/i18n_tools.py extract          -> po/linux-screen-translator.pot
    python3 tools/i18n_tools.py compile          -> locale/<lang>/LC_MESSAGES/*.mo
"""

import ast
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOMAIN = "linux-screen-translator"
SOURCES = ("linux_screen_translator", ".")


def _python_files():
    seen = set()
    for base in SOURCES:
        directory = os.path.join(ROOT, base)
        for name in sorted(os.listdir(directory)):
            path = os.path.join(directory, name)
            if name.endswith(".py") and os.path.isfile(path) and path not in seen:
                seen.add(path)
                yield path


def extract():
    """Collect every _("...") literal, keeping source order."""
    messages = {}
    for path in _python_files():
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Name) and func.id == "_"):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            text = node.args[0].value
            if isinstance(text, str):
                location = f"{os.path.relpath(path, ROOT)}:{node.lineno}"
                messages.setdefault(text, []).append(location)
    return messages


def write_pot(messages):
    os.makedirs(os.path.join(ROOT, "po"), exist_ok=True)
    out = os.path.join(ROOT, "po", f"{DOMAIN}.pot")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(
            'msgid ""\nmsgstr ""\n'
            '"Project-Id-Version: Screen Translation\\n"\n'
            '"MIME-Version: 1.0\\n"\n'
            '"Content-Type: text/plain; charset=UTF-8\\n"\n'
            '"Content-Transfer-Encoding: 8bit\\n"\n\n'
        )
        for text, locations in messages.items():
            for location in locations:
                fh.write(f"#: {location}\n")
            fh.write(f"msgid {_quote(text)}\nmsgstr \"\"\n\n")
    return out


def _quote(text):
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _unquote(chunk):
    """Undo the escaping done by _quote."""
    out, escaped = [], False
    for ch in chunk:
        if escaped:
            out.append({"n": "\n", "t": "\t"}.get(ch, ch))
            escaped = False
        elif ch == "\\":
            escaped = True
        else:
            out.append(ch)
    return "".join(out)


def parse_po(path):
    """Minimal .po reader, including strings continued across lines."""
    entries, key, value, field = {}, None, None, None

    def flush():
        # The entry with an empty msgid carries the header, and gettext needs
        # it to learn the charset — without it everything is assumed ASCII.
        if key is not None and value:
            entries[key] = value

    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("msgid "):
            flush()
            key, value, field = _unquote(line[6:].strip()[1:-1]), "", "id"
        elif line.startswith("msgstr "):
            value, field = _unquote(line[7:].strip()[1:-1]), "str"
        elif line.startswith('"'):
            piece = _unquote(line[1:-1])
            if field == "id":
                key += piece
            elif field == "str":
                value += piece
    flush()
    return entries


def write_mo(entries, out_path):
    """Write a binary catalogue in the GNU gettext .mo format."""
    keys = sorted(entries)
    ids = b"\x00".join(k.encode("utf-8") for k in keys)
    strs = b"\x00".join(entries[k].encode("utf-8") for k in keys)

    count = len(keys)
    start = 7 * 4 + 16 * count
    offsets, id_offset, str_offset = [], 0, 0
    for key in keys:
        encoded = key.encode("utf-8")
        translated = entries[key].encode("utf-8")
        offsets.append((len(encoded), start + id_offset,
                        len(translated), start + len(ids) + 1 + str_offset))
        id_offset += len(encoded) + 1
        str_offset += len(translated) + 1

    output = struct.pack("Iiiiiii", 0x950412DE, 0, count, 7 * 4,
                         7 * 4 + count * 8, 0, 0)
    output += b"".join(struct.pack("ii", length, offset)
                       for length, offset, _l, _o in offsets)
    output += b"".join(struct.pack("ii", length, offset)
                       for _l, _o, length, offset in offsets)
    output += ids + b"\x00" + strs + b"\x00"

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(output)


def compile_all():
    built = []
    po_dir = os.path.join(ROOT, "po")
    for name in sorted(os.listdir(po_dir)):
        if not name.endswith(".po"):
            continue
        language = name[:-3]
        entries = parse_po(os.path.join(po_dir, name))
        out = os.path.join(ROOT, "locale", language, "LC_MESSAGES", f"{DOMAIN}.mo")
        write_mo(entries, out)
        built.append((language, len(entries), out))
    return built


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "extract"
    if command == "extract":
        found = extract()
        print(f"{len(found)} strings -> {write_pot(found)}")
    elif command == "compile":
        for language, count, path in compile_all():
            print(f"{language}: {count} strings -> {os.path.relpath(path, ROOT)}")
    else:
        print(__doc__)
        sys.exit(1)
