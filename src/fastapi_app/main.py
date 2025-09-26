from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Body, Query, Path
from dotenv import load_dotenv
from typing import Optional, Any, Dict
import os
import json

load_dotenv()

app = FastAPI(
    title="Bitget Orders API",
    version="1.0.0",
    description="API for managing Bitget orders",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/start")
def start_execution(body: Optional[Dict[str, Any]] = Body(None)):
    """Start a coordinator / state machine execution.

    Behavior:
    - If a local `coordinator` handler exists (during local testing), call it directly.
    - Otherwise, if STATE_MACHINE_ARN is configured, start execution via Step Functions.
    """
    # Prefer local coordinator handler when available
    try:
        from src.lambdas.coordinator.handler import handler as coordinator_handler
    except Exception:
        coordinator_handler = None

    # Normalize input
    payload = body or {}

    # If local coordinator is available, call it (useful for local testing)
    if coordinator_handler:
        resp = coordinator_handler(payload, None)
        return resp

    # Otherwise attempt to start a Step Functions execution
    state_machine_arn = os.environ.get("STATE_MACHINE_ARN")
    if not state_machine_arn:
        raise HTTPException(status_code=500, detail="No coordinator available and STATE_MACHINE_ARN not configured")

    import boto3
    sf = boto3.client("stepfunctions")
    input_obj = payload
    if "startTimeMs" not in input_obj:
        input_obj["startTimeMs"] = int(__import__("time").time() * 1000)

    try:
        res = sf.start_execution(stateMachineArn=state_machine_arn, input=json.dumps(input_obj))
        return {"statusCode": 202, "executionArn": res.get("executionArn")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status/{execution_arn}")
def get_status(execution_arn: str = Path(..., description="Step Functions execution ARN")):
    """Return Step Functions execution status if available."""
    import boto3
    try:
        sf = boto3.client("stepfunctions")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"boto3 client error: {e}")

    try:
        resp = sf.describe_execution(executionArn=execution_arn)
        return {"status": resp.get("status"), "output": resp.get("output"), "startDate": str(resp.get("startDate"))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download")
def download(key: str = Query(..., description="S3 object key to download")):
    """Return a presigned URL to download the final JSON from S3.

    Requires `RESULTS_BUCKET` env var to be set.
    """
    bucket = os.environ.get("RESULTS_BUCKET")
    if not bucket:
        raise HTTPException(status_code=400, detail="RESULTS_BUCKET not configured")

    try:
        import boto3
        s3 = boto3.client("s3")
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=600,
        )
        return {"presigned_url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
