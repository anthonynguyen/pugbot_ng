import os
import pep8
import unittest


class TestCodeFormat(unittest.TestCase):
    def test_pep8(self):
        _basedir = os.path.dirname(os.path.abspath(__file__))
        _pkgdir = os.path.abspath(os.path.join(_basedir, '../pugbot_ng'))
        _pyfiles = [
            os.path.join(root, pyfile) for root, _, files in os.walk(_pkgdir)
            for pyfile in files
            if pyfile.endswith('.py')]

        style = pep8.StyleGuide(quiet=True)
        result = style.check_files(_pyfiles)
        self.assertEqual(result.total_errors, 0,
                         "Found code style errors (and warnings).")
