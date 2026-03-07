import gzip
import json
from io import BytesIO
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.admin.config import settings


def get_questions_bucket():
    s3 = boto3.resource(
        's3',
        region_name=settings.AWS_REGION,
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
    )
    return s3.Bucket(settings.AWS_S3_BUCKET_QUESTIONS)


def questions_object_key() -> str:
    return settings.AWS_S3_QUESTIONS_OBJECT_KEY.strip('/')


def _read_object_bytes() -> bytes | None:
    bucket = get_questions_bucket()
    key = questions_object_key()
    try:
        obj = bucket.Object(key).get()
    except ClientError as exc:
        if exc.response.get('Error', {}).get('Code') in {'NoSuchKey', '404'}:
            return None
        raise
    return obj['Body'].read()


def _write_object_bytes(payload: bytes) -> None:
    bucket = get_questions_bucket()
    bucket.put_object(
        Key=questions_object_key(),
        Body=payload,
        ContentType='application/x-ndjson',
        ContentEncoding='gzip',
    )


def _serialize_rows(items: list[dict[str, Any]]) -> bytes:
    buffer = BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode='wb') as gz:
        for item in items:
            gz.write(json.dumps(item, ensure_ascii=True).encode('utf-8'))
            gz.write(b'\n')
    return buffer.getvalue()


def _deserialize_rows(payload: bytes | None) -> list[dict[str, Any]]:
    if not payload:
        return []

    with gzip.GzipFile(fileobj=BytesIO(payload), mode='rb') as gz:
        raw = gz.read().decode('utf-8')

    items: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        if isinstance(data, dict):
            items.append(data)
    return items


def _read_rows() -> list[dict[str, Any]]:
    return _deserialize_rows(_read_object_bytes())


def _write_rows(items: list[dict[str, Any]]) -> None:
    _write_object_bytes(_serialize_rows(items))


def add_manual_question_payload(payload: dict[str, Any]) -> None:
    items = _read_rows()
    items.append(payload)
    _write_rows(items)


def save_bulk_question_payloads(_: str, payloads: list[dict[str, Any]]) -> str:
    items = _read_rows()
    items.extend(payloads)
    _write_rows(items)
    return questions_object_key()


def load_question_payload(question_id: str) -> dict[str, Any] | None:
    for item in _read_rows():
        if str(item.get('id')) == question_id:
            return item
    return None


def update_question_payload(question_id: str, payload: dict[str, Any]) -> None:
    items = _read_rows()
    updated = False
    for idx, item in enumerate(items):
        if str(item.get('id')) == question_id:
            items[idx] = payload
            updated = True
            break
    if not updated:
        raise KeyError(question_id)
    _write_rows(items)


def delete_question_payload(question_id: str) -> None:
    items = _read_rows()
    next_items = [item for item in items if str(item.get('id')) != question_id]
    if len(next_items) == len(items):
        raise KeyError(question_id)
    _write_rows(next_items)


def list_question_payloads() -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in _read_rows():
        question_id = str(item.get('id') or '')
        if question_id:
            deduped[question_id] = item
    return list(deduped.values())
