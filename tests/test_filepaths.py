"""Browser URL regressions, including Windows paths on every host."""
import sys
import unittest
from pathlib import Path, PureWindowsPath, PurePosixPath
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'workers'))
from filepaths import file_uri


class FileUriTests(unittest.TestCase):
    def test_windows_extended_drive(self):
        path = PureWindowsPath('C:/中文 dir/a#b.html')
        extended = PureWindowsPath('\\\\?\\' + str(path))
        self.assertEqual(file_uri(extended), path.as_uri())
        self.assertTrue(file_uri(extended).startswith('file:///C:/'))

    def test_windows_extended_unc(self):
        path = PureWindowsPath('//server/share/中文/a.html')
        extended = PureWindowsPath('\\\\?\\UNC\\server\\share\\中文\\a.html')
        self.assertEqual(file_uri(extended), path.as_uri())

    def test_posix(self):
        path = PurePosixPath('/tmp/中文 dir/a#b.html')
        self.assertEqual(file_uri(path), path.as_uri())


if __name__ == '__main__':
    unittest.main()
