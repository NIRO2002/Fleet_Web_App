"""Command-line entry point for the Beanie evaluation harness."""
import argparse
import asyncio
import sys
from pathlib import Path

from app.core.reproducibility import is_git_dirty, write_manifest
from app.db.database import init_database
from app.evaluation.harness import PipelineRunConfig, evaluation_catalog_snapshot, run_pipeline_batch_async
from app.evaluation.real_data import DATASET_PATH, list_instances


def _parse_args(argv):
    parser = argparse.ArgumentParser(prog="python -m app.evaluation.cli")
    parser.add_argument("--methods", default="hdbscan,kmeans")
    parser.add_argument("--capacity-aware", choices=("on", "off", "both"), default="both")
    parser.add_argument("--seeds", default=",".join(map(str, range(30))))
    parser.add_argument("--instances", default="all")
    parser.add_argument("--feature-set", default="location")
    parser.add_argument("--time-weight", type=float, default=5.0)
    parser.add_argument("--include-window-width", action="store_true")
    parser.add_argument("--pop", type=int, default=100)
    parser.add_argument("--gen", type=int, default=200)
    parser.add_argument("--out", required=True)
    parser.add_argument("--n-jobs", type=int, default=1)
    parser.add_argument("--allow-dirty", action="store_true")
    return parser.parse_args(argv)


async def _prepare(args):
    await init_database()
    catalog = await evaluation_catalog_snapshot()
    output = Path(args.out); output.mkdir(parents=True, exist_ok=True)
    write_manifest(output / "manifest.json", catalog=catalog, dataset_path=DATASET_PATH,
        experiment_config=vars(args), extra={"seeds": [int(x) for x in args.seeds.split(",")]})


async def _execute(args, configs):
    await _prepare(args)
    await run_pipeline_batch_async(configs, n_jobs=args.n_jobs, out_dir=args.out)


def main(argv=None):
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if is_git_dirty() and not args.allow_dirty:
        print("Refusing to evaluate a dirty working tree; commit or use --allow-dirty.", file=sys.stderr)
        return 1
    instances = list_instances() if args.instances == "all" else [tuple(x.split("/")) for x in args.instances.split(";")]
    capacity = {"on": [True], "off": [False], "both": [False, True]}[args.capacity_aware]
    configs = [PipelineRunConfig(
        depot_id=depot, delivery_date=str(day), method=method,
        capacity_aware=cap, seed=seed, population=args.pop,
        generations=args.gen, feature_set=args.feature_set,
        time_weight=args.time_weight,
        include_window_width=args.include_window_width,
    )
        for depot, day in instances for method in args.methods.split(",") for cap in capacity
        for seed in [int(x) for x in args.seeds.split(",")]]
    asyncio.run(_execute(args, configs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
