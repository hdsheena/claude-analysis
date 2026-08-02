"""Extract Claude Code built-in slash commands from the native claude binary.

Usage:
    python3 extract_commands.py [--binary /path/to/claude] [--out OUT_DIR]

Reads the minified JS bundle embedded in the claude binary, finds every
built-in command object (type:"local" / type:"local-jsx" / type:"prompt"), pulls
out its name, aliases, description, argument hint, and availability flags, then
writes one markdown file per command into OUT_DIR/commands/ plus a summary
OUT_DIR/README.md.
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

NAME_RE = re.compile(r'name:"([a-z0-9:-]+)"')
DESC_LIT_RE = re.compile(r'description:"((?:[^"\\]|\\.)*)"')
DESC_TEMPLATE_RE = re.compile(r'get description\(\)\{return`([^`]*)`')
DESC_COND_RE = re.compile(r'get description\(\)\{return[^?]*\?"((?:[^"\\]|\\.)*)":"((?:[^"\\]|\\.)*)"')
DESC_CALL_RE = re.compile(r'get description\(\)\{return\s*(\w+)\(\)')
DESC_RAW_GETTER_RE = re.compile(r'get description\(\)\{(.{0,300}?)\}')
ALIASES_RE = re.compile(r'aliases:\[([^\]]*)\]')
ARG_LIT_RE = re.compile(r'argumentHint:"((?:[^"\\]|\\.)*)"')
ARG_TPL_RE = re.compile(r'argumentHint:`([^`]*)`')
ARG_TPL_GET_RE = re.compile(r'get argumentHint\(\)\{return`([^`]*)`')
ARG_COND_GET_RE = re.compile(r'get argumentHint\(\)\{return[^?]*\?"((?:[^"\\]|\\.)*)"')
AVAIL_RE = re.compile(r'availability:\[([^\]]*)\]')


def decode_escapes(text):
    out = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), text)
    out = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), out)
    out = out.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')
    return out


def strip_dynamic(text, source):
    def replace(match):
        inner = match.group(1)
        m = re.fullmatch(r'(\w+)\(\)', inner)
        if m:
            return function_return(m.group(1), source, 0)
        return "{dynamic}"

    return re.sub(r'\$\{([^}]*)\}', replace, text)


def best_of_strings(body):
    strings = []
    for raw in re.findall(r'"((?:[^"\\]|\\.)*)"', body):
        decoded = decode_escapes(raw)
        if decoded and decoded not in strings:
            strings.append(decoded)
    return max(strings, key=len) if strings else None


def function_return(name, source, depth):
    if depth > 3:
        return "(dynamic)"
    m = re.search(r'function ' + re.escape(name) + r'\(\)\{return\s*', source)
    if not m:
        return f"(dynamic: {name}())"
    return parse_return(source, m.end(), depth)


def parse_return(source, pos, depth):
    body = source[pos:]
    if body.startswith('`'):
        end = body.find('`', 1)
        raw = body[1:end] if end != -1 else body[1:]
        return strip_dynamic(decode_escapes(raw), source)
    m = re.match(r'"((?:[^"\\]|\\.)*)"', body)
    if m:
        return decode_escapes(m.group(1))
    if '?' in body[:60]:
        m = re.search(r'\?"((?:[^"\\]|\\.)*)":"((?:[^"\\]|\\.)*)"', body[:200])
        if m:
            return decode_escapes(m.group(1)) + ' / ' + decode_escapes(m.group(2))
    m = re.match(r'(\w+)\(\)', body)
    if m:
        return function_return(m.group(1), source, depth + 1)
    strings = re.findall(r'"((?:[^"\\]|\\.)*)"', body[:160])
    if strings:
        return ' / '.join(decode_escapes(s) for s in strings)
    return "(dynamic)"


def extract_description(after, before, source):
    m = DESC_TEMPLATE_RE.search(after)
    if m:
        return strip_dynamic(decode_escapes(m.group(1)), source)
    m = DESC_COND_RE.search(after)
    if m:
        return decode_escapes(m.group(1)) + ' / ' + decode_escapes(m.group(2))
    m = DESC_CALL_RE.search(after)
    if m:
        return function_return(m.group(1), source, 0)
    m = DESC_RAW_GETTER_RE.search(after)
    if m:
        resolved = best_of_strings(m.group(1))
        if resolved:
            return resolved
    m = DESC_LIT_RE.search(after)
    if m:
        return decode_escapes(m.group(1))
    m = DESC_LIT_RE.search(before)
    if m:
        return decode_escapes(m.group(1))
    return None


def extract_aliases(after, before):
    m = ALIASES_RE.search(after)
    if m:
        return re.findall(r'"([^"]*)"', m.group(1))
    m = ALIASES_RE.search(before)
    if m:
        return re.findall(r'"([^"]*)"', m.group(1))
    return []


def extract_argument(after, source):
    m = ARG_LIT_RE.search(after)
    if m:
        return decode_escapes(m.group(1))
    m = ARG_TPL_RE.search(after)
    if m:
        return strip_dynamic(m.group(1), source)
    m = ARG_TPL_GET_RE.search(after)
    if m:
        return strip_dynamic(m.group(1), source)
    m = ARG_COND_GET_RE.search(after)
    if m:
        return decode_escapes(m.group(1))
    return ""


def extract_availability(after):
    m = AVAIL_RE.search(after)
    if m:
        return re.findall(r'"([^"]*)"', m.group(1))
    return []


def extract_flag(after, key):
    m = re.search(key + r'(:|\(\)\{return\s*)([^,]{0,80})', after)
    if not m:
        return None
    value = m.group(2).strip().rstrip('}')
    if value == '!0':
        return "yes"
    if value == '!1':
        return "no"
    return value


@dataclass
class Command:
    name: str
    description: str = None
    aliases: list = field(default_factory=list)
    argument: str = ""
    availability: list = field(default_factory=list)
    hidden: str = None
    enabled: str = None
    immediate: str = None
    noninteractive: str = None
    snippet: str = ""


def regions_for(source, pos, name_positions):
    next_pos = min((p for p in name_positions if p > pos), default=len(source))
    after_end = min(pos + 500, next_pos)
    after = source[pos:after_end]
    prev_close = source.rfind('}', max(0, pos - 400), pos)
    before_start = prev_close + 1 if prev_close != -1 else max(0, pos - 260)
    before = source[before_start:pos]
    return after, before


def build_command(source, pos, name_positions):
    after, before = regions_for(source, pos, name_positions)
    cmd = Command(name="")
    cmd.name = NAME_RE.search(source[pos:]).group(1)
    cmd.description = extract_description(after, before, source)
    cmd.aliases = extract_aliases(after, before)
    cmd.argument = extract_argument(after, source)
    cmd.availability = extract_availability(after)
    cmd.hidden = extract_flag(after, 'isHidden')
    cmd.enabled = extract_flag(after, 'isEnabled')
    cmd.immediate = extract_flag(after, 'immediate')
    cmd.noninteractive = extract_flag(after, 'supportsNonInteractive')
    cmd.snippet = (before[-180:] + after[:340]).replace('\\', '\\\\')
    return cmd


def nearest_type_is_supported(source, pos):
    lo = max(0, pos - 300)
    back = re.finditer(r'type:"([^"]+)"', source[lo:pos])
    fwd = re.finditer(r'type:"([^"]+)"', source[pos:pos + 300])
    best = None
    last = None
    for m in back:
        last = m
    if last:
        best = (pos - (lo + last.start()), last.group(1))
    first = next(fwd, None)
    if first:
        dist = first.start()
        if best is None or dist < best[0]:
            best = (dist, first.group(1))
    if best is None:
        return False
    return best[1] in ("local", "local-jsx", "prompt")


def extract_commands(source):
    name_positions = [m.start() for m in NAME_RE.finditer(source)]
    candidates = {}
    for m in NAME_RE.finditer(source):
        name = m.group(1)
        pos = m.start()
        if not nearest_type_is_supported(source, pos):
            continue
        candidates.setdefault(name, []).append(pos)

    commands = []
    for name, positions in sorted(candidates.items()):
        if name == "stub":
            continue
        best = None
        for pos in positions:
            cmd = build_command(source, pos, name_positions)
            if best is None or (cmd.description and best.description is None):
                best = cmd
        commands.append(best)
    return commands


def write_command_files(commands, out_dir):
    cmd_dir = out_dir / "commands"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    for existing in cmd_dir.glob("*.md"):
        existing.unlink()
    for cmd in commands:
        aliases = ", ".join(f"/{a}" for a in cmd.aliases) or "—"
        availability = ", ".join(cmd.availability) or "—"
        lines = [
            f"# /{cmd.name}",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| Description | {cmd.description or '(none)'} |",
            f"| Aliases | {aliases} |",
            f"| Argument | {cmd.argument or '—'} |",
            f"| Availability | {availability} |",
            f"| Hidden | {cmd.hidden or 'no'} |",
            f"| Enabled | {cmd.enabled or 'yes'} |",
            f"| Immediate | {cmd.immediate or 'no'} |",
            f"| Non-interactive | {cmd.noninteractive or 'no'} |",
            "",
            "Extracted definition (raw snippet from the built-in command registry):",
            "",
            "```js",
            cmd.snippet,
            "```",
            "",
        ]
        (cmd_dir / f"{cmd.name}.md").write_text("\n".join(lines))


def write_readme(commands, binary, out_dir):
    lines = [
        "# Claude Code built-in slash commands",
        "",
        f"Extracted from `{binary}` using `extract_commands.py`. "
        "These are the commands baked into the Claude Code CLI itself — not "
        "plugins, skills, or project commands.",
        "",
        f"{len(commands)} commands. Each has a detail page in `commands/`.",
        "",
        "| Command | Aliases | Description |",
        "|---|---|---|",
    ]
    for cmd in commands:
        aliases = ", ".join(f"/{a}" for a in cmd.aliases)
        aliases = aliases or "—"
        desc = cmd.description or "*no description*"
        lines.append(f"| /{cmd.name} | {aliases} | {desc} |")
    lines += [
        "",
        "Notes:",
        "- Hidden commands are flagged in their detail pages; they are usually internal.",
        "- Descriptions containing `{dynamic}` are computed at runtime (e.g. include the current model or account state).",
        "- Extraction is heuristic — it parses the minified JS bundle in the binary, so regenerate with `python3 extract_commands.py` after a Claude Code update.",
    ]
    (out_dir / "README.md").write_text("\n".join(lines))


def main(argv):
    parser = argparse.ArgumentParser(description="Extract Claude Code built-in slash commands.")
    parser.add_argument("--binary", default="/opt/homebrew/bin/claude", help="Path to the claude binary.")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent), help="Output directory.")
    args = parser.parse_args(argv)

    binary_path = Path(args.binary)
    if not binary_path.exists():
        print(f"error: binary not found: {binary_path}", file=sys.stderr)
        return 1

    source = binary_path.read_bytes().decode("latin-1")
    commands = extract_commands(source)
    out_dir = Path(args.out)
    write_command_files(commands, out_dir)
    write_readme(commands, str(binary_path), out_dir)
    print(f"wrote {len(commands)} commands to {out_dir / 'commands'} and summary to {out_dir / 'README.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
