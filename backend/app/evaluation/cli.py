"""Fix Pass 2 items B and E / Fix Pass 4 item S7: a thin CLI over
`harness.py`.

GA-only benchmark (real data by default as of Fix Pass 4 S5):
`python -m app.evaluation.cli run --n-parcels 400 --pop 100 --gen 200 \
    --seeds 0,1,2 --out results/ [--synthetic] [--allow-dirty]`

Full evaluation pipeline (Fix Pass 4 S7) -- one run per
(depot, date, method, capacity_aware, seed) combination, resumable:
`python -m app.evaluation.cli pipeline --methods hdbscan,kmeans \
    --capacity-aware both --seeds 0,1,2 --instances all --out results/ \
    [--allow-dirty]`

Both refuse to run against a dirty git tree (item E) -- a results set
produced from uncommitted code can't be tied back to what produced it --
and write a reproducibility manifest into the output directory before any
GA work starts.
"""
import argparse
import sys
from pathlib import Path

from app.core.reproducibility import is_git_dirty, write_manifest
from app.evaluation.harness import PipelineRunConfig, RunConfig, run_batch, run_pipeline_batch
from app.evaluation.real_data import list_instances


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.evaluation.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="GA-only benchmark: catalog load + run_nsga2, no persistence.")
    run.add_argument("--n-parcels", type=int, default=400)
    run.add_argument("--pop", type=int, default=100)
    run.add_argument("--gen", type=int, default=200)
    run.add_argument("--n-clusters", type=int, default=8)
    run.add_argument("--seeds", type=str, default="0", help="Comma-separated instance/GA seeds, e.g. 0,1,2")
    run.add_argument("--out", type=str, required=True, help="Output directory for per-run result files.")
    run.add_argument("--n-jobs", type=int, default=-1)
    run.add_argument("--synthetic", action="store_true", help="Use synthetic_data.py instead of real data.")
    run.add_argument(
        "--depot-id", type=str, default="D-CMB-001", help="Real-data instance depot (ignored with --synthetic)."
    )
    run.add_argument(
        "--delivery-date", type=str, default="2026-01-05",
        help="Real-data instance date, YYYY-MM-DD (ignored with --synthetic).",
    )
    run.add_argument("--allow-dirty", action="store_true", help="Skip the git-clean check.")

    pipeline = subparsers.add_parser("pipeline", help="Full pipeline: clustering -> capacity-aware -> NSGA-II -> LoadPlan.")
    pipeline.add_argument("--methods", type=str, default="hdbscan,kmeans")
    pipeline.add_argument(
        "--capacity-aware", type=str, default="both", choices=["on", "off", "both"],
    )
    pipeline.add_argument("--seeds", type=str, default="0", help="Comma-separated seeds, e.g. 0,1,2")
    pipeline.add_argument(
        "--instances", type=str, default="all",
        help="'all' (every (depot_id, delivery_date) in the dataset) or 'depot_id/delivery_date' pairs "
        "separated by ';', e.g. 'D-CMB-001/2026-01-05;D-CMB-002/2026-01-10'.",
    )
    pipeline.add_argument("--pop", type=int, default=100)
    pipeline.add_argument("--gen", type=int, default=200)
    pipeline.add_argument("--out", type=str, required=True, help="Output directory for per-run result files.")
    pipeline.add_argument("--n-jobs", type=int, default=-1)
    pipeline.add_argument("--allow-dirty", action="store_true", help="Skip the git-clean check.")

    return parser.parse_args(argv)


def _refuse_if_dirty(allow_dirty: bool) -> bool:
    if is_git_dirty() and not allow_dirty:
        print(
            "Refusing to run: the git working tree has uncommitted changes. "
            "A results set produced from an uncommitted tree can't be reproduced "
            "against any commit. Commit your changes, or pass --allow-dirty to "
            "override (not recommended for results you intend to report).",
            file=sys.stderr,
        )
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if args.command == "run":
        if _refuse_if_dirty(args.allow_dirty):
            return 1

        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        write_manifest(out_dir / "manifest.json")

        seeds = [int(s) for s in args.seeds.split(",")]
        configs = [
            RunConfig(
                n_parcels=args.n_parcels, instance_seed=seed, ga_seed=seed, n_clusters=args.n_clusters,
                population=args.pop, generations=args.gen, synthetic=args.synthetic,
                depot_id=args.depot_id, delivery_date=args.delivery_date,
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

    if args.command == "pipeline":
        if _refuse_if_dirty(args.allow_dirty):
            return 1

        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        write_manifest(out_dir / "manifest.json")

        methods = args.methods.split(",")
        capacity_aware_values = {"on": [True], "off": [False], "both": [True, False]}[args.capacity_aware]
        seeds = [int(s) for s in args.seeds.split(",")]
        if args.instances == "all":
            instances = list_instances()
        else:
            instances = [tuple(pair.split("/")) for pair in args.instances.split(";")]

        configs = [
            PipelineRunConfig(
                depot_id=depot_id, delivery_date=delivery_date, method=method, capacity_aware=capacity_aware,
                seed=seed, population=args.pop, generations=args.gen,
            )
            for depot_id, delivery_date in instances
            for method in methods
            for capacity_aware in capacity_aware_values
            for seed in seeds
        ]
        print(f"{len(configs)} runs queued ({len(instances)} instances x {len(methods)} methods x "
              f"{len(capacity_aware_values)} capacity-aware settings x {len(seeds)} seeds)")
        results = run_pipeline_batch(configs, n_jobs=args.n_jobs, out_dir=out_dir)
        for r in results:
            print(
                f"{r['run_id']}: utilization={r['mean_utilization']:.1%} "
                f"(ceiling {r['utilization_ceiling']:.1%}) runtime={r['runtime_seconds']:.1f}s"
            )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
