from __future__ import annotations

import argparse
import json
import sys

from .db import make_engine
from .retrieval import IndexConfigurationError, build_index


def main() -> int:
    parser = argparse.ArgumentParser(description='Build a complete provider-scoped Signal embedding index.')
    parser.add_argument('--batch-size', type=int, default=64, help='Embedding records per provider request (1–128).')
    args = parser.parse_args()
    try:
        result = build_index(make_engine(), batch_size=args.batch_size)
    except (IndexConfigurationError, RuntimeError, ValueError) as exc:
        print(f'Index build failed: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
