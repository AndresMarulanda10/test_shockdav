"""Small AWS helpers used by Lambdas: S3 read/write and Secrets Manager read.

These are intentionally tiny wrappers to centralize boto3 usage and make testing easier.
"""

from typing import Any, Dict, Optional
import json


def get_s3_client():
    """Return a boto3 S3 client. In real code, configure retries, region, etc."""
    import boto3

    return boto3.client("s3")


def read_json_from_s3(bucket: str, key: str) -> Dict[str, Any]:
    s3 = get_s3_client()
    obj = s3.get_object(Bucket=bucket, Key=key)
    return json.loads(obj["Body"].read())


def upload_json_to_s3(bucket: str, key: str, data: Any) -> None:
    s3 = get_s3_client()
    s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(data, default=str).encode("utf-8"))


def get_secret(secret_name: str, region_name: Optional[str] = None) -> Dict[str, Any]:
    """Read a Secrets Manager secret and return parsed JSON or {} on failure.

    Returns an empty dict if the secret is missing or not JSON.
    """
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client("secretsmanager", region_name=region_name)
    try:
        val = client.get_secret_value(SecretId=secret_name)
        if "SecretString" in val and val["SecretString"]:
            try:
                return json.loads(val["SecretString"])
            except (ValueError, TypeError):
                # If secret is plain string rather than JSON, return wrapped
                return {"secret": val["SecretString"]}
    except ClientError:
        return {}
    return {}
