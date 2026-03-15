import gzip
import json
from io import BytesIO
import re
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


def pyq_generated_pdf_object_key(pyq_id: int) -> str:
    return f'{_prefix()}{pyq_id}/generated/user-paper.pdf'


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


def save_generated_pyq_pdf(pyq_id: int, pdf_bytes: bytes) -> str:
    key = pyq_generated_pdf_object_key(pyq_id)
    _bucket().put_object(
        Key=key,
        Body=pdf_bytes,
        ContentType='application/pdf',
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


def build_pyq_pdf_file_name(title: str, year: int | None) -> str:
    label = f'{title or "pyq-paper"}-{year or ""}'.strip('-').lower()
    label = re.sub(r'[^a-z0-9]+', '-', label).strip('-') or 'pyq-paper'
    return f'{label}.pdf'


def _pdf_escape(text: str) -> str:
    return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _wrap_line(text: str, width: int = 92) -> list[str]:
    raw = ' '.join(str(text or '').split())
    if not raw:
        return ['']
    words = raw.split(' ')
    lines: list[str] = []
    current = ''
    for word in words:
        candidate = word if not current else f'{current} {word}'
        if len(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines or ['']


def _render_pdf_page(lines: list[tuple[str, int]]) -> bytes:
    chunks = ['BT', '/F1 11 Tf']
    y = 805
    for text, indent in lines:
        safe = _pdf_escape(text)
        x = 50 + indent
        chunks.append(f'1 0 0 1 {x} {y} Tm ({safe}) Tj')
        y -= 16
    chunks.append('ET')
    return '\n'.join(chunks).encode('latin-1', errors='replace')


def build_pyq_pdf_bytes(
    *,
    title: str,
    exam_name: str,
    year: int | None,
    paper_type: str | None,
    paper_set: str | None,
    questions: list[dict[str, Any]],
) -> bytes:
    page_capacity = 46
    lines: list[tuple[str, int]] = []

    def add_block(text: str, indent: int = 0, blank_after: bool = False) -> None:
        for line in _wrap_line(text):
            lines.append((line, indent))
        if blank_after:
            lines.append(('', 0))

    add_block(title or 'PYQ Paper')
    add_block(
        ' | '.join(
            [
                part for part in [
                    exam_name or 'Exam',
                    str(year) if year else '',
                    paper_type or '',
                    paper_set or '',
                ] if part
            ]
        ),
        blank_after=True,
    )

    for idx, question in enumerate(questions, start=1):
        add_block(f'Q{idx}. {question.get("question_text", "")}', blank_after=False)
        for option in question.get('options', []) or []:
            add_block(f'{option.get("key", "")}. {option.get("text", "")}', indent=18)
        correct = str(question.get('correct_option') or '').strip()
        if correct:
            add_block(f'Answer: {correct}', indent=18)
        explanation = str(question.get('explanation') or '').strip()
        if explanation:
            add_block(f'Explanation: {explanation}', indent=18)
        lines.append(('', 0))

    if not lines:
        add_block('No questions available.')

    pages: list[list[tuple[str, int]]] = []
    for start in range(0, len(lines), page_capacity):
        pages.append(lines[start:start + page_capacity])

    objects: list[bytes] = []
    objects.append(b'<< /Type /Catalog /Pages 2 0 R >>')
    kids = ' '.join(f'{4 + (idx * 2)} 0 R' for idx in range(len(pages)))
    objects.append(f'<< /Type /Pages /Count {len(pages)} /Kids [{kids}] >>'.encode('latin-1'))
    objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')

    for idx, page in enumerate(pages):
        page_obj = 4 + (idx * 2)
        content_obj = page_obj + 1
        objects.append(
            f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>'.encode('latin-1')
        )
        stream = _render_pdf_page(page)
        objects.append(
            b'<< /Length ' + str(len(stream)).encode('latin-1') + b' >>\nstream\n' + stream + b'\nendstream'
        )

    output = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f'{index} 0 obj\n'.encode('latin-1'))
        output.extend(obj)
        output.extend(b'\nendobj\n')

    xref_pos = len(output)
    output.extend(f'xref\n0 {len(objects) + 1}\n'.encode('latin-1'))
    output.extend(b'0000000000 65535 f \n')
    for offset in offsets[1:]:
        output.extend(f'{offset:010d} 00000 n \n'.encode('latin-1'))
    output.extend(
        f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF'.encode('latin-1')
    )
    return bytes(output)
