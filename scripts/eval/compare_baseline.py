import argparse
from backend.config import Config
from backend.eval_v2.artifacts import EvalArtifactStore

parser = argparse.ArgumentParser(); parser.add_argument("current"); parser.add_argument("baseline"); args = parser.parse_args()
store = EvalArtifactStore(Config.EVAL_ARTIFACT_DIR)
current = store.read(args.current, "metrics.json")["payload"]
baseline = store.read(args.baseline, "metrics.json")["payload"]
print({key: {"current": value, "baseline": baseline.get(key), "delta": value - baseline.get(key, value)} for key, value in current.items()})
