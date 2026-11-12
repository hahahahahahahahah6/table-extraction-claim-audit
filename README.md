# Documentation claim auditor

An offline audit tool that compares documentation about the checked capability with listed calls in Python source. It parses syntax without running the inspected code. Requires Python 3.9 or newer; no runtime dependencies.

Install and run:

```sh
python3 -m pip install .
table-extraction-claim-audit --version
table-extraction-claim-audit audit .
python3 -m table_extraction_claim_audit audit . --json
```

The optional directory defaults to the current directory. Available options:

```text
--json                 Emit a JSON object
--verbose              Show production and test evidence paths
--ignore PREFIX        Skip a relative path prefix; repeat for more prefixes
--fail-on high|medium  Failure threshold; default high
--version              Print 0.1.0 (top-level option)
```

The scanner checks root README.md and Markdown files beneath any directory component named docs. It skips backtick and tilde fences with up to three leading spaces; inline code counts. Paragraphs are normalized for case, contractions, hyphens, and whitespace. Exact phrases use word boundaries, longest first with alphabetical ties. Denial spans are removed before affirmative matching.

Python files are inspected one module at a time. Symlinks are skipped. Files beneath fixtures, docs, and examples contribute no evidence. Files beneath tests or named with the usual test prefix or suffix contribute only test evidence. Invalid syntax contributes none. Local function, method, and class definitions shadow route names. Import aliases and simple assignments, annotations, and context manager bindings are tracked.

The JSON object contains verdict, findings, evidence, and test_evidence. Findings contain id, severity, message, and paths. One finding per contradictory claim family is emitted:

```text
documented-table-extraction-claim-false     HIGH, or MEDIUM for test-only evidence
documented-no-table-extraction-claim-false HIGH
```

Exit status is 0 for a pass or findings below the selected threshold, 2 for findings meeting the threshold, and 1 for usage or input errors. An affirmative claim with no source is high severity; a denial with no source passes.

Supported calls and import gates:

```text
camelot: read_pdf
tabula: read_pdf, convert_into
pdfplumber: extract_table, extract_tables, find_table, find_tables
fitz / pymupdf: find_tables
```

The exact generic call names are defined in the installed phrase module. Generic attributes count without an import; bare names require import resolution. Imports alone, opening a document, plain text access, OCR, spreadsheet reads, exports, and external process invocations contribute no evidence.

Limitations are deliberate. This is static pattern matching; dead code counts, complex alias chains may be missed, and matching does not establish runtime correctness. Only listed phrases count, denials depend on the denial list, and each route must reside within one module. Ambiguous wording can refer to images, HTML, Markdown, or manual conversion and still match:

```text
table detection / detect tables
parse tables
pdf table to dataframe / pdf tables to dataframe
```

Generic calls may refer to an HTML operation or an external-process wrapper. Their names still count; a wrapper containing only an external process call contributes none:

```text
extract_table(...)
find_tables(...)
```

These operations are outside the recognized routes:

```text
tabula.convert_into_by_batch(...)       # batch wrapper
unstructured.partition_pdf(...)        # document partitioning
Docling DocumentConverter.convert(...) # document conversion
page.get_text("dict") / get_text("words") plus manual column detection
camelot CLI / tabula-java CLI / any external CLI via subprocess
```

The following built-in parsers work on text-based PDFs. For scanned inputs, the recognized call alone does not establish an OCR step or successful results. OCR alone does not satisfy the checked capability:

```text
Camelot, tabula-py, pdfplumber
```

Run the regression suite and build both distributions:

```sh
python3 -m unittest discover
python3 -m build
```

MIT licensed.
