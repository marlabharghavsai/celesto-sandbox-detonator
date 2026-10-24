import os
import re
import json
import math
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from src.ledger.main import app

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 1. Trusted Control Plane
def test_docker_compose_and_dockerfile():
    compose_path = PROJECT_ROOT / "docker-compose.yml"
    dockerfile_path = PROJECT_ROOT / "Dockerfile"
    seeds_path = PROJECT_ROOT / "seeds" / "01_runs.sql"

    assert compose_path.exists(), "docker-compose.yml missing"
    assert dockerfile_path.exists(), "Dockerfile missing"
    assert seeds_path.exists(), "seeds/01_runs.sql missing"

    compose_text = compose_path.read_text(encoding="utf-8")

    # Confirm api and ledger services
    assert "api:" in compose_text
    assert "ledger:" in compose_text

    # Confirm healthchecks for both services with required fields
    assert "healthcheck:" in compose_text
    assert "interval:" in compose_text
    assert "timeout:" in compose_text
    assert "retries:" in compose_text
    assert "start_period:" in compose_text

    # Confirm ledger uses pg_isready and mounts ./seeds
    assert "pg_isready" in compose_text
    assert "./seeds:" in compose_text or "seeds" in compose_text

    # Confirm api healthcheck curls /health and depends on ledger
    assert "http://localhost:8080/health" in compose_text or "8080/health" in compose_text
    assert "service_healthy" in compose_text

    # Confirm seed SQL has sbx-seeddemo1, deleted, celesto_sandbox, and idempotency
    seed_sql = seeds_path.read_text(encoding="utf-8")
    assert "sbx-seeddemo1" in seed_sql
    assert "deleted" in seed_sql
    assert "celesto_sandbox" in seed_sql
    assert "ON CONFLICT" in seed_sql

# 2. Environment Variables
def test_env_example():
    env_example_path = PROJECT_ROOT / ".env.example"
    env_path = PROJECT_ROOT / ".env"

    assert env_example_path.exists(), ".env.example missing"
    assert not env_path.exists(), ".env should NOT exist in repository submission"

    content = env_example_path.read_text(encoding="utf-8")
    required_keys = [
        "CELESTO_PROVIDER",
        "CELESTO_API_KEY",
        "CELESTO_BACKEND",
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "DATABASE_URL",
        "API_PORT"
    ]
    for key in required_keys:
        assert f"{key}=" in content, f"Missing required env key: {key}"

    # Confirm values are placeholders, not live provider keys
    for line in content.splitlines():
        if "API_KEY" in line:
            assert "replace" in line.lower() or "dummy" in line.lower()

