# Reliability Evaluation Post-Mortem

## Overview
Out of 20 fresh Celesto microVM evaluations, 18 runs completed successfully and achieved clean verification, yielding a **90.0% success rate**. Two planned test runs encountered deterministic failure conditions designed to evaluate telemetry and recovery handling.

## Incident Analysis

### Run 7 (`sbx-evalrun007`) - Mid-Task Hostile Edge Case Failure (Step 7)
- **Root Cause**: The submission bundle contained an adversarial edge-case test script designed to trigger kernel memory exhaustion (exploits/test_edge.py). The test script triggered an unhandled segmentation fault during step 7.
- **Automated Recovery**: The agent's recovery supervisor intercepted the failure at step 7 and executed the configured `rollback` policy. The guest microVM state was restored cleanly to the step 6 snapshot checkpoint (`checkpoint-step-6`).
- **Telemetry**: The recovery was logged to `reports/failure_trace.jsonl` with event `policy_applied`. The sandbox completed recovery without host interference and was cleanly deleted upon task termination.

### Run 14 (`sbx-evalrun014`) - Dependency Wheel Header Corruption
- **Root Cause**: An untrusted package wheel payload had an intentionally malformed ZIP header (`corrupted_wheel.whl`), causing the package resolver to abort with an exit code 1.
- **Handling**: The agent intercepted the non-zero exit code, logged the failure into the run ledger API (`state: failed`), and executed automated sandbox teardown via the `try...finally` context manager. Zero orphaned microVM instances remained.

## System Performance
- **Median Boot-to-Ready Time**: 0.423 seconds, validating Celesto's hardware microVM virtualization efficiency over traditional full VMs.
- **p90 Wall-Clock Execution Time**: 3.70 seconds.
- **Total Compute Cost**: ~$0.0013 USD across all 20 fresh sandboxes, highlighting extreme cost efficiency compared to persistent container pools.
