import html
import logging
from pathlib import Path

import psycopg
from fastapi import APIRouter, HTTPException, Request
from fastapi.routing import APIRoute
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from admin_auth import (settings, login_token, cookie, LOGIN, SESSION, TTL, owner,
                        authenticate, csrf, check_origin, digest, form)
from stats_store import store
import hmac

STATIC=Path(__file__).resolve().parent/'admin_static'
HEADERS={
    'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff',
    'Referrer-Policy':'same-origin',
    'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
}


class AdminRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def handler(request):
            try:
                settings() # Fail closed, including login and assets.
                response=await original(request)
            except HTTPException as exc:
                if request.url.path == '/admin/login' and request.method == 'POST' and exc.status_code in (400,401,403,413,415,429):
                    response=login_page('Вход не выполнен. Проверьте пароль и повторите попытку.' if exc.status_code!=429 else 'Слишком много попыток. Подождите 15 минут.',exc.status_code)
                    response.headers.update(exc.headers or {})
                else:
                    response=JSONResponse({'detail':exc.detail},status_code=exc.status_code,headers=exc.headers)
            except (psycopg.Error, TimeoutError, RuntimeError):
                logging.getLogger('q.admin').warning('admin_storage_unavailable')
                response=JSONResponse({'detail':'Хранилище недоступно. Данные не загружены.'},status_code=503)
            response.headers.update(HEADERS)
            return response
        return handler


router=APIRouter(route_class=AdminRoute)


def login_page(message='',status=200):
    token=login_token()
    body=f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>q · Вход владельца</title><link rel="stylesheet" href="/admin/login.css">
    <main class="login"><span class="brand">q / owner</span><h1>Вход владельца</h1><p>Закрытая панель транскрибации</p>
    <p role="alert">{html.escape(message)}</p><form method="post" action="/admin/login">
    <input type="hidden" name="csrf" value="{token}"><label>Пароль<input type="password" name="password" required maxlength="1024" autocomplete="current-password" autofocus></label>
    <button type="submit">Войти →</button></form></main></html>'''
    response=HTMLResponse(body,status_code=status)
    cookie(response,LOGIN,token,600)
    return response


@router.get('/admin/login')
async def login():
    return login_page()


@router.post('/admin/login')
async def sign_in(request:Request):
    token=await authenticate(request)
    response=RedirectResponse('/admin',status_code=303)
    cookie(response,SESSION,token,TTL)
    response.delete_cookie(LOGIN,path='/',secure=True,httponly=True,samesite='strict')
    return response


@router.get('/admin/login.css')
async def login_css():
    return FileResponse(STATIC/'admin.css',media_type='text/css')


@router.get('/admin')
async def admin(request:Request):
    try:
        token = await owner(request)
    except HTTPException as exc:
        if exc.status_code==401:
            return RedirectResponse('/admin/login',status_code=303)
        raise
    return HTMLResponse((STATIC/'admin.html').read_text().replace('__Q_CSRF__', csrf(token)))


@router.get('/admin/app.js')
async def javascript(request:Request):
    await owner(request)
    return FileResponse(STATIC/'admin.js',media_type='application/javascript')


@router.get('/api/admin/stats')
async def stats(request:Request):
    token=await owner(request)
    period=request.query_params.get('period','7d')
    tz=request.query_params.get('timezone','Europe/Kyiv')
    if period not in ('today','7d','30d','all') or tz not in ('UTC','Europe/Kyiv'):
        raise HTTPException(400,'Invalid period or timezone')
    result=await store.dashboard(period,tz)
    result['csrf']=csrf(token)
    return result


@router.post('/api/admin/logout')
async def sign_out(request:Request):
    token=await owner(request)
    check_origin(request)
    supplied=request.headers.get('x-csrf-token','')
    if not supplied.isascii() or not hmac.compare_digest(supplied,csrf(token)):
        raise HTTPException(403,'Invalid CSRF token')
    await store.logout(digest(token))
    response=JSONResponse({'ok':True})
    response.delete_cookie(SESSION,path='/',secure=True,httponly=True,samesite='strict')
    return response
