import argparse
import base64
import html.entities
import hashlib
import mimetypes
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


DEFAULT_INPUT = Path("./notes/evernote-html")
DEFAULT_OUTPUT_DIR = Path("./notes/evernote-md")
XML_DECL_RE = re.compile(r"<\?xml[^>]*\?>", re.IGNORECASE)
DOCTYPE_RE = re.compile(r"<!DOCTYPE[^>]*>", re.IGNORECASE)
INVALID_FILENAME_RE = re.compile(r'[\\/:*?"<>|\0\n\r\t]+')
WHITESPACE_RE = re.compile(r"\s+")
HTML_ENTITY_RE = re.compile(r"&([A-Za-z][A-Za-z0-9]+);")
XML_ENTITIES = {"amp", "lt", "gt", "apos", "quot"}


@dataclass
class ResourceFile:
    digest: str
    filename: str
    mime: str
    relative_path: str


@dataclass
class ConvertResult:
    note_count: int
    resource_count: int
    notebooks: list[tuple[str, int]]


def safe_filename(value, fallback="Untitled", max_length=120):
    value = INVALID_FILENAME_RE.sub("_", value or "").strip(" .")
    if not value:
        value = fallback
    if len(value) > max_length:
        value = value[:max_length].rstrip(" .")
    return value or fallback


def unique_name(filename, used_names):
    path = Path(filename)
    stem = path.stem
    suffix = path.suffix
    candidate = filename
    index = 2

    while candidate in used_names:
        candidate = f"{stem}-{index}{suffix}"
        index += 1

    used_names.add(candidate)
    return candidate


def markdown_link_path(path):
    return quote(path.replace("\\", "/"), safe="/._-~()")


def local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def parse_evernote_date(value):
    if not value:
        return ""

    try:
        parsed = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc
        )
        return parsed.isoformat().replace("+00:00", "Z")
    except ValueError:
        return value


def clean_inline_text(value):
    if not value:
        return ""
    return WHITESPACE_RE.sub(" ", value)


def strip_enml_wrappers(enml):
    enml = XML_DECL_RE.sub("", enml or "")
    enml = DOCTYPE_RE.sub("", enml)
    return enml.strip()


def normalize_html_entities(source):
    def replace_entity(match):
        name = match.group(1)
        if name in XML_ENTITIES:
            return match.group(0)

        codepoint = html.entities.name2codepoint.get(name)
        if codepoint is None:
            return match.group(0)
        return f"&#{codepoint};"

    return HTML_ENTITY_RE.sub(replace_entity, source)


def parse_xmlish_file(path):
    source = Path(path).read_text(encoding="utf-8")
    source = normalize_html_entities(source)
    return ET.fromstring(source)


def extension_for_mime(mime):
    overrides = {
        "image/jpeg": ".jpg",
        "image/svg+xml": ".svg",
        "image/webp": ".webp",
        "application/octet-stream": ".bin",
    }
    return overrides.get(mime) or mimetypes.guess_extension(mime or "") or ".bin"


def resource_filename(resource, digest, used_resource_names):
    attributes = resource.find("resource-attributes")
    original_name = ""
    if attributes is not None:
        original_name = attributes.findtext("file-name") or ""

    mime = resource.findtext("mime") or "application/octet-stream"
    if original_name:
        filename = safe_filename(original_name, fallback=f"resource-{digest[:8]}")
    else:
        filename = f"resource-{digest[:8]}{extension_for_mime(mime)}"

    return unique_name(filename, used_resource_names)


def write_resources(note, resource_dir, note_resource_root):
    resources = {}
    used_resource_names = set()
    resource_count = 0

    for resource in note.findall("resource"):
        encoded = "".join((resource.findtext("data") or "").split())
        if not encoded:
            continue

        data = base64.b64decode(encoded)
        digest = hashlib.md5(data).hexdigest()
        filename = resource_filename(resource, digest, used_resource_names)
        resource_path = resource_dir / filename
        resource_path.parent.mkdir(parents=True, exist_ok=True)
        resource_path.write_bytes(data)

        mime = resource.findtext("mime") or "application/octet-stream"
        resources[digest] = ResourceFile(
            digest=digest,
            filename=filename,
            mime=mime,
            relative_path=f"{note_resource_root}/{filename}",
        )
        resource_count += 1

    return resources, resource_count


