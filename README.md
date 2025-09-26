# Bitget Futures Orders Extraction

This repository contains a fully‑functional solution that extracts all Futures orders from Bitget using AWS Lambda, Step Functions, and FastAPI. The architecture follows the technical test requirements and is ready for deployment.

## Architecture Overview

```
+-------------------+      +-------------------+      +-------------------+
|  FastAPI API     | ---\u003e |  Coordinator Lambda | ---\u003e |  Step Functions   |
+-------------------+      +-------------------+      +-------------------+
                                            |
                                            |  Map (MaxConcurrency=8)
                                            v
                                    +-------------------+
                                    |  Worker Lambda    |
                                    +-------------------+
                                            |
                                            v
                                    +-------------------+
                                    |  Collector Lambda |
                                    +-------------------+
                                            |
                                            v
                                    +-------------------+
                                    |  S3 Bucket        |
                                    +-------------------+
```

- **FastAPI** exposes two endpoints: `/start` to trigger the extraction and `/status/{executionArn}` to query the Step Functions state.
- **Coordinator Lambda** discovers all user symbols, starts the Step Functions execution.
- **Worker Lambda** fetches all orders for a single symbol, handling pagination, throttling, and retries.
- **Collector Lambda** merges all results, sorts them chronologically, and uploads the final JSON to S3.

## Prerequisites

- Python 3.11
- Node.js (for CDK)
- AWS CLI configured with a user that has permissions to create CDK stacks, Lambda, Step Functions, S3, Secrets Manager, and IAM.

## Local Setup

```bash
# Install CDK
npm install -g aws-cdk@2

# Create and activate virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r infra/requirements.txt
pip install -r src/fastapi_app/requirements.txt
```

## Deploying the Infrastructure

```bash
cd infra
cdk bootstrap aws://\u003cACCOUNT_ID\u003e/\u003cREGION\u003e
cdk synth
cdk deploy --require-approval never
```

The CDK stack will create:
- An S3 bucket for the final JSON.
- A Secrets Manager secret named `bitget/credentials` (you must create it manually with your Bitget API keys).
- Three Lambda functions with the appropriate IAM roles.
- A Step Functions state machine with a Map state.

## Running the FastAPI API

```bash
cd src/fastapi_app
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Using the API

1. **Start extraction**
   ```http
   POST http://localhost:8000/start
   ```
   Response: `{ "executionArn": "...", "startTimeMs": 169... }`

2. **Check status**
   ```http
   GET http://localhost:8000/status/\u003cexecutionArn\u003e
   ```

3. **Download result**
   ```http
   GET http://localhost:8000/download?key=bitget-orders/169...-orders.json
   ```

## Validation Checklist

- Step Functions Map state shows parallel executions (MaxConcurrency=8).
- CloudWatch logs confirm no more than 10 requests per second across all workers.
- Final JSON contains \u003e17 000 orders and is sorted by `cTime`.
- Total extraction time reported by Collector is \u003c 60 s.

## Notes

- Bitget may limit historical data to 90 days via API. For older data, export from the UI and process the CSV.
- If your account has limited Lambda concurrency, request an increase from AWS.

---

Happy coding!
