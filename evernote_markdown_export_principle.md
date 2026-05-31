# 印象笔记导出为可读 Markdown 的方案原理

## 背景问题

macOS 印象笔记支持通过 AppleScript 导出笔记。最自然的第一步是把每个笔记本导出成 ENEX 文件，然后解析 ENEX 里的 ENML 内容，再转换成 Markdown。

但在印象笔记 9.x 的实际导出结果中，ENEX 的正文并不一定是明文 ENML。很多笔记的 `<content>` 节点会出现类似下面的形式：

```xml
<content encoding="base64:aes">RU5D...</content>
```

这里的 `RU5D...` 不是普通的笔记正文，而是经过 `base64:aes` 包装后的加密内容。直接离线解析 ENEX 时，只能读到密文，无法恢复成可读文本。因此直接从 ENEX 转 Markdown 会得到一大段不可读内容。

## 核心思路

方案改为两阶段处理：

1. 让印象笔记客户端自己导出 HTML。
2. 再把导出的 HTML 文件转换成 Markdown。

原因是印象笔记客户端在导出 HTML 时，会在应用内部完成正文解密和资源展开。导出的 HTML 已经是可读内容，因此后续转换脚本只需要处理普通 HTML 结构、图片和附件引用，不需要破解或复现印象笔记的加密逻辑。

整体流程如下：

```text
印象笔记 App
    |
    | AppleScript 导出 HTML
    v
notes/evernote-html/
    |
    | enex_to_markdown.py 解析 HTML
    v
notes/evernote-md/
```

## 为什么不继续解析 ENEX

ENEX 仍然适合作为备份格式，但不适合作为本次 Markdown 转换的主输入，原因有三个：

1. ENEX 正文可能是 `base64:aes` 加密内容，离线脚本无法直接得到明文。
2. 同一个 ENEX 文件中，附件和正文结构更偏向应用迁移，不是面向人直接阅读。
3. 即使保留 ENEX，也还需要额外处理 ENML、资源哈希、MIME 类型和附件落盘，复杂度更高。

所以当前策略是：

- ENEX：保留为备份或迁移格式。
- HTML：作为转换 Markdown 的主输入。
- Markdown：作为最终可读、可搜索、可迁移的个人笔记格式。

## 实现方式

### 1. 导出 HTML

使用 `evernote_exporter.py` 调用印象笔记的 AppleScript 导出能力：

```bash
python3 evernote_exporter.py --format html -o notes/evernote-html
```

脚本会按笔记本导出内容。印象笔记会生成类似这样的目录结构：

```text
notes/evernote-html/
  某个笔记本.html/
    某条笔记.html
    某条笔记.resources/
      image.png
      attachment.pdf
```

其中 `.html` 文件是已解密、可阅读的正文，`.resources` 目录保存图片和附件。

### 2. 转换 Markdown

使用 `enex_to_markdown.py` 读取 HTML 导出目录：

```bash
python3 enex_to_markdown.py
```

默认输入目录是：

```text
notes/evernote-html/
```

默认输出目录是：

```text
notes/evernote-md/
```

转换时会做这些事情：

1. 递归扫描 HTML 导出目录。
2. 跳过 `index.html` 和 `.resources` 资源目录。
3. 将每个 HTML 文件转换为一个 `.md` 文件。
4. 按笔记本名称创建 Markdown 子目录。
5. 把同名 `.resources` 目录复制到对应 Markdown 文件旁边。
6. 把图片、链接、标题、段落、列表、表格、代码块等常见结构转换成 Markdown。

最终结构类似：

```text
notes/evernote-md/
  某个笔记本/
    某条笔记.md
    某条笔记.resources/
      image.png
      attachment.pdf
```

## 关键处理点

### 文件名清理

笔记本名和笔记标题可能包含文件系统不友好的字符。脚本会清理文件名，避免 `/`、控制字符或过长文件名导致写入失败。

### 附件保留

图片和附件不会内嵌到 Markdown 中，而是保留为相邻资源目录。这样 Markdown 本身保持轻量，同时资源路径仍然可用。

示例：

```markdown
![图片](某条笔记.resources/image.png)
```

### HTML 容错解析

印象笔记导出的 HTML 可能包含 `&nbsp;` 等 XML 解析器不认识的 HTML 实体。转换脚本会先做一层实体规范化，再用结构化解析方式读取内容。

### ENEX 兼容保留

`enex_to_markdown.py` 仍保留 ENEX 输入能力，但对于带 `base64:aes` 的 ENEX 正文，只会输出提示，不会把密文直接写进 Markdown。实际可读 Markdown 建议始终从 HTML 导出转换。

## 当前验证结果

本次已经完成一次实际导出和转换：

```text
Markdown 文件数：829
附件文件数：960
输出目录：notes/evernote-md/
```

并检查过输出目录中没有以下加密残留：

```text
RU5D
ENC0
base64:aes
```

也就是说，当前保存下来的 Markdown 是从印象笔记 HTML 导出解析之后的可读版本，不再是 ENEX 密文内容。

## 后续复用命令

如果之后要重新导出并生成 Markdown，执行：

```bash
python3 evernote_exporter.py --format html -o notes/evernote-html
python3 enex_to_markdown.py
```

如果只想重新转换已有 HTML，不重新控制印象笔记导出，只需要执行：

```bash
python3 enex_to_markdown.py
```

