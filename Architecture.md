repo-root/
├─ infra/          # CDK infrastructure (Python)
│  ├─ app.py
│  ├─ bitget_stack.py
│  └─ requirements.txt
├─ src/            # Application source
│  ├─ fastapi_app/
│  │  └─ main.py          # FastAPI entry‑point
│  ├─ lambdas/
│  │  ├─ coordinator/
│  │  │  └─ handler.py
│  │  ├─ worker/
│  │  │  └─ handler.py
│  │  ├─ aggregator/
│  │  │  └─ handler.py
│  │  ├─ collector/
│  │  │  └─ handler.py
│  │  ├─ common/
│  │  │  ├─ bitget_client.py
│  │  │  └─ aws_helpers.py
│  │  └─ __init__.py
│  └─ __init__.py
├─ tests/          # Unit‑test stubs
│  └─ __init__.py
├─ app/            # Existing FastAPI code (kept for backward compatibility)
│  ├─ main.py
│  ├─ api/
│  │  └─ routes/
│  │      ├─ orders.py
│  │      ├─ health.py
│  │      └─ symbols.py
│  ├─ services/
│  │  ├─ orders_service.py
│  │  ├─ database_service.py
│  │  └─ symbols_service.py
│  └─ core/
│      └─ config.py
├─ lambda_functions/   # Legacy Lambda code (kept for reference)
│  ├─ aggregator/
│  │  └─ app.py
│  ├─ coordinator/
│  │  └─ app.py
│  └─ worker/
│      └─ app.py
├─ scripts/
│  ├─ init_db.py
│  ├─ start.py
│  └─ __init__.py
├─ step_functions/
│  └─ init.json
├─ tasks.md
├─ README.md
├─ .gitignore
├─ requirements.txt
└─ requirements-freeze.txt
