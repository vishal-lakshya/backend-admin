import gzip
import json
from io import BytesIO
from typing import Any

import boto3

from app.admin.config import settings


def _s3_bucket():
    s3 = boto3.resource(
        's3',
        region_name=settings.AWS_REGION,
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
    )
    return s3.Bucket(settings.AWS_S3_BUCKET_QUESTIONS)


def test_questions_object_key(test_id: int) -> str:
    prefix = settings.AWS_S3_TESTS_PREFIX
    if prefix and not prefix.endswith('/'):
        prefix = f'{prefix}/'
    return f'{prefix}{test_id}/questions.ndjson.gz'


def save_test_question_payloads(test_id: int, payloads: list[dict[str, Any]]) -> str:
    buffer = BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode='wb') as gz:
        for payload in payloads:
            gz.write(json.dumps(payload, ensure_ascii=True).encode('utf-8'))
            gz.write(b'\n')

    key = test_questions_object_key(test_id)
    _s3_bucket().put_object(
        Key=key,
        Body=buffer.getvalue(),
        ContentType='application/x-ndjson',
        ContentEncoding='gzip',
    )
    return key


def load_test_question_payloads(test_id: int) -> list[dict[str, Any]]:
    key = test_questions_object_key(test_id)
    obj = _s3_bucket().Object(key).get()
    raw = obj['Body'].read()
    with gzip.GzipFile(fileobj=BytesIO(raw), mode='rb') as gz:
        content = gz.read().decode('utf-8')
    rows: list[dict[str, Any]] = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows
