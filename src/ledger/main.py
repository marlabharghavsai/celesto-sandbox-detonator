import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from src.ledger.schemas import RunCreate, RunResponse
from src.ledger.database import init_db, get_all_runs, insert_run

app = FastAPI(title="Celesto Run Ledger API", version="1.0.0")

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        errors.append({
            "loc": [str(x) for x in err.get("loc", [])],
            "msg": str(err.get("msg", "")),
            "type": str(err.get("type", ""))
        })
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": errors, "message": "Validation error"}
    )

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc), "message": "Value error"}
    )

@app.get("/health")
def get_health():
    return {"status": "ok"}

@app.get("/api/runs")
def list_runs():
    runs = get_all_runs()
    return runs

@app.post("/api/runs", status_code=status.HTTP_201_CREATED)
def create_run(run: RunCreate):
    # Extra validation defensive check
    if run.execution_target != "celesto_sandbox":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid execution_target '{run.execution_target}'. Must be 'celesto_sandbox'."
        )
    stored = insert_run(run.model_dump())
    return stored
