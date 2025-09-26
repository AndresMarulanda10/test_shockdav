import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.lambdas.common.aws_helpers import read_json_from_s3, upload_json_to_s3

# Optional DB persistence helpers
try:
    from app.models.database import save_execution_result, save_orders_bulk, get_db_session
    _HAS_DB = True
except Exception:
    _HAS_DB = False

RESULTS_BUCKET = os.environ.get("RESULTS_BUCKET")
RESULTS_PREFIX = os.environ.get("RESULTS_PREFIX", "bitget-orders/")


def _order_time(o: Dict[str, Any]) -> int:
    # Try common fields
    for f in ("orderTime", "timestamp", "time", "createdAt"):
        v = o.get(f)
        if v:
            try:
                return int(v)
            except Exception:
                try:
                    # isoformat parse fallback
                    import dateutil.parser
                    dt = dateutil.parser.parse(v)
                    return int(dt.timestamp() * 1000)
                except Exception:
                    continue
    return 0


def handler(event, context):
    # event can be: {"results": [...] } or a list of items
    items = event.get("results") if isinstance(event, dict) and "results" in event else (event if isinstance(event, list) else [event])

    # allow passing startTimeMs and executionArn via the event (optional)
    start_time_ms = event.get("startTimeMs") if isinstance(event, dict) else None
    execution_arn = event.get("executionArn") if isinstance(event, dict) else None

    all_orders: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # if s3_key provided, read from S3
        key = item.get("s3_key") or item.get("s3Key")
        if key and RESULTS_BUCKET:
            try:
                data = read_json_from_s3(RESULTS_BUCKET, key)
                orders = data.get("orders") or []
            except Exception:
                orders = []
        else:
            orders = item.get("orders") or []

        if isinstance(orders, list):
            all_orders.extend(orders)

    # sort ascending by time then write final aggregated JSON
    all_orders.sort(key=_order_time)

    now = datetime.now(timezone.utc)

    # build final key using startTimeMs and executionArn when available per tasks.md
    if start_time_ms:
        key_base = f"{RESULTS_PREFIX.rstrip('/')}/{start_time_ms}"
        if execution_arn:
            # sanitize execution arn for filename
            safe_exec = execution_arn.replace(':', '_').replace('/', '_')
            final_key = f"{key_base}-{safe_exec}.json"
        else:
            final_key = f"{key_base}.json"
    else:
        final_key = f"{RESULTS_PREFIX.rstrip('/')}/{now.strftime('%Y/%m/%d/%H-%M-%SZ')}.json"

    final_obj = {"generated_at": now.isoformat(), "orders": all_orders, "count": len(all_orders)}

    elapsed_seconds = None
    if start_time_ms:
        try:
            elapsed_seconds = (int(now.timestamp() * 1000) - int(start_time_ms)) / 1000.0
            final_obj["elapsedSeconds"] = elapsed_seconds
        except Exception:
            pass

    if RESULTS_BUCKET:
        upload_json_to_s3(RESULTS_BUCKET, final_key, final_obj)

    # Persist to DB if available (best-effort - do not fail the lambda on DB errors)
    if _HAS_DB:
        try:
            session = get_db_session()
            if session:
                # save execution result summary
                try:
                    er = save_execution_result(session, execution_arn or final_key, "SUCCEEDED", total_symbols=len(items), total_orders=len(all_orders), s3_uri=f"s3://{RESULTS_BUCKET}/{final_key}" if RESULTS_BUCKET else None, result_data=json.dumps({"count": len(all_orders)}), processing_time_seconds=elapsed_seconds)
                    session.commit()
                except Exception:
                    try:
                        session.rollback()
                    except Exception:
                        pass

                # Save orders in bulk (deduplicated by database constraint)
                try:
                    inserted = save_orders_bulk(session, execution_arn or final_key, all_orders)
                    session.commit()
                except Exception:
                    try:
                        session.rollback()
                    except Exception:
                        pass
        except Exception:
            # Do not let DB failures break the aggregator
            pass

    out = {"status": "ok", "final_key": final_key, "count": len(all_orders)}
    if elapsed_seconds is not None:
        out["elapsedSeconds"] = elapsed_seconds
    return out
