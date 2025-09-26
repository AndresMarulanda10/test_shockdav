Submission notes

This repository implements a Bitget Futures orders extraction prototype with the following components:

- FastAPI control plane (local), Bitget signed client (HMAC-SHA256), coordinator/worker/aggregator Lambda handlers, and local probe/extraction scripts.
- Worker supports pagination, retries with backoff, and throttling. Aggregator merges per-symbol results, sorts orders chronologically and writes a single JSON artifact to `artifacts/` and optionally persists to a database if configured.

Local execution

- To reproduce the local extraction run that was used during development:

  1. Install dependencies (preferably in a venv):

     python3 -m venv .venv
     source .venv/bin/activate
     pip install -r requirements.txt

  2. Export test credentials (only for local testing):

     export BITGET_API_KEY=...
     export BITGET_API_SECRET=...
     export BITGET_API_PASSPHRASE=...

  3. Run the probe+extraction script (this will write to `artifacts/`):

     python3 scripts/real_extract_full.py

Result from local run included with this submission

- File: artifacts/bitget-orders-1758854030-orders.json
- Content summary: generated JSON with timestamp and `orders` list.
- Note: In the development environment the generated JSON contained `count: 0` (no orders) because the provided test credentials did not return accessible orders via the endpoint variants probed.

Limitations and next steps

- The >17k orders in <60s performance goal requires deploying the Step Functions Map + Lambda parallel pipeline on AWS and running it against an account with sufficient order history. This repository provides the Lambda handlers and a CDK skeleton; deployment was not executed here.

- If desired, I can:
  - Run a final, broader probe sweep to find the exact private endpoint/parameter shape if you can provide a sanitized successful request/response.
  - Prepare CDK deployment assets and a short deployment guide to validate the performance target on AWS.

Notes

- This submission intentionally removes development comments and emojis; code lint warnings were addressed where low-risk and straightforward.
