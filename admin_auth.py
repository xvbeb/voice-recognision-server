"""Single owner only: Argon2id, opaque PostgreSQL sessions, CSRF, shared throttle."""
import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

from argon2 import PasswordHasher, extract_parameters, Type
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from stats_store import store

SESSION = '__Host-q_session'
LOGIN = '__Host-q_login'
TTL = 3600
hasher = PasswordHasher()


def settings():
    hashed = os.getenv('ADMIN_PASSWORD_HASH','')
    secret = os.getenv('ADMIN_SESSION_SECRET','')
    origin = os.getenv('ADMIN_ORIGIN','https://voice-recognision-server-production.up.railway.app')
    try:
        params = extract_parameters(hashed)
        parsed = urlsplit(origin)
        valid = params.type == Type.ID and params.memory_cost >= 19456 and params.time_cost >= 2
        valid = valid and len(secret)>=32 and parsed.scheme=='https' and parsed.netloc and not parsed.path and not parsed.query and not parsed.fragment and not parsed.username
    except (ValueError, InvalidHashError):
        valid = False
    if not valid:
        raise HTTPException(404, 'Not found')
    return hashed,secret,origin


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def mac(value):
    return hmac.new(settings()[1].encode(), value.encode(), hashlib.sha256).hexdigest()


def version():
    return mac(settings()[0])


def login_token():
    value=f'{int(time.time())}.{secrets.token_urlsafe(24)}'
    return value+'.'+mac(value)


def cookie(response,name,value,seconds):
    response.set_cookie(name,value,max_age=seconds,httponly=True,secure=True,samesite='strict',path='/')


def check_origin(request):
    if request.headers.get('origin') != settings()[2]:
        raise HTTPException(403, 'Invalid origin')


async def form(request):
    if request.headers.get('content-type','').split(';')[0] != 'application/x-www-form-urlencoded':
        raise HTTPException(415, 'Form required')
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>8192:
            raise HTTPException(413, 'Form too large')
    try:
        data = parse_qs(raw.decode(), max_num_fields=4, strict_parsing=True)
        if any(len(v)!=1 for v in data.values()):
            raise ValueError()
        return {k:v[0] for k,v in data.items()}
    except (ValueError, UnicodeError):
        raise HTTPException(400, 'Invalid form') from None


def check_login_csrf(request, token):
    check_origin(request)
    saved = request.cookies.get(LOGIN,'')
    if not token or not token.isascii() or not saved.isascii() or len(token)>256 or not hmac.compare_digest(token,saved):
        raise HTTPException(403, 'Invalid CSRF token')
    try:
        ts,nonce,signature=token.split('.')
        age=time.time()-int(ts)
        valid = 0 <= age < 600 and hmac.compare_digest(signature,mac(ts+'.'+nonce))
    except ValueError:
        valid=False
    if not valid:
        raise HTTPException(403, 'Expired CSRF token')


async def owner(request):
    settings()
    token=request.cookies.get(SESSION,'')
    if len(token)!=43:
        raise HTTPException(401, 'Authentication required')
    session=await store.session(digest(token),version())
    if not session:
        raise HTTPException(401, 'Session expired')
    return token


def csrf(token):
    return mac('csrf:'+token)


async def authenticate(request):
    data=await form(request)
    check_login_csrf(request,data.get('csrf',''))
    # Global per-owner throttle, shared by all replicas, independent of spoofable IP.
    if not await store.reserve_login():
        raise HTTPException(429, 'Too many attempts. Try again in 15 minutes.',headers={'Retry-After':'900'})
    password=data.get('password','')
    if not password or len(password)>1024:
        raise HTTPException(401,'Invalid password')
    try:
        valid=await run_in_threadpool(hasher.verify,settings()[0],password)
    except (VerificationError,InvalidHashError):
        valid=False
    if not valid:
        raise HTTPException(401,'Invalid password')
    token=secrets.token_urlsafe(32)
    await store.create_session(digest(token),version(),datetime.now(timezone.utc)+timedelta(seconds=TTL))
    # Rotate an existing session on reauthentication.
    old=request.cookies.get(SESSION,'')
    if old:
        await store.logout(digest(old))
    return token
