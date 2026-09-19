"""
Benchmark Runner — Phase 4.

Runs the complete detection pipeline against the labeled dataset and
outputs precision, recall, F1-score, FPR, and confusion matrix.
Results are saved as benchmark_results.md.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Ensure backend packages are importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.dataset_builder import build_dataset
from detection.orchestrator import DetectionOrchestrator, OrchestratorConfig


def run_benchmark(
    threshold: float = 0.20,  # Anything above this = "injection" prediction
    output_path: Path | None = None,
) -> dict:
    """
    Run the full detection pipeline against the labeled dataset.

    Returns a dict with all metrics and per-sample results.
    """
    print("=" * 60)
    print("LLM PROMPT INJECTION FIREWALL — BENCHMARK")
    print("=" * 60)

    # --- Load dataset ---
    dataset = build_dataset()
    injections = dataset["injections"]
    benign = dataset["benign"]

    # --- Initialize orchestrator (no heavy ML models for speed) ---
    config = OrchestratorConfig()
    orch = DetectionOrchestrator(config=config)

    print(f"\nDataset: {len(injections)} injections, {len(benign)} benign")
    print(f"Detection threshold: {threshold}")
    print(f"Orchestrator layers: {sorted(config.enabled_layers)}")
    print("\nRunning benchmark...\n")

    results = []
    start_time = time.perf_counter()

    # --- Scan injections (expected: flagged) ---
    tp = fp = tn = fn = 0
    per_sample = []

    for sample in injections:
        report = orch.scan(sample["text"])
        predicted_injection = report.risk_score >= threshold
        correct = predicted_injection  # True Positive

        if predicted_injection:
            tp += 1
        else:
            fn += 1

        per_sample.append({
            "id": sample["id"],
            "true_label": "injection",
            "predicted": "injection" if predicted_injection else "benign",
            "correct": correct,
            "risk_score": round(report.risk_score, 4),
            "risk_level": report.risk_level.value,
            "category": sample["category"],
            "obfuscation": sample.get("obfuscation", "none"),
            "primary_reason": report.primary_reason,
        })

    # --- Scan benign samples (expected: not flagged) ---
    fp_trap_fp = 0  # FPs specifically on false-positive traps

    for sample in benign:
        report = orch.scan(sample["text"])
        predicted_injection = report.risk_score >= threshold
        correct = not predicted_injection  # True Negative

        if predicted_injection:
            fp += 1
            if sample.get("fp_trap"):
                fp_trap_fp += 1
        else:
            tn += 1

        per_sample.append({
            "id": sample["id"],
            "true_label": "benign",
            "predicted": "injection" if predicted_injection else "benign",
            "correct": correct,
            "risk_score": round(report.risk_score, 4),
            "risk_level": report.risk_level.value,
            "fp_trap": sample.get("fp_trap", False),
            "category": sample.get("category", ""),
            "primary_reason": report.primary_reason,
        })

    total_time = time.perf_counter() - start_time

    # --- Compute metrics ---
    total = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    accuracy = (tp + tn) / total if total > 0 else 0.0

    # Breakdown by obfuscation type
    obf_results: dict[str, dict] = {}
    for r in per_sample:
        if r["true_label"] == "injection":
            obf = r.get("obfuscation", "none")
            if obf not in obf_results:
                obf_results[obf] = {"detected": 0, "total": 0}
            obf_results[obf]["total"] += 1
            if r["correct"]:
                obf_results[obf]["detected"] += 1

    metrics = {
        "total_samples": total,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "false_positive_rate": round(fpr, 4),
        "accuracy": round(accuracy, 4),
        "fp_on_traps": fp_trap_fp,
        "total_traps": sum(1 for s in benign if s.get("fp_trap")),
        "benchmark_time_seconds": round(total_time, 2),
        "avg_time_per_sample_ms": round(total_time / total * 1000, 1) if total > 0 else 0,
        "obfuscation_breakdown": obf_results,
        "threshold_used": threshold,
        "per_sample": per_sample,
    }

    # --- Print summary ---
    _print_summary(metrics)

    # --- Save markdown report ---
    if output_path is None:
        output_path = Path(__file__).parent / "benchmark_results.md"
    _save_markdown(metrics, output_path)
    print(f"\n✅ Benchmark report saved to: {output_path}")

    return metrics


def _print_summary(m: dict) -> None:
    print(f"{'─'*50}")
    print(f"  Total samples:          {m['total_samples']}")
    print(f"  True Positives (TP):    {m['tp']}")
    print(f"  False Positives (FP):   {m['fp']}")
    print(f"  True Negatives (TN):    {m['tn']}")
    print(f"  False Negatives (FN):   {m['fn']}")
    print(f"{'─'*50}".encode('ascii', errors='replace').decode())
    print(f"  Precision:              {m['precision']:.1%}")
    print(f"  Recall:                 {m['recall']:.1%}")
    print(f"  F1 Score:               {m['f1_score']:.1%}")
    print(f"  False Positive Rate:    {m['false_positive_rate']:.1%}")
    print(f"  Accuracy:               {m['accuracy']:.1%}")
    print(f"{'─'*50}".encode('ascii', errors='replace').decode())
    print(f"  FPs on tricky traps:    {m['fp_on_traps']}/{m['total_traps']}")
    print(f"  Total time:             {m['benchmark_time_seconds']:.1f}s")
    print(f"  Avg per sample:         {m['avg_time_per_sample_ms']:.0f}ms")
    print(f"{'─'*50}")

    print("\nDetection by obfuscation type:")
    for obf, res in sorted(m["obfuscation_breakdown"].items()):
        pct = res["detected"] / res["total"] * 100 if res["total"] > 0 else 0
        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        print(f"  {obf:<25} [{bar}] {res['detected']}/{res['total']} ({pct:.0f}%)")


def _save_markdown(m: dict, path: Path) -> None:
    obf_table = "\n".join(
        f"| `{obf}` | {res['detected']} / {res['total']} | "
        f"{res['detected']/res['total']*100:.0f}% |"
        for obf, res in sorted(m["obfuscation_breakdown"].items())
    )

    # Per-sample table (failures only, for brevity)
    failures = [r for r in m["per_sample"] if not r["correct"]]
    failures_table = "\n".join(
        f"| `{r['id']}` | {r['true_label']} | {r['predicted']} | {r['risk_score']} | "
        f"{r.get('obfuscation', r.get('fp_trap', ''))} |"
        for r in failures[:20]  # cap at 20
    )

    md = f"""# LLM Prompt Injection Firewall — Benchmark Results

