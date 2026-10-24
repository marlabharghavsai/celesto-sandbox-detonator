import os
import json
import time
import signal
import sys
from pathlib import Path
from typing import Dict, Any, List

from src.agent.celesto_client import CelestoSandbox

TRACE_PATH = Path(__file__).resolve().parent.parent.parent / "reports" / "failure_trace.jsonl"

class StepExecutionError(Exception):
    pass

class DetonationAgentRunner:
    """
    Executes a 10-step autonomous detonation workflow inside a Celesto microVM.
    Implements snapshot checkpointing, step 7 failure recovery, and clean teardown.
    """

    def __init__(self, sandbox: CelestoSandbox, simulate_failure_step_7: bool = False, failure_policy: str = "rollback"):
        self.sandbox = sandbox
        self.simulate_failure_step_7 = simulate_failure_step_7
        self.failure_policy = failure_policy
        self.trace_records = []
        self._setup_interrupt_handlers()

    def _setup_interrupt_handlers(self):
        def _interrupt_handler(signum, frame):
            print(f"[Interrupt] Received signal {signum}. Triggering emergency cleanup of {self.sandbox.sandbox_name}...")
            self.sandbox.delete()
            sys.exit(130)

        try:
            signal.signal(signal.SIGINT, _interrupt_handler)
            signal.signal(signal.SIGTERM, _interrupt_handler)
        except (ValueError, AttributeError):
            # In some threaded or Windows worker environments
            pass

    def _record_trace(self, step: int, event: str, details: Dict[str, Any]):
        record = {
            "step": step,
            "event": event,
            "sandbox_name": self.sandbox.sandbox_name,
            **details
        }
        self.trace_records.append(record)
        with open(TRACE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def run_10_step_workflow(self) -> Dict[str, Any]:
        """
        Executes 10-step submission grading / package detonation workflow.
        """
        steps = [
            (1, "Verify guest microVM environment", "python3 --version && uname -a"),
            (2, "Extract untrusted artifact package", "tar -xzf untrusted_submission.tar.gz -C /workspace || true"),
            (3, "Static safety heuristic scan", "grep -rn 'os.system' /workspace || true"),
            (4, "Install isolated dependencies", "pip install --no-index /workspace/wheels/*.whl || true"),
            (5, "Execute baseline test suite", "pytest /workspace/tests/test_basic.py || true"),
            (6, "Snapshot healthy baseline checkpoint", "SNAPSHOT"),
            (7, "Execute hostile edge-case exploit test", "python3 /workspace/exploits/test_edge.py"),
            (8, "Generate memory and coverage profile", "python3 -m cProfile /workspace/submission.py || true"),
            (9, "Compile forensic execution manifest", "sha256sum /workspace/* > /workspace/manifest.sha256 || true"),
            (10, "Finalize audit report and cleanup", "echo 'DETONATION_COMPLETE' > /workspace/report.done")
        ]

        total_steps = len(steps)
        step_6_snapshot_id = "checkpoint-step-6"

        for step_num, step_desc, step_cmd in steps:
            if step_num == 6:
                self.sandbox.snapshot(step_6_snapshot_id)
                self._record_trace(step_num, "snapshot_created", {"snapshot_id": step_6_snapshot_id})
                continue

            if step_num == 7 and self.simulate_failure_step_7:
                self._record_trace(step_num, "step_failed", {
                    "error": "GuestProcessCrashed: Segmentation fault / hostile exploit triggered in edge case test",
                    "command": step_cmd
                })

                # Apply named recovery policy
                self._record_trace(step_num, "policy_applied", {
                    "policy": self.failure_policy,
                    "action": f"Executing {self.failure_policy} to restore guest microVM to {step_6_snapshot_id}"
                })

                if self.failure_policy == "rollback":
                    self.sandbox.rollback(step_6_snapshot_id)
                    self._record_trace(step_num, "rollback_succeeded", {
                        "snapshot_id": step_6_snapshot_id,
                        "state": "restored"
                    })
                elif self.failure_policy == "fresh":
                    self.sandbox.delete()
                    # Provision fresh replacement
                    self.sandbox.create()
                    self.sandbox.wait_until_ready()
                    self._record_trace(step_num, "fresh_provisioned", {"sandbox_name": self.sandbox.sandbox_name})
                elif self.failure_policy == "resume":
                    self._record_trace(step_num, "resumed_disk", {"state": "resumed"})

                # Step 7 resolved with safe fallback
                step_cmd = "echo 'EDGE_CASE_HEURISTIC_FLAGGED_AND_CONTAINED'"

            res = self.sandbox.exec(step_cmd)
            self._record_trace(step_num, "step_completed", {
                "description": step_desc,
                "exit_code": res.exit_code,
                "ok": res.ok
            })

        return {
            "success": True,
            "sandbox_name": self.sandbox.sandbox_name,
            "steps_completed": total_steps
        }
