"""Offline documentation and Python syntax inspection."""
import ast
import os
import re
from pathlib import Path
from . import phrases as p


def normalize(text):
    return ' '.join(text.lower().replace("n't", ' not').replace('-', ' ').split())


def paragraphs(text):
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = None
            lines.append('')
        elif match:
            fence = match[1]
            lines.append('')
        else:
            lines.append(line)
    return [normalize(x) for x in re.split(r'\n\s*\n', '\n'.join(lines)) if x.strip()]


def pattern(phrases):
    return re.compile(r'\b(?:' + '|'.join(re.escape(normalize(x)) for x in sorted(phrases, key=lambda x: (-len(x), x))) + r')\b')


POSITIVE = pattern(p.TABLEEXTRACTION)
NEGATIVE = pattern(p.NOTABLEEXTRACTION)


def evidence(source):
    """Recognize listed calls within one syntactically valid module."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    nodes = list(ast.walk(tree))
    shadow = {n.name for n in nodes
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    aliases, bindings, gates = {}, {}, set()

    def bind(target, value):
        if isinstance(target, ast.Name):
            bindings[target.id] = value
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                bind(item, None)

    for node in nodes:
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split('.')[0]] = (
                    item.name if item.asname else item.name.split('.')[0])
                gates.add(item.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            gates.add(module.split('.')[0])
            for item in node.names:
                if item.name != '*':
                    aliases[item.asname or item.name] = module + '.' + item.name
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                bind(target, node.value)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                bind(item.optional_vars, item.context_expr)

    def resolve(expr, seen=()):
        if isinstance(expr, ast.Name):
            if expr.id in shadow or expr.id in seen:
                return ''
            if expr.id in bindings:
                return resolve(bindings[expr.id], seen + (expr.id,))
            return aliases.get(expr.id, '')
        if isinstance(expr, ast.Attribute):
            if expr.attr in shadow:
                return ''
            base = resolve(expr.value, seen)
            return base + '.' + expr.attr if base else ''
        return ''

    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        resolved = resolve(func)
        if isinstance(func, ast.Attribute):
            operation = func.attr
            if operation in shadow:
                continue
            # A locally bound imported receiver cannot impersonate its old import.
            if isinstance(func.value, ast.Name) and func.value.id in shadow:
                continue
            if operation in p.GENERIC_NAMES:
                return True
            for gate, names in (('camelot', p.CAMELOT_NAMES), ('tabula', p.TABULA_NAMES)):
                if gate not in gates or operation not in names:
                    continue
                literal = (isinstance(func.value, ast.Name) and func.value.id == gate
                           and gate not in bindings and gate not in shadow)
                if literal or resolved == gate + '.' + operation:
                    return True
            if 'pdfplumber' in gates and operation in p.PDFPLUMBER_NAMES:
                return True
            if gates.intersection({'fitz', 'pymupdf'}) and operation in p.FITZ_NAMES:
                return True
        elif isinstance(func, ast.Name) and resolved:
            operation = resolved.split('.')[-1]
            if operation in shadow:
                continue
            if operation in p.GENERIC_NAMES:
                return True
            for gate, names in (('camelot', p.CAMELOT_NAMES), ('tabula', p.TABULA_NAMES),
                                ('pdfplumber', p.PDFPLUMBER_NAMES), ('fitz', p.FITZ_NAMES),
                                ('pymupdf', p.FITZ_NAMES)):
                if gate in gates and resolved == gate + '.' + operation and operation in names:
                    return True
    return False


def audit(repo='.', ignore=()):
    root = Path(repo)
    if not root.is_dir():
        raise OSError('not a directory: ' + str(root))
    positive, negative, production, tests = [], [], [], []
    for directory, dirs, files in os.walk(root, onerror=lambda error: (_ for _ in ()).throw(error), followlinks=False):
        dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink()
                         and not any((Path(directory) / d).relative_to(root).as_posix().startswith(prefix)
                                     for prefix in ignore))
        for filename in sorted(files):
            path = Path(directory) / filename
            rel = path.relative_to(root)
            if path.is_symlink() or any(rel.as_posix().startswith(prefix) for prefix in ignore):
                continue
            if rel.as_posix() == 'README.md' or (path.suffix == '.md' and 'docs' in rel.parts[:-1]):
                for para in paragraphs(path.read_text(encoding='utf-8')):
                    if NEGATIVE.search(para):
                        negative.append(rel.as_posix())
                    if POSITIVE.search(NEGATIVE.sub(' ', para)):
                        positive.append(rel.as_posix())
            if path.suffix == '.py' and not set(rel.parts[:-1]) & {'fixtures', 'docs', 'examples'}:
                if evidence(path.read_text(encoding='utf-8')):
                    is_test = 'tests' in rel.parts[:-1] or filename.startswith('test_') or filename.endswith('_test.py')
                    (tests if is_test else production).append(rel.as_posix())
    findings = []
    if positive and not production:
        findings.append(dict(id='documented-table-extraction-claim-false', severity='MEDIUM' if tests else 'HIGH', message='Documented capability has only test evidence.' if tests else 'Documented capability has no production evidence.', paths=sorted(set(positive))))
    if negative and production:
        findings.append(dict(id='documented-no-table-extraction-claim-false', severity='HIGH', message='Documented denial contradicts production evidence.', paths=sorted(set(negative))))
    return dict(verdict='FAIL' if findings else 'PASS', findings=findings, evidence=production, test_evidence=tests)
