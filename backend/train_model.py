"""Train (or retrain) the supervised career classifier and print how each algorithm scored.

    python train_model.py

The API also trains the model automatically on first start and whenever careers.csv changes,
so this script is only needed to retrain on demand or to see the comparison table.
"""
from __future__ import annotations

import argparse
import logging

import database as db
from config import get_settings
from ml_model import load_or_train


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--samples-per-career", type=int, default=None,
                        help="Generated training profiles per career (default from SAMPLES_PER_CAREER, 80).")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    settings = get_settings()
    careers = db.load_careers_csv(settings.careers_csv)
    per_career = args.samples_per_career or settings.samples_per_career
    print(f"Training on {len(careers)} careers x {per_career} generated profiles ...")
    classifier = load_or_train(careers, settings.model_path, per_career, force=True)
    report = classifier.report

    print(f"\nHeld-out test set: {report['samples']['test']} profiles "
          f"(train {report['samples']['train']}, {report['samples']['features']} features)\n")
    print(f"{'Algorithm':<26}{'Accuracy':>10}{'Top-3':>9}{'Macro F1':>10}{'Log loss':>10}{'Train s':>9}")
    for name, m in report["comparison"].items():
        mark = "  <- selected" if name == report["selected"] else ""
        print(f"{name:<26}{m['accuracy']:>10.1%}{m['top3_accuracy']:>9.1%}{m['macro_f1']:>10.3f}"
              f"{m['log_loss']:>10.3f}{m['train_seconds']:>9.2f}{mark}")
    print(f"\nSaved to {settings.model_path}")
    print(f"Metrics written to {settings.model_path.with_suffix('.metrics.json')}")
    print("Note: the test profiles are generated the same way as the training profiles, so these scores show"
          "\nhow well the model learned the career dataset, not how accurate it is for real people.")


if __name__ == "__main__":
    main()
