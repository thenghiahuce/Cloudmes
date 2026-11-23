"""Private, per-account Vanna chat history persisted in PostgreSQL."""
from __future__ import annotations

import re
import uuid
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from psycopg2.extras import RealDictCursor
from backend.db import get_connection

router = APIRouter(prefix='/api/ai-history', tags=['ai-history'])

# Installation is idempotent for existing databases. The same SQL lives in
# migrations/023_ai_chat_history.sql for controlled deployments.
_SCHEMA = '''
CREATE TABLE IF NOT EXISTS ai_conversations (
    id UUID PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    title VARCHAR(180) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ai_conversations_user_updated_idx
    ON ai_conversations(user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS ai_messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL CHECK(role IN ('user','assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ai_messages_conversation_idx
    ON ai_messages(conversation_id, id);
'''

_initialized = False


def _actor(cur, request: Request) -> int:
    username = (request.scope.get('state', {}).get('user') or {}).get('username')
    if not username:
        raise HTTPException(401, 'Vui lòng đăng nhập')
    cur.execute('SELECT id FROM app_users WHERE lower(username)=lower(%s) AND is_active', (username,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(403, 'Tài khoản không hợp lệ')
    return row['id']


def _ensure(cur):
    global _initialized
    if not _initialized:
        cur.execute(_SCHEMA)
        _initialized = True


def _uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, 'Mã cuộc trò chuyện không hợp lệ')


def record_exchange(request: Request, conversation_id: str, question: str, answer: str):
    """Called only after a completed AI response, never with untrusted user IDs."""
    global _initialized
    question = str(question or '').strip()[:12000]
    answer = str(answer or '').strip()[:100000]
    if not question or not answer:
        return
    chat_id = _uuid(conversation_id)
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                _ensure(cur)
                user_id = _actor(cur, request)
                title = re.sub(r'\s+', ' ', question).strip()[:180]
                cur.execute('''INSERT INTO ai_conversations(id,user_id,title)
                    VALUES (%s,%s,%s)
                    ON CONFLICT(id) DO UPDATE SET updated_at=NOW()
                    WHERE ai_conversations.user_id=EXCLUDED.user_id
                    RETURNING id''', (chat_id, user_id, title))
                if not cur.fetchone():
                    raise HTTPException(403, 'Không có quyền truy cập hội thoại')
                # Vanna's stream and the browser completion fallback can both
                # save the same exchange. Avoid duplicating the last pair.
                cur.execute('''SELECT role, content FROM ai_messages
                    WHERE conversation_id=%s ORDER BY id DESC LIMIT 2''', (chat_id,))
                latest = list(reversed(cur.fetchall()))
                if len(latest)==2 and latest[0]['role']=='user' and latest[1]['role']=='assistant' \
                   and latest[0]['content']==question and latest[1]['content']==answer:
                    return
                cur.executemany('''INSERT INTO ai_messages(conversation_id,role,content)
                    VALUES (%s,%s,%s)''', [(chat_id,'user',question),(chat_id,'assistant',answer)])
    finally:
        conn.close()


class HistoryExchangeIn(BaseModel):
    conversation_id: str
    question: str = Field(min_length=1, max_length=12000)
    answer: str = Field(min_length=1, max_length=100000)


@router.post('/exchanges', status_code=201)
def save_completed_exchange(payload: HistoryExchangeIn, request: Request):
    """Authenticated fallback for completed Vanna SSE responses.

    Data remains account-scoped: user_id always comes from the session and
    is never accepted from the browser.
    """
    record_exchange(request, payload.conversation_id, payload.question, payload.answer)
    return {'ok': True}


@router.get('')
def list_conversations(request: Request):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                _ensure(cur)
                user_id = _actor(cur, request)
                cur.execute('''SELECT id::text AS id,title,created_at,updated_at,
                          (SELECT COUNT(*)/2 FROM ai_messages m WHERE m.conversation_id=c.id) AS exchanges
                    FROM ai_conversations c WHERE user_id=%s
                    ORDER BY updated_at DESC LIMIT 100''',(user_id,))
                return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


@router.get('/{conversation_id}')
def get_conversation(conversation_id: str, request: Request):
    conv_id = _uuid(conversation_id)
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                _ensure(cur)
                user_id = _actor(cur, request)
                cur.execute('''SELECT id::text AS id,title,created_at,updated_at
                    FROM ai_conversations WHERE id=%s AND user_id=%s''',(conv_id,user_id))
                conv = cur.fetchone()
                if not conv: raise HTTPException(404, 'Không tìm thấy lịch sử')
                cur.execute('''SELECT role,content,created_at FROM ai_messages
                    WHERE conversation_id=%s ORDER BY id LIMIT 200''',(conv_id,))
                return {'conversation':dict(conv),'messages':[dict(x) for x in cur.fetchall()]}
    finally:
        conn.close()


@router.delete('/{conversation_id}')
def delete_conversation(conversation_id: str, request: Request):
    conv_id = _uuid(conversation_id)
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                _ensure(cur)
                user_id = _actor(cur,request)
                cur.execute('DELETE FROM ai_conversations WHERE id=%s AND user_id=%s RETURNING id',(conv_id,user_id))
                if not cur.fetchone(): raise HTTPException(404,'Không tìm thấy lịch sử')
                return {'ok':True}
    finally:
        conn.close()