> **Generated by `benchmark/run_benchmark.py`**
> Threshold: `{m['threshold_used']}` | Samples: `{m['total_samples']}`

## Summary

| Metric | Value |
|--------|-------|
| **Precision** | {m['precision']:.1%} |
| **Recall** | {m['recall']:.1%} |
| **F1 Score** | {m['f1_score']:.1%} |
| **False Positive Rate** | {m['false_positive_rate']:.1%} |
| **Accuracy** | {m['accuracy']:.1%} |
| Total Samples | {m['total_samples']} |
| True Positives | {m['tp']} |
| False Positives | {m['fp']} |
| True Negatives | {m['tn']} |
| False Negatives | {m['fn']} |
| FPs on Deceptive Traps | {m['fp_on_traps']} / {m['total_traps']} |
| Avg scan time (ms) | {m['avg_time_per_sample_ms']} |

## Confusion Matrix

```
                    Predicted
                 Injection | Benign
              ┌────────────┬────────┐
Actual Inject │  TP={m['tp']:>4}   │ FN={m['fn']:>3} │
       Benign │  FP={m['fp']:>4}   │ TN={m['tn']:>3} │
              └────────────┴────────┘
```

## Detection by Obfuscation Type

| Obfuscation Method | Detected | Detection Rate |
|--------------------|----------|----------------|
{obf_table}

## Missed Detections & False Positives (up to 20)

| ID | True Label | Predicted | Score | Notes |
|----|-----------|-----------|-------|-------|
{failures_table if failures_table else "*(None — perfect score!)*"}

---

> [!CAUTION]
> **Disclaimer:** This firewall is a defense-in-depth layer, not a guaranteed or
> foolproof solution.  Adversarial prompt injection is an active research area and
> no static ruleset or classifier can provide 100% coverage against all current and
> future attack vectors.  Use this tool as one layer in a broader security strategy.
"""
    path.write_text(md, encoding="utf-8")


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    run_benchmark()
