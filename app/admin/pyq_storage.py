import gzip
import json
from io import BytesIO
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.admin.config import settings


def _bucket():
    s3 = boto3.resource(
        's3',
        region_name=settings.AWS_REGION,
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
    )
    return s3.Bucket(settings.AWS_S3_BUCKET_QUESTIONS)


def _client():
    return boto3.client(
        's3',
        region_name=settings.AWS_REGION,
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
    )


def _prefix() -> str:
    prefix = settings.AWS_S3_PYQ_PREFIX
    if prefix and not prefix.endswith('/'):
        prefix = f'{prefix}/'
    return prefix


def pyq_paper_object_key(pyq_id: int, file_name: str) -> str:
    safe_name = file_name.rsplit('/', 1)[-1]
    return f'{_prefix()}{pyq_id}/paper/{safe_name}'


def pyq_questions_object_key(pyq_id: int) -> str:
    return f'{_prefix()}{pyq_id}/questions.ndjson.gz'


def save_pyq_paper_file(pyq_id: int, file_name: str, file_bytes: bytes, content_type: str | None) -> str:
    key = pyq_paper_object_key(pyq_id, file_name)
    _bucket().put_object(
        Key=key,
        Body=file_bytes,
        ContentType=content_type or 'application/octet-stream',
    )
    return key


def save_pyq_questions(pyq_id: int, payloads: list[dict[str, Any]]) -> str:
    buffer = BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode='wb') as gz:
        for payload in payloads:
            gz.write(json.dumps(payload, ensure_ascii=True).encode('utf-8'))
            gz.write(b'\n')
    key = pyq_questions_object_key(pyq_id)
    _bucket().put_object(
        Key=key,
        Body=buffer.getvalue(),
        ContentType='application/x-ndjson',
        ContentEncoding='gzip',
    )
    return key


def load_pyq_questions(key: str) -> list[dict[str, Any]]:
    try:
        obj = _bucket().Object(key).get()
    except ClientError as exc:
        if exc.response.get('Error', {}).get('Code') in {'NoSuchKey', '404'}:
            return []
        raise
    payload = obj['Body'].read()
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


def create_download_url(key: str, *, file_name: str | None = None) -> str:
    params: dict[str, Any] = {
        'Bucket': settings.AWS_S3_BUCKET_QUESTIONS,
        'Key': key,
    }
    if file_name:
        params['ResponseContentDisposition'] = f'attachment; filename="{file_name}"'
    return _client().generate_presigned_url('get_object', Params=params, ExpiresIn=3600)


def delete_object(key: str | None) -> None:
    if not key:
        return
    try:
        _bucket().Object(key).delete()
    except ClientError as exc:
        if exc.response.get('Error', {}).get('Code') in {'NoSuchKey', '404'}:
            return
        raise
