"""Fix Pass 2 items B and E: a thin CLI over `harness.run_batch`.

`python -m app.evaluation.cli run --n-parcels 400 --pop 100 --gen 200 \
    --seeds 0,1,2 --out results/ [--allow-dirty]`

Refuses to run against a dirty git tree (item E) -- a results set produced
from uncommitted code can't be tied back to what produced it -- and writes a
reproducibility manifest into the output directory before any GA work
starts.
"""
import argparse
import sys
from pathlib import Path

from app.core.reproducibility import is_git_dirty, write_manifest
from app.evaluation.harness import RunConfig, run_batch


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.evaluation.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run one or more GA instances and write results.")
    run.add_argument("--n-parcels", type=int, default=400)
    run.add_argument("--pop", type=int, default=100)
    run.add_argument("--gen", type=int, default=200)
    run.add_argument("--n-clusters", type=int, default=8)
    run.add_argument("--seeds", type=str, default="0", help="Comma-separated instance/GA seeds, e.g. 0,1,2")
    run.add_argument("--out", type=str, required=True, help="Output directory for per-run result files.")
    run.add_argument("--n-jobs", type=int, default=-1)
    run.add_argument("--allow-dirty", action="store_true", help="Skip the git-clean check.")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if args.command == "run":
        if is_git_dirty() and not args.allow_dirty:
            print(
                "Refusing to run: the git working tree has uncommitted changes. "
                "A results set produced from an uncommitted tree can't be reproduced "
                "against any commit. Commit your changes, or pass --allow-dirty to "
                "override (not recommended for results you intend to report).",
                file=sys.stderr,
            )
            return 1

        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        write_manifest(out_dir / "manifest.json")

        seeds = [int(s) for s in args.seeds.split(",")]
        configs = [
            RunConfig(
                n_parcels=args.n_parcels, instance_seed=seed, ga_seed=seed, n_clusters=args.n_clusters,
                population=args.pop, generations=args.gen,
            )
            for seed in seeds
        ]
        results = run_batch(configs, n_jobs=args.n_jobs, out_dir=out_dir)
        for r in results:
            print(
                f"seed={r['instance_seed']} elapsed={r['elapsed_seconds']:.1f}s "
                f"cache_hit_rate={r['cache_hit_rate']:.1%} short_circuit_rate={r['short_circuit_rate']:.1%}"
            )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
