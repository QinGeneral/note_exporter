import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path


DEFAULT_APP_NAME = "印象笔记"
DEFAULT_OUTPUT_DIR = Path("./notes/evernote")
SUPPORTED_FORMATS = ("enex", "html")

APPLESCRIPT_TEMPLATE = r'''
on replaceText(sourceText, searchString, replacementString)
    set oldDelimiters to AppleScript's text item delimiters
    set AppleScript's text item delimiters to searchString
    set textItems to text items of sourceText
    set AppleScript's text item delimiters to replacementString
    set newText to textItems as text
    set AppleScript's text item delimiters to oldDelimiters
    return newText
end replaceText

on safePathComponent(rawName)
    set componentName to rawName as text
    set invalidCharacters to {":", "/", linefeed, return, tab}

    repeat with invalidCharacter in invalidCharacters
        set componentName to my replaceText(componentName, invalidCharacter as text, "_")
    end repeat

    if componentName is "" then
        set componentName to "Untitled"
    end if

    return componentName
end safePathComponent

on fileForPath(posixPath)
    return POSIX file posixPath
end fileForPath

on run argv
    set outputRoot to item 1 of argv
    set exportFormatName to item 2 of argv
    set includeTagsValue to ((item 3 of argv) is "1")
    set shouldSync to ((item 4 of argv) is "1")
    set syncTimeout to (item 5 of argv) as integer
    set fileExtension to exportFormatName
    set totalNotes to 0
    set reportLines to {}
    set usedPaths to {}

    tell application __APP_SPECIFIER__
        if shouldSync then
            synchronize
            set waitedSeconds to 0

            repeat while (isSynchronizing is true) and (waitedSeconds < syncTimeout)
                delay 1
                set waitedSeconds to waitedSeconds + 1
            end repeat
        end if

        set notebookList to notebooks

        repeat with currentNotebook in notebookList
            set notebookName to name of currentNotebook as text
            set noteList to notes of currentNotebook
            set noteCount to count of noteList

            if noteCount > 0 then
                set safeNotebookName to my safePathComponent(notebookName)
                set exportPath to outputRoot & "/" & safeNotebookName & "." & fileExtension
                set suffixNumber to 2

                repeat while usedPaths contains exportPath
                    set exportPath to outputRoot & "/" & safeNotebookName & "-" & (suffixNumber as text) & "." & fileExtension
                    set suffixNumber to suffixNumber + 1
                end repeat

                set end of usedPaths to exportPath
                set exportFile to my fileForPath(exportPath)

                -- The Evernote export term does not compile reliably in readable
                -- AppleScript, so call its Apple Event directly.
                if exportFormatName is "html" then
                    «event EVRNenxp» noteList given «class kfil»:exportFile, «class Exit»:includeTagsValue, «class Expf»:«constant Exffexht»
                else
                    «event EVRNenxp» noteList given «class kfil»:exportFile, «class Exit»:includeTagsValue, «class Expf»:«constant Exffenex»
                end if

                set totalNotes to totalNotes + noteCount
                set end of reportLines to ((noteCount as text) & tab & notebookName & tab & exportPath)
            end if
        end repeat
    end tell

    set oldDelimiters to AppleScript's text item delimiters
    set AppleScript's text item delimiters to linefeed
    set reportBody to reportLines as text
    set AppleScript's text item delimiters to oldDelimiters

    if reportBody is "" then
        return totalNotes as text
    end if

    return (totalNotes as text) & linefeed & reportBody
end run
'''


@dataclass
class NotebookExport:
    note_count: int
    name: str
    path: Path


@dataclass
class ExportResult:
    total_notes: int
    notebooks: list[NotebookExport]


def quote_applescript_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_export_script(app_name):
    return APPLESCRIPT_TEMPLATE.replace(
        "__APP_SPECIFIER__", quote_applescript_string(app_name)
    )


def parse_export_output(output):
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return ExportResult(total_notes=0, notebooks=[])

    total_notes = int(lines[0])
    notebooks = []

    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) != 3:
            continue

        note_count, notebook_name, export_path = parts
        notebooks.append(
            NotebookExport(
                note_count=int(note_count),
                name=notebook_name,
                path=Path(export_path),
            )
        )

    return ExportResult(total_notes=total_notes, notebooks=notebooks)


def format_osascript_error(error):
    detail = (error.stderr or error.stdout or "").strip()
    if detail:
        return detail
    return f"osascript exited with code {error.returncode}"


def export_notes(output_dir, export_format, include_tags, app_name, sync, sync_timeout):
    export_format = export_format.lower()
    if export_format not in SUPPORTED_FORMATS:
        raise ValueError(f"unsupported format: {export_format}")
    if sync_timeout < 0:
        raise ValueError("sync timeout must be greater than or equal to 0")

    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    script = build_export_script(app_name)
    args = [
        str(output_path),
        export_format,
        "1" if include_tags else "0",
        "1" if sync else "0",
        str(sync_timeout),
    ]

    try:
        completed = subprocess.run(
            ["osascript", "-e", script, *args],
            capture_output=True,
            check=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("macOS osascript command was not found") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(format_osascript_error(exc)) from exc

    return parse_export_output(completed.stdout)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export all notes from the macOS Yinxiang/Evernote app."
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for exported notebook files. Default: ./notes/evernote",
    )
    parser.add_argument(
        "--format",
        choices=SUPPORTED_FORMATS,
        default="enex",
        help="Export format. ENEX preserves exact note content and attachments.",
    )
    parser.add_argument(
        "--no-tags",
        action="store_true",
        help="Do not include tags in the exported files.",
    )
    parser.add_argument(
        "--app",
        default=DEFAULT_APP_NAME,
        help="macOS app name. Yinxiang default: 印象笔记; international app: Evernote.",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Ask the app to synchronize before exporting.",
    )
    parser.add_argument(
        "--sync-timeout",
        type=int,
        default=300,
        help="Maximum seconds to wait for synchronization when --sync is used.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the export configuration without opening the note app.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    output_path = Path(args.output_dir).expanduser()

    if args.dry_run:
        print("印象笔记导出配置：")
        print(f"应用名称：{args.app}")
        print(f"输出目录：{output_path}")
        print(f"导出格式：{args.format}")
        print(f"包含标签：{not args.no_tags}")
        print(f"导出前同步：{args.sync}")
        return 0

    try:
        result = export_notes(
            output_dir=output_path,
            export_format=args.format,
            include_tags=not args.no_tags,
            app_name=args.app,
            sync=args.sync,
            sync_timeout=args.sync_timeout,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"导出失败：{exc}")
        print("请确认印象笔记已安装并登录；首次运行时需要允许终端或 Codex 控制印象笔记。")
        return 1

    print(f"已导出 {result.total_notes} 条笔记到 {Path(args.output_dir).expanduser().resolve()}")
    for notebook in result.notebooks:
        print(f"- {notebook.name}: {notebook.note_count} -> {notebook.path}")

    if result.total_notes == 0:
        print("没有找到可导出的笔记，请确认本机印象笔记已经同步完成。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
