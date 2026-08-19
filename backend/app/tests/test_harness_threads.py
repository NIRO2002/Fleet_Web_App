import os

from app.evaluation import harness  # noqa: F401


def test_evaluation_workers_limit_numerical_thread_pools():
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        assert os.environ[name] == "1"
