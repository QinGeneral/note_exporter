The goal of this project is to export all notes and attachments in the note software without requiring membership functions.

## Export

### Bear

![](./icon/bear.png)

To export all notes and attachments in Bear software, simply execute the following command:

```python
python bear_exporter.py
```

### Yinxiang/Evernote for macOS

To export all notes and attachments from the macOS Yinxiang app, run:

```python
python evernote_exporter.py
```

By default, notes are exported per notebook to `./notes/evernote/*.enex`. ENEX preserves note content, tags, and attachments, making it suitable for backups or imports into ENEX-compatible apps. HTML export is also available:

```python
python evernote_exporter.py --format html
```

macOS may ask you to allow Terminal or Codex to control Yinxiang on the first run. For the international Evernote app, pass its app name:

```python
python evernote_exporter.py --app Evernote
```

Yinxiang/Evernote 9.x may export ENEX note bodies with `base64:aes` encryption, which cannot be converted into readable Markdown offline. Export HTML first, then convert the decrypted HTML export into Markdown:

```python
python evernote_exporter.py --format html -o notes/evernote-html
```

```python
python enex_to_markdown.py
```

By default, this reads `./notes/evernote-html/` and writes notebooks to `./notes/evernote-md/`. Each note becomes one `.md` file, and images/attachments are saved in a `.resources/` directory next to the note.
