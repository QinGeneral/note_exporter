import base64
import hashlib
import tempfile
import unittest
from pathlib import Path

from enex_to_markdown import convert_path, enml_to_markdown


class EnexToMarkdownTest(unittest.TestCase):
    def test_enml_to_markdown_renders_common_tags(self):
        markdown = enml_to_markdown(
            """<?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">
            <en-note><div>Hello <b>world</b><br/><en-todo checked="true"/>done</div></en-note>""",
            {},
        )

        self.assertIn("Hello **world**", markdown)
        self.assertIn("[x] done", markdown)

    def test_convert_path_writes_markdown_and_resources(self):
        data = b"fake png data"
        digest = hashlib.md5(data).hexdigest()
        encoded = base64.b64encode(data).decode("ascii")

        enex = f"""<?xml version="1.0" encoding="UTF-8"?>
<en-export>
  <note>
    <title>Sample/Title</title>
    <content><![CDATA[<?xml version="1.0" encoding="UTF-8"?>
      <!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">
      <en-note><div>Hello <en-media type="image/png" hash="{digest}"/></div></en-note>]]></content>
    <created>20240101T010203Z</created>
    <updated>20240102T030405Z</updated>
    <tag>tag-a</tag>
    <resource>
      <data encoding="base64">{encoded}</data>
      <mime>image/png</mime>
      <resource-attributes><file-name>image.png</file-name></resource-attributes>
    </resource>
  </note>
</en-export>"""

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_file = tmp_path / "Notebook.enex"
            output_dir = tmp_path / "markdown"
            input_file.write_text(enex, encoding="utf-8")

            result = convert_path(input_file, output_dir)

            self.assertEqual(result.note_count, 1)
            self.assertEqual(result.resource_count, 1)

            markdown_file = output_dir / "Notebook" / "Sample_Title.md"
            markdown = markdown_file.read_text(encoding="utf-8")
            self.assertIn("# Sample/Title", markdown)
            self.assertIn("- Tags: tag-a", markdown)
            self.assertIn("![image.png](resources/Sample_Title/image.png)", markdown)
            self.assertEqual(
                (output_dir / "Notebook" / "resources" / "Sample_Title" / "image.png").read_bytes(),
                data,
            )

    def test_convert_path_writes_markdown_from_html_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            notebook_dir = tmp_path / "Notebook.html"
            resource_dir = notebook_dir / "Readable.resources"
            output_dir = tmp_path / "markdown"
            resource_dir.mkdir(parents=True)
            (resource_dir / "image.png").write_bytes(b"image")
            (notebook_dir / "Readable.html").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
                <html>
                  <head>
                    <meta name="created" content="2024-01-01 01:02:03 +0000"/>
                    <title>Readable</title>
                  </head>
                  <body>
                    <div><b>Hello</b> world</div>
                    <div><img src="Readable.resources/image.png"/></div>
                  </body>
                </html>""",
                encoding="utf-8",
            )

            result = convert_path(tmp_path, output_dir)

            self.assertEqual(result.note_count, 1)
            markdown = (output_dir / "Notebook" / "Readable.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("**Hello** world", markdown)
            self.assertIn("![image.png](Readable.resources/image.png)", markdown)
            self.assertEqual(
                (output_dir / "Notebook" / "Readable.resources" / "image.png").read_bytes(),
                b"image",
            )


if __name__ == "__main__":
    unittest.main()
