"""Offline regression suite."""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from table_extraction_claim_audit import phrases as p
from table_extraction_claim_audit.audit import audit, evidence, paragraphs
from table_extraction_claim_audit.__main__ import main

EXPECTED_POSITIVE = ('table extraction', 'extract tables', 'extracts tables', 'extracting tables', 'extract table', 'extracts table', 'extracting table', 'pdf table extraction', 'extract tables from pdf', 'extracts tables from pdf', 'extract tables from pdfs', 'extracts tables from pdfs', 'table extraction from pdf', 'table extraction from pdfs', 'extract tabular data', 'extracts tabular data', 'extracting tabular data', 'tabular data extraction', 'parse tables', 'parses tables', 'parsing tables', 'table parsing', 'pdf table parser', 'pdf table parsing', 'extract table data', 'extracts table data', 'extracting table data', 'table data extraction', 'read tables from pdf', 'reads tables from pdf', 'reading tables from pdf', 'convert pdf tables', 'converts pdf tables', 'pdf to table', 'pdf tables to csv', 'pdf tables to excel', 'pdf tables to dataframe', 'pdf table to dataframe', 'table detection', 'detect tables', 'detects tables', 'detecting tables', 'table finder', 'find tables', 'finds tables', 'finding tables', 'table recognition', 'pdf table recognition', 'extract pdf tables', 'extracts pdf tables')
EXPECTED_NEGATIVE = ('no table extraction', 'does not extract tables', 'does not extract table', 'does not support table extraction', 'without table extraction', 'no table parser', 'does not parse tables', 'no pdf table extraction', 'does not extract tables from pdf', 'does not support pdf table extraction', 'no table detection', 'does not detect tables', 'does not find tables', 'no tabular data extraction', 'does not extract tabular data', 'table extraction not supported', 'no pdf tables', 'does not read tables from pdf', 'no table recognition', 'does not extract table data', 'without pdf table extraction', 'no extract tables', 'does not do table extraction', 'does not perform table extraction')
EXPECTED_GENERIC = ('extract_table', 'extract_tables', 'find_table', 'find_tables', 'extract_pdf_table', 'extract_pdf_tables', 'read_pdf_table', 'read_pdf_tables', 'pdf_table_extraction', 'table_extraction', 'table_extractor', 'extract_tabular_data', 'tabular_data_extraction', 'parse_pdf_table', 'parse_pdf_tables', 'pdf_table_parser', 'pdf_table_reader', 'convert_pdf_table', 'convert_pdf_tables', 'extract_tables_from_pdf', 'detect_tables', 'table_detection', 'pdf_tables_to_dataframe', 'read_pdf_tables_to_dataframe')

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            try:
                code = main(list(args))
            except SystemExit as error:
                code = error.code
        return code, out.getvalue()

    def test_phrase_oracle(self):
        tree = ast.parse(Path(p.__file__).read_text())
        literals = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body
                    if isinstance(n, ast.Assign)}
        for name, expected in [('TABLEEXTRACTION', EXPECTED_POSITIVE),
                               ('NOTABLEEXTRACTION', EXPECTED_NEGATIVE),
                               ('GENERIC_NAMES', EXPECTED_GENERIC)]:
            self.assertEqual(literals[name], expected)
            self.assertEqual(len(literals[name]), len(set(literals[name])))
        self.assertEqual(tuple(map(len, [EXPECTED_POSITIVE, EXPECTED_NEGATIVE, EXPECTED_GENERIC])), (50,24,24))
        self.assertEqual(p.CAMELOT_NAMES, ('read_pdf',))
        self.assertEqual(p.TABULA_NAMES, ('read_pdf','convert_into'))
        self.assertEqual(p.PDFPLUMBER_NAMES, ('extract_table','extract_tables','find_table','find_tables'))
        self.assertEqual(p.FITZ_NAMES, ('find_tables',))

    def test_all_positive_phrases(self):
        for phrase in EXPECTED_POSITIVE:
            with self.subTest(phrase=phrase):
                self.write('README.md', phrase)
                self.assertEqual(audit(self.root)['findings'][0]['severity'], 'HIGH')

    def test_all_negative_phrases(self):
        self.write('app.py', 'x.extract_tables()')
        for phrase in EXPECTED_NEGATIVE:
            with self.subTest(phrase=phrase):
                self.write('README.md', phrase)
                result = audit(self.root)
                self.assertEqual(len(result['findings']), 1)
                self.assertEqual(result['findings'][0]['id'], 'documented-no-table-extraction-claim-false')

    def test_routes(self):
        sources = ['import camelot; camelot.read_pdf("x")',
                   'from camelot import read_pdf; read_pdf("x")',
                   'import tabula; tabula.read_pdf("x")',
                   'from tabula import read_pdf; read_pdf("x")',
                   'import tabula; tabula.convert_into("x", "y")',
                   'from tabula import convert_into; convert_into("x", "y")',
                   'from pdfplumber import extract_tables; extract_tables()',
                   'import fitz; page.find_tables()', 'import pymupdf; page.find_tables()',
                   'from fitz import find_tables; find_tables()',
                   'import camelot as c; c.read_pdf("x")',
                   'from tabula import convert_into as c; c("x", "y")',
                   'import camelot; c = camelot; c.read_pdf("x")',
                   'import camelot; with_alias = camelot.read_pdf; with_alias("x")',
                   'import tabula; f: object = tabula.read_pdf; f("x")']
        for name in p.PDFPLUMBER_NAMES:
            sources.append('import pdfplumber; page.' + name + '()')
        for name in EXPECTED_GENERIC:
            sources.extend(['x.' + name + '()', 'from other import ' + name + '; ' + name + '()'])
        for source in sources:
            with self.subTest(source=source):
                self.assertTrue(evidence(source))
        self.assertFalse(evidence('import camelot\nwith thing() as camelot: camelot.read_pdf("x")'))

    def test_non_evidence(self):
        sources = ['import ' + name for name in ['camelot','tabula','pdfplumber','fitz','pymupdf']]
        sources += ['read_pdf("x")', 'from other import read_pdf; read_pdf("x")',
                    'import pdfplumber; pdfplumber.open("x")', 'import fitz; fitz.open("x")',
                    'import pymupdf; pymupdf.open("x")',
                    'import pdfplumber; page.extract_text()', 'import pdfplumber; page.extract_words()',
                    'import pypdf; page.extract_text()', 'import PyPDF2; page.extract_text()',
                    'import pdfminer; page.extract_text()',
                    'import pytesseract; pytesseract.image_to_string(x)',
                    'import pandas; pandas.read_csv("x")', 'import pandas; pandas.read_excel("x")',
                    'import openpyxl; openpyxl.load_workbook("x")',
                    'import camelot; tables.export("x")', 'tables[0].df', 'table.extract()',
                    'import fitz; table.extract()', 'import pdfplumber; page.debug_tablefinder()',
                    'import tabula; tabula.convert_into_by_batch("x")',
                    'from unstructured import partition_pdf; partition_pdf("x")',
                    'converter.convert("x")', 'page.get_text("words")',
                    'import subprocess; subprocess.run(["camelot", "x"])',
                    'import subprocess; subprocess.run(["tabula-java", "x"])',
                    '"x.extract_table()"', '# x.extract_table()', 'x.extract_table',
                    'def broken(:', 'extract_table()',
                    'import camelot\ndef read_pdf(): pass\ncamelot.read_pdf("x")',
                    'from camelot import read_pdf as r\ndef r(): pass\nr("x")',
                    'def extract_table(): pass\nx.extract_table()',
                    'class X:\n def find_tables(self): pass\nx.find_tables()',
                    'import tabula\nclass tabula: pass\ntabula.read_pdf("x")',
                    'import camelot\ncamelot = other\ncamelot.read_pdf("x")',
                    'from camelot import read_pdf\nwith thing() as read_pdf: read_pdf("x")',
                    'import camelot\nasync def f():\n async with thing() as camelot: camelot.read_pdf("x")']
        for source in sources:
            with self.subTest(source=source):
                self.assertFalse(evidence(source))

    def test_good(self):
        self.write('README.md', 'Extract tables from PDF.')
        self.write('app.py', 'import camelot; camelot.read_pdf("x")')
        self.assertEqual(self.cli('audit', str(self.root))[0], 0)
        self.assertEqual(audit(self.root)['verdict'], 'PASS')

    def test_bad_json(self):
        self.write('README.md', 'Table extraction')
        code, output = self.cli('audit', str(self.root), '--json')
        self.assertEqual(code, 2)
        result = json.loads(output)
        self.assertEqual(result['verdict'], 'FAIL')
        self.assertEqual(result['findings'][0]['id'], 'documented-table-extraction-claim-false')
        self.assertEqual(result['findings'][0]['severity'], 'HIGH')
        self.assertTrue(result['findings'][0]['message'])

    def test_test_only(self):
        self.write('README.md', 'Table extraction')
        for path in ['tests/app.py', 'test_app.py', 'app_test.py']:
            with self.subTest(path=path):
                file = self.write(path, 'x.extract_tables()')
                self.assertEqual(audit(self.root)['findings'][0]['severity'], 'MEDIUM')
                self.assertEqual(self.cli('audit', str(self.root))[0], 0)
                self.assertEqual(self.cli('audit', str(self.root), '--fail-on', 'medium')[0], 2)
                file.unlink()

    def test_denial(self):
        self.write('README.md', "Doesn't extract tables")
        self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.write('app.py', 'x.extract_tables()')
        self.assertEqual(self.cli('audit', str(self.root))[0], 2)
        self.assertEqual(audit(self.root)['findings'][0]['severity'], 'HIGH')

    def test_no_claim(self):
        self.write('README.md', 'A useful utility.')
        self.write('app.py', 'x.extract_tables()')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')

    def test_fences_inline_normalization(self):
        for fence in ['```', '~~~', '   ````']:
            self.write('README.md', fence + '\nextract tables\n' + fence + '\nSafe.')
            self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.write('README.md', '`EXTRACT-TABLES`')
        self.assertEqual(audit(self.root)['verdict'], 'FAIL')
        self.assertEqual(paragraphs('table\n extraction\n\nSafe'), ['table extraction','safe'])
        self.write('README.md', 'extract tablesauce')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')

    def test_scope_exclusions(self):
        self.write('README.md', 'extract tables')
        self.write('a.py', 'import camelot')
        self.write('b.py', 'camelot.read_pdf("x")')
        for path in ['docs/a.py','fixtures/a.py','examples/a.py']:
            self.write(path, 'x.extract_tables()')
        self.assertEqual(audit(self.root)['findings'][0]['severity'], 'HIGH')
        self.write('nested/docs/guide.md', 'does not extract tables')
        self.write('ignored.md', 'extract tables')
        self.assertEqual(len(audit(self.root)['findings']), 1)

    def test_symlinks(self):
        self.write('README.md', 'extract tables')
        with tempfile.TemporaryDirectory() as other:
            path = Path(other)
            (path/'a.py').write_text('x.extract_tables()')
            (self.root/'linked.py').symlink_to(path/'a.py')
            (self.root/'linked').symlink_to(path, target_is_directory=True)
            self.assertEqual(audit(self.root)['findings'][0]['severity'], 'HIGH')

    def test_ignore_and_docs(self):
        self.write('docs/a.md', 'extract tables')
        self.write('notes.md', 'extract tables')
        self.assertEqual(self.cli('audit', str(self.root), '--ignore', 'docs', '--ignore', 'other')[0], 0)
        self.write('app.py', 'x.extract_tables()')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.assertEqual(audit(self.root, ['app'])['verdict'], 'FAIL')

    def test_cli_errors_and_version(self):
        self.assertEqual(self.cli('--version'), (0, '0.1.0\n'))
        for args in [[], ['audit','/nonexistent-r187'], ['audit','--fail-on','HIGH'],
                     ['audit','--ignore'], ['audit','--unknown']]:
            self.assertEqual(self.cli(*args)[0], 1)
        result = subprocess.run([sys.executable, '-m', 'table_extraction_claim_audit', '--version'],
                                capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout), (0, '0.1.0\n'))

    def test_no_source_asymmetry(self):
        self.write('README.md', 'extract tables')
        self.assertEqual(audit(self.root)['findings'][0]['severity'], 'HIGH')
        self.write('README.md', 'does not extract tables')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')

    def test_mixed_claims_and_longest_denial(self):
        self.write('README.md', 'does not extract tables from pdf')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.write('README.md', 'does not extract tables from pdf; extract tables')
        self.assertEqual(len(audit(self.root)['findings']), 1)
        self.write('app.py', 'x.extract_tables()')
        self.assertEqual(audit(self.root)['findings'][0]['id'],
                         'documented-no-table-extraction-claim-false')

    def test_io_errors(self):
        with patch('table_extraction_claim_audit.audit.os.walk', side_effect=PermissionError('unreadable')):
            self.assertEqual(self.cli('audit', str(self.root))[0], 1)
        self.write('README.md', 'safe')
        with patch.object(Path, 'read_text', side_effect=PermissionError('unreadable')):
            self.assertEqual(self.cli('audit', str(self.root))[0], 1)
        (self.root/'README.md').write_bytes(bytes([255]))
        self.assertEqual(self.cli('audit', str(self.root))[0], 1)

    def test_alias_binding_cycles_and_shadow(self):
        for source in ['import tabula as t; f = t.convert_into; f("x")',
                       'from tool import extract_tables as e; f = e; f()',
                       'import camelot; c: object = camelot; c.read_pdf("x")']:
            self.assertTrue(evidence(source))
        for source in ['import camelot; a = b; b = a; a.read_pdf("x")',
                       'from tool import extract_tables as e\ne = other\ne()',
                       'from tool import extract_tables as e\nwith thing() as e: e()',
                       'from tool import extract_tables as e\nclass extract_tables: pass\ne()']:
            self.assertFalse(evidence(source))

    def test_docs_selection_and_symlink(self):
        self.write('README.md', 'safe')
        self.write('nested/docs/guide.md', 'extract tables')
        self.assertEqual(audit(self.root)['findings'][0]['paths'], ['nested/docs/guide.md'])
        self.assertEqual(audit(self.root, ['nested'])['verdict'], 'PASS')
        (self.root/'nested/docs/guide.md').unlink()
        with tempfile.TemporaryDirectory() as other:
            path = Path(other)/'claims.md'
            path.write_text('extract tables')
            (self.root/'nested/docs/link.md').symlink_to(path)
            self.assertEqual(audit(self.root)['verdict'], 'PASS')

if __name__ == '__main__':
    unittest.main()
