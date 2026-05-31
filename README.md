For English README, Click [here](./README-en.md).

本项目目标是导出笔记软件中的所有笔记 + 附件，而无需会员功能。

## 导出

### 熊掌记 Bear

![](./icon/bear.png)

导出熊掌记 Bear 软件中的所有笔记和附件，执行以下命令即可：

```python
python bear_exporter.py
```

### 印象笔记 macOS

导出 macOS 印象笔记中的所有笔记和附件，执行以下命令即可：

```python
python evernote_exporter.py
```

默认会按笔记本导出为 `./notes/evernote/*.enex`。ENEX 会保留笔记内容、标签和附件，适合备份或导入其他支持 ENEX 的应用。也可以导出 HTML：

```python
python evernote_exporter.py --format html
```

首次运行时，macOS 可能会要求允许终端或 Codex 控制印象笔记。若使用国际版 Evernote，可指定应用名称：

```python
python evernote_exporter.py --app Evernote
```

印象笔记 9.x 导出的 ENEX 正文可能会带 `base64:aes` 加密，直接转 ENEX 会得到不可读密文。建议先导出 HTML，再把 HTML 转为可直接阅读的 Markdown：

```python
python evernote_exporter.py --format html -o notes/evernote-html
```

```python
python enex_to_markdown.py
```

默认会读取 `./notes/evernote-html/`，并按笔记本输出到 `./notes/evernote-md/`。每条笔记会变成一个 `.md` 文件，图片和附件会保存在笔记旁边的 `.resources/` 目录。
