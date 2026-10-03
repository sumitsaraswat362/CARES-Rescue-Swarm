"""Validate explicitly registered claims against files, symbols and frozen JSON.

This checks the registry's declared facts. It does not understand arbitrary prose,
prove algorithm correctness, or certify flight performance.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path


def check(registry, root):
    root = Path(root).resolve()
    data = json.loads(Path(registry).read_text())
    errors = []
    identifiers = set()
    for claim in data['claims']:
        cid = claim['id']
        if cid in identifiers:
            errors.append(f'{cid}: duplicate claim ID')
        identifiers.add(cid)
        if claim['status'] not in ('planned', 'blocked', 'implemented', 'verified'):
            errors.append(f'{cid}: unsupported status')
        for reference in claim.get('implementation', []):
            path = (root / reference['path']).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                errors.append(f'{cid}: missing or outside-root implementation path')
                continue
            symbol = reference.get('symbol')
            if symbol:
                names = {node.name for node in ast.walk(ast.parse(path.read_text()))
                         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
                if symbol not in names:
                    errors.append(f'{cid}: symbol {symbol} not found in {reference["path"]}')
        evidence = claim.get('evidence', [])
        if claim['status'] == 'verified' and not evidence:
            errors.append(f'{cid}: verified claim has no evidence')
        for reference in evidence:
            path = (root / reference['path']).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                errors.append(f'{cid}: evidence file missing or outside repository')
                continue
            if hashlib.sha256(path.read_bytes()).hexdigest() != reference['sha256']:
                errors.append(f'{cid}: evidence checksum changed')
                continue
            value = json.loads(path.read_text())
            try:
                for key in reference.get('keys', []):
                    value = value[key]
                if value != reference['equals']:
                    errors.append(f'{cid}: numerical/status claim disagrees with JSON')
            except (KeyError, IndexError, TypeError):
                errors.append(f'{cid}: JSON evidence path is invalid')
    return {'registered_claims': len(identifiers), 'passed': not errors, 'errors': errors,
            'scope': 'Registered structured claims only; arbitrary document prose still needs review.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', default='validation/claims.json')
    parser.add_argument('--root', default='.')
    args = parser.parse_args()
    result = check(args.registry, args.root)
    print(json.dumps(result, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
