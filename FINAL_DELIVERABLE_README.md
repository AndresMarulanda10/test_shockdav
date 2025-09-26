Final deliverable — Bitget futures orders extraction (summary)

Goal
- Implement a scalable pipeline (FastAPI control plane, Coordinator Lambda, Step Functions Map, Worker Lambda, Collector Lambda) that extracts a user's Bitget futures orders and produces a single chronological JSON and elapsed time.

Repository status (what I implemented)
- FastAPI control plane: `src/fastapi_app/main.py` — start, status, download endpoints (local coordinator used when running locally).
- Coordinator Lambda: `src/lambdas/coordinator/handler.py` — accepts symbols OR auto-detects symbols by scanning Bitget `orders-history` (idLessThan pagination). Builds state machine input with `startTimeMs` and `productType`.
- Worker Lambda: `src/lambdas/worker/app.py` — paginates `limit=100`, idLessThan; enforces per-worker throttle (0.8s); added retry/backoff (5 attempts) for 429/5xx; uploads to S3 when payload large.
- Aggregator Lambda: `src/lambdas/aggregator/handler.py` — merges per-symbol results, sorts chronologically, writes final JSON to S3 with key using `startTimeMs` and optional `executionArn`, returns `elapsedSeconds`.
- Bitget client: `src/lambdas/common/bitget_client.py` — HMAC signing, supports GET and POST probes, ms/seconds timestamps.
- CDK infra: `infra/bitget_stack.py` — builds S3, Secrets Manager secret, Lambdas, Step Functions ASL from `step_functions/init.json` or programmatic fallback. Grants least-privilege roles.
- DB helpers: `app/models/database.py` — SQLAlchemy models + `save_execution_result` and `save_orders_bulk` helpers (optional integration).
- Scripts: `scripts/real_extract_full.py` and `scripts/run_probe_batch.py` for local runs and probing.

What I validated locally
- Unit tests and smoke scripts (local) updated earlier and import checks pass for the modules.
- Ran a curated local extraction (see artifact below). Worker retries and aggregator elapsedSeconds executed.

Sample artifact produced locally
- artifacts/bitget-orders-1758852265-orders.json
  - Content (sample run): {"generated_at": "2025-09-26T02:04:25Z", "orders": [], "count": 0}
  - Note: zero orders in this sample run. Causes: either the provided credentials have no orders for those symbols, or Bitget requires a different request shape to fetch futures history. See "Blockers" below.

Blockers and next steps to finalize the live extraction
- Bitget API discovery: during aggressive probing many `orders-history` variants returned HTTP 400. Without a working request shape (exact path, param names and productType), automatic detection/extraction returns empty results.
- To finish and produce the expected >17K orders <60s credential-based run you must either:
  1. Provide a sanitized working request/response (curl or example) that returns orders for the account; or
  2. Allow me to run a broader probe sweep (more endpoints and higher caps) — this will be noisier and takes longer; or
  3. If testing on your AWS account, deploy CDK (below) and run the Map in parallel — but still needs the correct Bitget request shape.

How to run locally (quick smoke)
- Create and activate venv (Python 3.11 recommended):

  python3.11 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt

- Quick curated extraction (uses env vars and local worker/aggregator code):

  export BITGET_API_KEY=bg_680026a00a63d58058c738c952ce67a2
  export BITGET_API_SECRET=7abac4a9404e82830db5f9db5e867a8370c7e59dc74e52615c59552d0afbd7c9
  export BITGET_API_PASSPHRASE=22Dominic22
  export CURATED_SYMBOLS='BTCUSDT,ETHUSDT,LTCUSDT'
  python -m scripts.real_extract_full

- To run the probe sweep (discovers symbols):

  python -m scripts.run_probe_batch

How to deploy to AWS (CDK)
- From `infra/`:

  npm install -g aws-cdk@2
  cd infra
  cdk bootstrap aws://<ACCOUNT_ID>/<REGION>
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  cdk synth
  cdk deploy --require-approval never

- After deploy, CDK outputs will include the S3 bucket and StateMachineArn. Set `STATE_MACHINE_ARN` and `RESULTS_BUCKET` as env vars for local FastAPI or let the deployed Lambdas have them.

How to validate Step Functions parallelism
- Start an execution (via FastAPI `/start` or AWS console). In the Step Functions console open the execution and inspect the Map state — it will show parallel iterators; MaxConcurrency is set in the ASL or by the CDK state.

What I'll deliver in the final handoff
- The codebase in this repo (this branch) with working Lambdas and ASL.
- Local scripts to reproduce extraction behavior and to probe Bitget API shapes.
- A short demo plan for the live call (what to show in the console, sample commands).

Recommended immediate actions for you (pick one)
- Provide a sanitized working Bitget request/response for futures order history so I can adapt the client and re-run a full extraction.
- Permit a broader probe sweep (I will run more endpoint variants and raise probe caps; I recommend probes_per_symbol=48 and test 50 market symbols). I can run it and report exact successful request shape if found.
- If you prefer to proceed without live Bitget probing, I can prepare the CDK deployment artifacts and the final README + screenshots you can use in the interview, and mark the task as "blocked on live credentials/endpoint shape".

If you want me to continue, tell me which of the three options above you choose and I'll act immediately.
