"""Load and validate an environment package. Every parameter must be published (with source,
locator and quote) or derived (with a formula over other parameters, recomputed here).
Anything incomplete raises PackageError; nothing is defaulted.

    python -m mission.package [package-id]   # prints the resolved parameter table
"""
import ast
import hashlib
import json
import math
import sys
from pathlib import Path

PACKAGES = Path(__file__).resolve().parent / 'packages'
PUBLISHED_FIELDS = {'value', 'unit', 'source', 'locator', 'quote', 'retrieved'}
DERIVED_FIELDS = {'unit', 'formula', 'inputs', 'note'}
_ALLOWED = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Attribute,
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.Load)


class PackageError(ValueError):
    pass


def _evaluate(formula, values):
    # Parameter names contain dots; map each to a safe identifier before parsing.
    names = sorted(values, key=len, reverse=True)
    expr = formula
    mapping = {}
    for i, name in enumerate(names):
        token = f'_p{i}'
        if name in expr:
            expr = expr.replace(name, token)
            mapping[token] = values[name]
    tree = ast.parse(expr, mode='eval')
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise PackageError(f'Disallowed syntax in formula: {formula}')
        if isinstance(node, ast.Name) and node.id not in mapping and node.id != 'pi':
            raise PackageError(f'Formula references an undeclared name {node.id!r}: {formula}')
    result = eval(compile(tree, '<formula>', 'eval'), {'__builtins__': {}}, {**mapping, 'pi': math.pi})
    if not isinstance(result, (int, float)) or not math.isfinite(result):
        raise PackageError(f'Formula did not produce a finite number: {formula}')
    return float(result)


def load(package_id='arcadia-mars-v1', overrides=None):
    """overrides: {published parameter: value within its recorded range}, for uncertainty propagation only."""
    path = PACKAGES / f'{package_id}.json'
    if not path.exists():
        raise PackageError(f'No environment package {package_id!r} at {path}')
    raw = path.read_bytes()
    pkg = json.loads(raw)
    sources, params = pkg.get('sources') or {}, pkg.get('parameters') or {}
    for sid, source in sources.items():
        if not source.get('url') or not source.get('title'):
            raise PackageError(f'Source {sid} needs url and title')
    values = {}
    for name, p in params.items():
        if p.get('classification') == 'published':
            missing = PUBLISHED_FIELDS - set(p)
            if missing:
                raise PackageError(f'{name}: published parameter missing {sorted(missing)}')
            if p['source'] not in sources:
                raise PackageError(f'{name}: unknown source {p["source"]}')
            v = p['value']
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise PackageError(f'{name}: value must be a finite number')
            values[name] = float(v)
            if overrides and name in overrides:
                rng = p.get('range') or {}
                if not rng or not rng['minimum'] <= overrides[name] <= rng['maximum']:
                    raise PackageError(f'{name}: override {overrides[name]} outside the recorded range')
                values[name] = float(overrides[name])
        elif p.get('classification') != 'derived':
            raise PackageError(f'{name}: classification must be published or derived')
    pending = {n: p for n, p in params.items() if p['classification'] == 'derived'}
    while pending:
        progressed = False
        for name, p in list(pending.items()):
            missing = DERIVED_FIELDS - set(p)
            if missing:
                raise PackageError(f'{name}: derived parameter missing {sorted(missing)}')
            unknown = [i for i in p['inputs'] if i not in params]
            if unknown:
                raise PackageError(f'{name}: inputs not in package {unknown}')
            if all(i in values for i in p['inputs']):
                values[name] = _evaluate(p['formula'], {i: values[i] for i in p['inputs']})
                del pending[name]
                progressed = True
        if not progressed:
            raise PackageError(f'Circular or unresolved derivations: {sorted(pending)}')
    conflicts = pkg.get('conflicts') or {}
    for cid, c in conflicts.items():
        if len(c.get('parameters') or []) < 2 or any(n not in values for n in c['parameters']):
            raise PackageError(f'Conflict {cid} must list at least two resolved parameters')
        if c.get('selected') is not None and c['selected'] not in c['parameters']:
            raise PackageError(f'Conflict {cid} selected value is not one of its parameters')
    decisions = pkg.get('operator_decisions') or {}
    for name,p in params.items():
        if p.get('model_assumption') and p['model_assumption'] not in decisions:
            raise PackageError(f'{name}: model assumption must resolve to a recorded operator decision')
    unapproved = sorted(k for k, d in decisions.items() if not d.get('approved'))
    return {'id': pkg['id'], 'environment': pkg['environment'], 'hash': hashlib.sha256(raw).hexdigest(),
            'values': values, 'parameters': params, 'sources': sources, 'decisions': decisions,
            'conflicts': {cid: {**c, 'values': {n: values[n] for n in c['parameters']}} for cid, c in conflicts.items()},
            'unapproved_decisions': unapproved}


def require_approved(package):
    if package['unapproved_decisions']:
        raise PackageError('Mission cannot start: operator decisions not approved: ' + ', '.join(package['unapproved_decisions']))


if __name__ == '__main__':
    pkg = load(sys.argv[1] if len(sys.argv) > 1 else 'arcadia-mars-v1')
    print(f"{pkg['id']}  sha256:{pkg['hash'][:16]}")
    for name in sorted(pkg['values']):
        p = pkg['parameters'][name]
        origin = {'published': lambda: f"{p['source']} {p['locator']}", 'derived': lambda: p['formula'],
                  'computed': lambda: f"{p['source']}:{p['function']}"}[p['classification']]()
        print(f"{name:34} {pkg['values'][name]:>16.6g} {p['unit']:<28} {p['classification']:<9} {origin}")
    for cid, c in pkg['conflicts'].items():
        print(f"CONFLICT {cid}: " + ', '.join(f'{n}={v:.4g}' for n, v in c['values'].items()) + f" -> selected {c['selected']}")
    print('Unapproved decisions:', ', '.join(pkg['unapproved_decisions']) or 'none')
