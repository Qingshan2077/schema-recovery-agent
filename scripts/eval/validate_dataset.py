"""Validate a registered dataset without executing an Agent or database fixture."""
import argparse

from backend.config import Config
from backend.eval_v2.registry import DatasetRegistry


parser = argparse.ArgumentParser()
parser.add_argument("--dataset", required=True)
parser.add_argument("--version", required=True)
parser.add_argument("--split", required=True)
args = parser.parse_args()
manifest, cases = DatasetRegistry(Config.EVAL_DATASET_REGISTRY_PATH).load(args.dataset, args.version, args.split)
print({"dataset": manifest.dataset_id, "version": manifest.version, "split": args.split, "cases": len(cases), "hash": manifest.content_hash})
