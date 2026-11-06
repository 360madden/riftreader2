#!/usr/bin/env python3
"""Retired legacy experiment adapter.

Use the RR2-owned supervised controller workflow documented in
 docs/workflows/operation-dependencies.md. This entry point performs no input.
"""
import json
import sys


def main():
    print(json.dumps({'status': 'retired', 'reason': 'legacy experiment adapter removed',
                      'replacement': 'python scripts/ensure_controller.py --help',
                      'workflow': 'docs/workflows/operation-dependencies.md'}), file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
