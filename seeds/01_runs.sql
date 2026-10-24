CREATE TABLE IF NOT EXISTS runs (
    run_id VARCHAR(64) PRIMARY KEY,
    sandbox_name VARCHAR(64) NOT NULL UNIQUE,
    problem_id VARCHAR(64) NOT NULL,
    state VARCHAR(32) NOT NULL,
    execution_target VARCHAR(32) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_runs_sandbox_name ON runs(sandbox_name);

INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target)
VALUES ('run-seeddemo1', 'sbx-seeddemo1', 'problem-detonator-001', 'deleted', 'celesto_sandbox')
ON CONFLICT (run_id) DO NOTHING;