def render_children(element, resources, list_level=0, preserve=False):
    pieces = []
    if element.text:
        pieces.append(element.text if preserve else clean_inline_text(element.text))

    for child in element:
        pieces.append(render_element(child, resources, list_level, preserve))
        if child.tail:
            pieces.append(child.tail if preserve else clean_inline_text(child.tail))

    return "".join(pieces)


def render_list(element, resources, ordered, list_level):
    lines = []
    item_index = 1

    for child in element:
        child_name = local_name(child.tag)
        if child_name in {"ol", "ul"}:
            lines.append(
                render_list(child, resources, child_name == "ol", list_level + 1).rstrip()
            )
            continue
        if child_name != "li":
            continue

        marker = f"{item_index}. " if ordered else "- "
        body = render_children(child, resources, list_level + 1).strip()
        body_lines = body.splitlines() or [""]
        indent = "  " * list_level
        lines.append(f"{indent}{marker}{body_lines[0].strip()}")

        for continuation in body_lines[1:]:
            if continuation.strip():
                lines.append(f"{indent}  {continuation.rstrip()}")
            else:
                lines.append("")

        item_index += 1

    return "\n".join(lines) + "\n\n"


def render_table(element, resources):
    rows = []

    for row in element.iter():
        if local_name(row.tag) != "tr":
            continue

        cells = []
        for cell in row:
            if local_name(cell.tag) not in {"td", "th"}:
                continue
            text = render_children(cell, resources).strip().replace("|", "\\|")
            cells.append(text)

        if cells:
            rows.append(cells)

    if not rows:
        return ""

    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    output = [
        "| " + " | ".join(rows[0]) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    output.extend("| " + " | ".join(row) + " |" for row in rows[1:])
    return "\n".join(output) + "\n\n"


def render_media(element, resources):
    digest = (element.attrib.get("hash") or "").lower()
    resource = resources.get(digest)
    if resource is None:
        return ""

    link = markdown_link_path(resource.relative_path)
    if resource.mime.startswith("image/"):
        return f"![{resource.filename}]({link})"
    return f"[{resource.filename}]({link})"


def render_image(element, resources):
    src = element.attrib.get("src", "")
    if not src:
        return ""

    alt = element.attrib.get("alt") or Path(src).name
    return f"![{alt}]({src})"


def render_element(element, resources, list_level=0, preserve=False):
    tag = local_name(element.tag)

    if tag == "br":
        return "\n"
    if tag == "img":
        return render_image(element, resources)
    if tag == "en-media":
        return render_media(element, resources)
    if tag == "en-crypt":
        hint = element.attrib.get("hint")
        if hint:
            return f"\n\n> [Encrypted content. Hint: {hint}]\n\n"
        return "\n\n> [Encrypted content. Decrypt it in Evernote/Yinxiang first.]\n\n"
    if tag == "en-todo":
        checked = element.attrib.get("checked", "false").lower() == "true"
        return "[x] " if checked else "[ ] "
    if tag in {"strong", "b"}:
        body = render_children(element, resources, list_level).strip()
        return f"**{body}**" if body else ""
    if tag in {"em", "i"}:
        body = render_children(element, resources, list_level).strip()
        return f"*{body}*" if body else ""
    if tag in {"s", "strike"}:
        body = render_children(element, resources, list_level).strip()
        return f"~~{body}~~" if body else ""
    if tag == "code":
        body = render_children(element, resources, list_level).strip()
        return f"`{body}`" if body else ""
    if tag == "pre":
        return "```\n" + render_children(element, resources, list_level, True) + "\n```\n\n"
    if tag == "a":
        text = render_children(element, resources, list_level).strip()
        href = element.attrib.get("href", "")
        if href:
            return f"[{text or href}]({href})"
        return text
    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        level = int(tag[1])
        return f"{'#' * level} {render_children(element, resources, list_level).strip()}\n\n"
    if tag in {"p", "div"}:
        body = render_children(element, resources, list_level).strip()
        return f"{body}\n\n" if body else "\n"
    if tag == "blockquote":
        body = render_children(element, resources, list_level).strip()
        return "\n".join(f"> {line}" for line in body.splitlines()) + "\n\n"
    if tag == "ul":
        return render_list(element, resources, False, list_level)
    if tag == "ol":
        return render_list(element, resources, True, list_level)
    if tag == "table":
        return render_table(element, resources)

    return render_children(element, resources, list_level, preserve)


def enml_to_markdown(enml, resources):
    source = strip_enml_wrappers(enml)
    if not source:
        return ""
    if source.startswith("RU5D"):
        return "> [Encrypted content. Export HTML from Evernote/Yinxiang to convert readable text.]"

    try:
        root = ET.fromstring(source)
    except ET.ParseError:
        return re.sub(r"<[^>]+>", "", source).strip()

    return render_children(root, resources).strip()


def note_markdown(note, notebook_name, resources):
    title = note.findtext("title") or "Untitled"
    created = parse_evernote_date(note.findtext("created"))
    updated = parse_evernote_date(note.findtext("updated"))
    tags = [tag.text for tag in note.findall("tag") if tag.text]
    body = enml_to_markdown(note.findtext("content") or "", resources)

    metadata = [f"# {title}", ""]
    metadata.append(f"- Notebook: {notebook_name}")
    if created:
        metadata.append(f"- Created: {created}")
    if updated:
        metadata.append(f"- Updated: {updated}")
    if tags:
        metadata.append(f"- Tags: {', '.join(tags)}")
    metadata.extend(["", "---", ""])

    return "\n".join(metadata) + body + "\n"


def convert_enex_file(enex_file, output_root):
    root = ET.parse(enex_file).getroot()
    notebook_name = enex_file.stem
    notebook_dir = output_root / safe_filename(notebook_name, fallback="Notebook")
    notebook_dir.mkdir(parents=True, exist_ok=True)

    used_note_names = set()
    note_count = 0
    resource_count = 0

    for note in root.findall("note"):
        title = note.findtext("title") or "Untitled"
        note_filename = unique_name(
            safe_filename(title, fallback="Untitled") + ".md", used_note_names
        )
        note_stem = Path(note_filename).stem
        resource_root = f"resources/{note_stem}"
        resource_dir = notebook_dir / resource_root
        resources, written_resources = write_resources(note, resource_dir, resource_root)

        markdown = note_markdown(note, notebook_name, resources)
        (notebook_dir / note_filename).write_text(markdown, encoding="utf-8")

        note_count += 1
        resource_count += written_resources

    return note_count, resource_count


def first_descendant(root, tag_name):
    for element in root.iter():
        if local_name(element.tag) == tag_name:
            return element
    return None


def html_meta(root):
    result = {}
    for element in root.iter():
        if local_name(element.tag) != "meta":
            continue
        name = element.attrib.get("name")
        content = element.attrib.get("content")
        if name and content:
            result[name] = content
    return result


def html_title(root, fallback):
    title = first_descendant(root, "title")
    if title is not None and title.text:
        return title.text
    return fallback


def html_note_markdown(html_file, notebook_name):
    root = parse_xmlish_file(html_file)
    title = html_title(root, html_file.stem)
    metadata = html_meta(root)
    body = first_descendant(root, "body")
    body_markdown = render_children(body, {}) if body is not None else ""

    frontmatter = [f"# {title}", "", f"- Notebook: {notebook_name}"]
    if metadata.get("created"):
        frontmatter.append(f"- Created: {metadata['created']}")
    if metadata.get("updated"):
        frontmatter.append(f"- Updated: {metadata['updated']}")
    if metadata.get("source-url"):
        frontmatter.append(f"- Source: {metadata['source-url']}")
    frontmatter.extend(["", "---", ""])

    return "\n".join(frontmatter) + body_markdown.strip() + "\n"


def copy_html_resources(html_file, notebook_dir, markdown_stem):
    resource_dir = html_file.with_suffix(".resources")
    if not resource_dir.exists():
        return 0

    target_dir = notebook_dir / f"{markdown_stem}.resources"
    shutil.copytree(resource_dir, target_dir, dirs_exist_ok=True)
    return sum(1 for path in target_dir.rglob("*") if path.is_file())


def convert_html_file(html_file, output_root, notebook_name=None, used_names=None):
    if used_names is None:
        used_names = set()
    if notebook_name is None:
        notebook_name = html_file.parent.stem

    notebook_dir = output_root / safe_filename(notebook_name, fallback="Notebook")
    notebook_dir.mkdir(parents=True, exist_ok=True)

    markdown_name = unique_name(
        safe_filename(html_file.stem, fallback="Untitled") + ".md", used_names
    )
    markdown_stem = Path(markdown_name).stem
    markdown = html_note_markdown(html_file, notebook_name)
    (notebook_dir / markdown_name).write_text(markdown, encoding="utf-8")
    resource_count = copy_html_resources(html_file, notebook_dir, markdown_stem)

    return 1, resource_count


def find_html_files(input_path):
    if input_path.is_file() and input_path.suffix.lower() in {".html", ".htm"}:
        return [input_path]

    files = []
    for html_file in sorted(input_path.rglob("*.html")):
        if not html_file.is_file():
            continue
        if html_file.name == "index.html":
            continue
        if ".resources" in html_file.parts:
            continue
        files.append(html_file)
    return files


def convert_html_export(input_path, output_root):
    html_files = find_html_files(input_path)
    if not html_files:
        raise FileNotFoundError(f"no exported .html notes found: {input_path}")

    used_by_notebook = {}
    total_notes = 0
    total_resources = 0
    notebook_counts = {}

    for html_file in html_files:
        notebook_name = html_file.parent.stem
        used_names = used_by_notebook.setdefault(notebook_name, set())
        note_count, resource_count = convert_html_file(
            html_file, output_root, notebook_name, used_names
        )
        total_notes += note_count
        total_resources += resource_count
        notebook_counts[notebook_name] = notebook_counts.get(notebook_name, 0) + note_count

    return ConvertResult(
        note_count=total_notes,
        resource_count=total_resources,
        notebooks=sorted(notebook_counts.items()),
    )


def find_enex_files(input_path):
    if input_path.is_file():
        return [input_path]
    return sorted(input_path.glob("*.enex"))


def convert_path(input_path, output_dir):
    input_path = Path(input_path).expanduser()
    output_root = Path(output_dir).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)

    if input_path.is_file() and input_path.suffix.lower() in {".html", ".htm"}:
        return convert_html_export(input_path, output_root)

    if input_path.is_dir() and find_html_files(input_path):
        return convert_html_export(input_path, output_root)

    enex_files = find_enex_files(input_path)
    if not enex_files:
        raise FileNotFoundError(f"no .enex files found: {input_path}")

    total_notes = 0
    total_resources = 0
    notebooks = []

    for enex_file in enex_files:
        note_count, resource_count = convert_enex_file(enex_file, output_root)
        total_notes += note_count
        total_resources += resource_count
        notebooks.append((enex_file.stem, note_count))

    return ConvertResult(
        note_count=total_notes,
        resource_count=total_resources,
        notebooks=notebooks,
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert Evernote/Yinxiang HTML or ENEX exports into Markdown files."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=str(DEFAULT_INPUT),
        help="An HTML export directory/file, ENEX file, or directory containing .enex files. Default: ./notes/evernote-html",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Markdown output directory. Default: ./notes/evernote-md",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        result = convert_path(args.input, args.output_dir)
    except (OSError, ET.ParseError, ValueError) as exc:
        print(f"转换失败：{exc}")
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve()
    print(f"已转换 {result.note_count} 条笔记到 {output_dir}")
    print(f"已写出 {result.resource_count} 个附件")
    for notebook, note_count in result.notebooks:
        print(f"- {notebook}: {note_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
