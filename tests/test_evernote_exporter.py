import unittest
from pathlib import Path

from evernote_exporter import build_export_script, parse_export_output


class EvernoteExporterTest(unittest.TestCase):
    def test_parse_export_output(self):
        result = parse_export_output(
            "3\n2\tInbox\t/tmp/evernote/Inbox.enex\n1\tWork\t/tmp/evernote/Work.enex\n"
        )

        self.assertEqual(result.total_notes, 3)
        self.assertEqual(len(result.notebooks), 2)
        self.assertEqual(result.notebooks[0].note_count, 2)
        self.assertEqual(result.notebooks[0].name, "Inbox")
        self.assertEqual(result.notebooks[0].path, Path("/tmp/evernote/Inbox.enex"))

    def test_build_export_script_uses_app_name(self):
        script = build_export_script("印象笔记")

        self.assertIn('tell application "印象笔记"', script)
        self.assertIn("on fileForPath(posixPath)", script)
        self.assertIn("set exportFile to my fileForPath(exportPath)", script)
        self.assertIn("«constant Exffenex»", script)
        self.assertIn("«constant Exffexht»", script)

    def test_build_export_script_escapes_app_name(self):
        script = build_export_script('Bad"Name')

        self.assertIn('tell application "Bad\\"Name"', script)


if __name__ == "__main__":
    unittest.main()