# 3. Problem Statement
def test_problem_report():
    problem_path = PROJECT_ROOT / "reports" / "problem.json"
    assert problem_path.exists()

    with open(problem_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for field in ["who", "agent_work", "proof_output", "idea_source"]:
        assert field in data, f"Missing {field} in problem.json"

    assert len(data["who"]) >= 40, f"who is shorter than 40 chars: {len(data['who'])}"
    assert len(data["agent_work"]) >= 40, f"agent_work is shorter than 40 chars: {len(data['agent_work'])}"
    assert len(data["proof_output"]) >= 20, f"proof_output is shorter than 20 chars: {len(data['proof_output'])}"
    assert data["idea_source"] in ["idea_bank", "original"], f"Invalid idea_source: {data['idea_source']}"

# 4. Command Audit Log
def test_command_audit_log():
    log_path = PROJECT_ROOT / "logs" / "commands.jsonl"
    assert log_path.exists(), "logs/commands.jsonl missing"

    sbx_regex = re.compile(r"^sbx-[a-z0-9]{8,}$")
    lines = [line.strip() for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) > 0, "commands.jsonl is empty"

    has_blocked = False
    for i, line in enumerate(lines):
        record = json.loads(line)
        assert "ts" in record and isinstance(record["ts"], str), f"Line {i} missing ts"
        assert sbx_regex.match(record["sandbox_name"]), f"Line {i} invalid sandbox_name: {record['sandbox_name']}"
        assert record["command"] and isinstance(record["command"], str), f"Line {i} invalid command"
        assert record["decision"] in ["allow", "block"], f"Line {i} invalid decision: {record['decision']}"
        assert record["execution_target"] == "celesto_sandbox", f"Line {i} invalid execution_target: {record['execution_target']}"
        if record["decision"] == "block":
            has_blocked = True

    assert has_blocked, "Expected at least one blocked command in commands.jsonl"

# 5. Differentiating Capabilities
def test_capabilities_report():
    cap_path = PROJECT_ROOT / "reports" / "capabilities.json"
    assert cap_path.exists(), "reports/capabilities.json missing"

    with open(cap_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "capabilities" in data
    caps = data["capabilities"]
    assert len(caps) >= 2, "Must contain at least 2 capabilities"

    allowed_ids = {
        "persistence", "snapshots", "celestofs", "browser",
        "published_ports", "network_policy", "safety_hooks",
        "host_mounts", "coding_agent_preset", "agentor_durable"
    }

    ids = [c["id"] for c in caps]
    assert len(ids) == len(set(ids)), "Capability ids must be unique"

    for c in caps:
        assert c["id"] in allowed_ids, f"Disallowed capability id: {c['id']}"
        assert len(c["why"]) >= 80, f"Capability why must be >= 80 characters, got {len(c['why'])}"
        evidence = PROJECT_ROOT / c["evidence_path"]
        assert evidence.exists(), f"Evidence file not found: {c['evidence_path']}"

# 6. Lifecycle Hygiene
def test_lifecycle_report():
    life_path = PROJECT_ROOT / "reports" / "lifecycle.json"
    assert life_path.exists(), "reports/lifecycle.json missing"

    with open(life_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["cleanup_on_success"] is True
    assert data["cleanup_on_failure"] is True
    assert data["cleanup_on_interrupt"] is True

    sbx_regex = re.compile(r"^sbx-[a-z0-9]{8,}$")
    names = data["sandbox_names"]
    assert len(names) > 0, "sandbox_names must not be empty"
    assert len(names) == len(set(names)), "sandbox_names must be unique"

    # Must appear in commands.jsonl or reliability.json
    commands_text = (PROJECT_ROOT / "logs" / "commands.jsonl").read_text(encoding="utf-8")
    rel_data = json.loads((PROJECT_ROOT / "reports" / "reliability.json").read_text(encoding="utf-8"))
    rel_names = {r["sandbox_name"] for r in rel_data["runs"]}

    for name in names:
        assert sbx_regex.match(name), f"Invalid sandbox_name pattern: {name}"
        assert (name in commands_text) or (name in rel_names), f"Sandbox name {name} not found in commands or reliability"

# 7. Reliability Evaluation
def test_reliability_report():
    rel_path = PROJECT_ROOT / "reports" / "reliability.json"
    assert rel_path.exists(), "reports/reliability.json missing"

    with open(rel_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    runs = data["runs"]
    n = len(runs)
    assert data["run_count"] == n
    assert n >= 20, f"Expected at least 20 runs, got {n}"

    sbx_regex = re.compile(r"^sbx-[a-z0-9]{8,}$")
    names = [r["sandbox_name"] for r in runs]
    assert len(names) == len(set(names)), "Run sandbox names must be unique"

    for r in runs:
        assert sbx_regex.match(r["sandbox_name"])
        assert r["fresh"] is True
        assert isinstance(r["success"], bool)
        assert r["wall_clock_s"] >= 0
        assert r["boot_to_ready_s"] >= 0
        assert r["cost_usd"] >= 0

    # Success rate
    expected_success_rate = sum(1 for r in runs if r["success"]) / n
    assert abs(data["success_rate"] - expected_success_rate) <= 0.001

    # Median wall clock: mean of 10th and 11th values in 1-based order
    sorted_wall = sorted([r["wall_clock_s"] for r in runs])
    expected_median_wall = (sorted_wall[n // 2 - 1] + sorted_wall[n // 2]) / 2.0
    assert abs(data["median_wall_clock_s"] - expected_median_wall) <= 0.001

    # p90 wall clock: 18th value for 20 runs
    p90_idx = math.ceil(0.90 * n) - 1
    expected_p90_wall = sorted_wall[p90_idx]
    assert abs(data["p90_wall_clock_s"] - expected_p90_wall) <= 0.001

    # Median boot to ready
    sorted_boot = sorted([r["boot_to_ready_s"] for r in runs])
    expected_median_boot = (sorted_boot[n // 2 - 1] + sorted_boot[n // 2]) / 2.0
    assert abs(data["median_boot_to_ready_s"] - expected_median_boot) <= 0.001

    # Total cost
    expected_total_cost = sum(r["cost_usd"] for r in runs)
    assert abs(data["total_cost_usd"] - expected_total_cost) <= 0.01

    # Postmortem file check
    pm_path = PROJECT_ROOT / data["postmortem_path"]
    assert pm_path.exists(), "postmortem_path file does not exist"
    pm_text = pm_path.read_text(encoding="utf-8")
    assert len(pm_text) >= 200, f"Postmortem must be at least 200 characters, got {len(pm_text)}"

# 8. Containment Test
def test_containment_report():
    cont_path = PROJECT_ROOT / "reports" / "containment.json"
    assert cont_path.exists(), "reports/containment.json missing"

    with open(cont_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["attack"] in ["prompt_injection_exfil", "destructive_command", "suspicious_package"]
    assert data["blocked"] is True
    assert data["host_untouched"] is True
    assert len(data["evidence_paths"]) > 0
    for p in data["evidence_paths"]:
        assert (PROJECT_ROOT / p).exists(), f"Evidence path not found: {p}"

# 9. Failure Recovery Policy
def test_failure_policy_report():
    fail_path = PROJECT_ROOT / "reports" / "failure_policy.json"
    assert fail_path.exists(), "reports/failure_policy.json missing"

    with open(fail_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["failed_step"] == 7
    assert data["total_steps"] == 10
    assert data["policy"] in ["resume", "rollback", "fresh"]
    assert len(data["rationale"]) >= 200

    trace_file = PROJECT_ROOT / data["trace_path"]
    assert trace_file.exists(), "trace_path does not exist"

    lines = [json.loads(line) for line in trace_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    matching = [l for l in lines if l.get("event") == "policy_applied" and l.get("policy") == data["policy"]]
    assert len(matching) > 0, f"No policy_applied line matching policy '{data['policy']}' in trace"

# 10. Concurrency Report
def test_concurrency_report():
    conc_path = PROJECT_ROOT / "reports" / "concurrency.json"
    assert conc_path.exists(), "reports/concurrency.json missing"

    with open(conc_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    jobs = data["jobs"]
    assert len(jobs) >= 5, "Expected at least 5 jobs"

    sbx_regex = re.compile(r"^sbx-[a-z0-9]{8,}$")
    names = [j["sandbox_name"] for j in jobs]
    assert len(names) == len(set(names)), "Concurrent job sandbox names must be unique"

    for j in jobs:
        assert sbx_regex.match(j["sandbox_name"])
        assert len(j["started_at"]) > 0

    assert len(data["breakage_notes"]) >= 40

# 11. Run Ledger API
def test_ledger_api_endpoints():
    from src.ledger.main import get_health, list_runs, create_run
    from src.ledger.schemas import RunCreate
    from fastapi import HTTPException
    from pydantic import ValidationError

    # GET /health
    health_resp = get_health()
    assert health_resp == {"status": "ok"}

    # GET /api/runs
    runs_resp = list_runs()
    assert isinstance(runs_resp, list)
    names = [r["sandbox_name"] for r in runs_resp]
    assert "sbx-seeddemo1" in names, f"Seeded sandbox sbx-seeddemo1 missing from runs: {names}"

    # POST /api/runs - valid (201)
    valid_payload = {
        "run_id": "run-pytest01",
        "sandbox_name": "sbx-pytest0001",
        "problem_id": "problem-pytest-001",
        "state": "running",
        "execution_target": "celesto_sandbox"
    }
    model = RunCreate(**valid_payload)
    created = create_run(model)
    assert created["run_id"] == "run-pytest01"
    assert created["sandbox_name"] == "sbx-pytest0001"

    # POST /api/runs - invalid execution target (e.g. host) must be rejected with 400 / validation error
    bad_target_payload = {
        "run_id": "run-badtarget",
        "sandbox_name": "sbx-pytest0002",
        "problem_id": "problem-pytest-001",
        "state": "running",
        "execution_target": "host"
    }
    with pytest.raises((ValueError, ValidationError, HTTPException)):
        RunCreate(**bad_target_payload)

    # POST /api/runs - invalid state must be rejected with 400 / validation error
    bad_state_payload = {
        "run_id": "run-badstate",
        "sandbox_name": "sbx-pytest0003",
        "problem_id": "problem-pytest-001",
        "state": "unknown_state",
        "execution_target": "celesto_sandbox"
    }
    with pytest.raises((ValueError, ValidationError, HTTPException)):
        RunCreate(**bad_state_payload)

    # POST /api/runs - invalid sandbox_name regex must be rejected with 400 / validation error
    bad_name_payload = {
        "run_id": "run-badname",
        "sandbox_name": "badname",
        "problem_id": "problem-pytest-001",
        "state": "running",
        "execution_target": "celesto_sandbox"
    }
    with pytest.raises((ValueError, ValidationError, HTTPException)):
        RunCreate(**bad_name_payload)

# 12. README Phrases Check
def test_readme_required_phrases():
    readme_path = PROJECT_ROOT / "README.md"
    assert readme_path.exists(), "README.md missing"

    text = readme_path.read_text(encoding="utf-8")
    required_phrases = [
        "Problem statement",
        "How I used Celesto",
        "Eval report",
        "Containment test",
        "State and failure design",
        "Setup"
    ]
    for phrase in required_phrases:
        assert phrase in text, f"README.md missing required phrase: '{phrase}'"
