"""Thin ARM lab ops panel. Not production vpush admin. Not a reading desk."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from ops_actions import ActionError, cicc_sync, ima_sync, requeue_failed
from ops_auth import (
    COOKIE_KWARGS,
    issue_session,
    password_configured,
    session_ok,
    verify_password,
)
from ops_lab_knobs import get_settings, save_settings
from ops_qr115 import QRError, QRManager
from ops_settings import (
    BIND_ALL_WARNING,
    DEFAULT_HOST,
    IMA_GROUP_ALLOWLIST,
    P115_DEVICE_TYPES,
    SESSION_COOKIE,
    SYNC_LIMIT_DEFAULT,
    SYNC_LIMIT_MAX,
    TAILSCALE_BIND_TOKENS,
    TAILSCALE_MISSING_WARNING,
    bind_host,
    bind_port,
    bind_spec,
    binds_all_interfaces,
    default_device_type,
)
from ops_status import collect_status, redact

HERE = Path(__file__).resolve().parent
log = logging.getLogger("arm_lab_ops")


def create_app() -> FastAPI:
    app = FastAPI(title="ARM lab ops", docs_url=None, redoc_url=None, openapi_url=None)
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    app.state.qr = QRManager()

    def logged_in(request: Request) -> bool:
        return session_ok(request.cookies.get(SESSION_COOKIE))

    def login_redirect() -> RedirectResponse:
        return RedirectResponse("/login", status_code=303)

    def unauthorized() -> JSONResponse:
        return JSONResponse({"ok": False, "error": "auth required"}, status_code=401)

    async def read_json_body(request: Request) -> dict:
        ctype = request.headers.get("content-type", "")
        if "application/json" in ctype:
            try:
                body = await request.json()
            except Exception:
                return {}
            return body if isinstance(body, dict) else {}
        try:
            form = await request.form()
        except Exception:
            return {}
        return {str(key): form.get(key) for key in form}

    def action_error(exc: ActionError) -> JSONResponse:
        log.warning("action failed: %s", redact(str(exc)))
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=exc.status_code)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request) -> HTMLResponse:
        if logged_in(request):
            return RedirectResponse("/", status_code=303)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": None, "configured": password_configured()},
        )

    @app.post("/login")
    def login_submit(request: Request, password: str = Form("")):
        if not password_configured():
            return templates.TemplateResponse(
                request,
                "login.html",
                {
                    "error": "口令未配置（ARM_OPS_PASSWORD 或 /secrets/arm-ops-password.txt）",
                    "configured": False,
                },
                status_code=503,
            )
        if not verify_password(password):
            log.info("login failed")
            return templates.TemplateResponse(
                request,
                "login.html",
                {"error": "口令不正确", "configured": True},
                status_code=401,
            )
        log.info("login ok")
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(value=issue_session(), **COOKIE_KWARGS)
        return response

    @app.post("/logout")
    def logout() -> RedirectResponse:
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        if not logged_in(request):
            return login_redirect()
        try:
            status = collect_status()
        except Exception as exc:
            log.warning("status collect failed: %s", redact(str(exc)))
            status = {"ok": False, "error": "status unavailable"}
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "status": status,
                "status_json": json.dumps(status, ensure_ascii=False).replace("<", "\\u003c"),
                "device_types": P115_DEVICE_TYPES,
                "default_device": default_device_type(),
                "ima_groups": IMA_GROUP_ALLOWLIST,
                "sync_limit_default": SYNC_LIMIT_DEFAULT,
                "sync_limit_max": SYNC_LIMIT_MAX,
                "cicc_incr_days": (status.get("cicc") or {}).get("incr_days") or 3,
            },
        )

    @app.get("/api/status")
    def api_status(request: Request):
        if not logged_in(request):
            return unauthorized()
        return collect_status()

    @app.post("/api/115/qr/start")
    async def qr_start(request: Request):
        if not logged_in(request):
            return unauthorized()
        device = default_device_type()
        ctype = request.headers.get("content-type", "")
        if "application/json" in ctype:
            body = await request.json()
            if isinstance(body, dict) and body.get("device_type"):
                device = str(body.get("device_type"))
        else:
            form = await request.form()
            if form.get("device_type"):
                device = str(form.get("device_type"))
        try:
            return app.state.qr.start(device)
        except QRError as exc:
            log.warning("qr start failed: %s", exc)
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @app.get("/api/115/qr/status")
    def qr_status(request: Request, session_id: str = ""):
        if not logged_in(request):
            return unauthorized()
        if not session_id:
            return JSONResponse({"ok": False, "error": "session_id required"}, status_code=400)
        try:
            return app.state.qr.poll(session_id)
        except QRError as exc:
            log.warning("qr poll failed: %s", exc)
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @app.post("/api/failed/requeue")
    async def failed_requeue(request: Request):
        if not logged_in(request):
            return unauthorized()
        body = await read_json_body(request)
        try:
            return requeue_failed(body)
        except ActionError as exc:
            return action_error(exc)

    @app.post("/api/sync/ima/dry-run")
    async def sync_ima_dry_run(request: Request):
        if not logged_in(request):
            return unauthorized()
        body = await read_json_body(request)
        try:
            return ima_sync(body, dry_run=True)
        except ActionError as exc:
            return action_error(exc)

    @app.post("/api/sync/ima/apply")
    async def sync_ima_apply(request: Request):
        if not logged_in(request):
            return unauthorized()
        body = await read_json_body(request)
        try:
            return ima_sync(body, dry_run=False)
        except ActionError as exc:
            return action_error(exc)

    @app.post("/api/sync/cicc/dry-run")
    async def sync_cicc_dry_run(request: Request):
        if not logged_in(request):
            return unauthorized()
        body = await read_json_body(request)
        try:
            return cicc_sync(body, dry_run=True)
        except ActionError as exc:
            return action_error(exc)

    @app.post("/api/sync/cicc/apply")
    async def sync_cicc_apply(request: Request):
        if not logged_in(request):
            return unauthorized()
        body = await read_json_body(request)
        try:
            return cicc_sync(body, dry_run=False)
        except ActionError as exc:
            return action_error(exc)

    @app.get("/api/settings")
    def api_settings_get(request: Request):
        if not logged_in(request):
            return unauthorized()
        return get_settings()

    @app.post("/api/settings")
    async def api_settings_save(request: Request):
        if not logged_in(request):
            return unauthorized()
        body = await read_json_body(request)
        try:
            return save_settings(body)
        except ActionError as exc:
            return action_error(exc)

    return app


app = create_app()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    spec = bind_spec()
    host = bind_host()
    port = bind_port()
    if binds_all_interfaces(spec) or binds_all_interfaces(host):
        print(BIND_ALL_WARNING, file=sys.stderr)
    if spec.lower() in TAILSCALE_BIND_TOKENS and host == DEFAULT_HOST:
        print(TAILSCALE_MISSING_WARNING, file=sys.stderr)
    print(f"ARM lab ops bind {host}:{port} (ARM_OPS_BIND={spec!r})", file=sys.stderr)
    if not password_configured():
        print(
            "ARM lab ops: set ARM_OPS_PASSWORD or ARM_OPS_PASSWORD_FILE "
            "(host: /opt/vpush-ima-lab/secrets/arm-ops-password.txt)",
            file=sys.stderr,
        )
    import uvicorn

    uvicorn.run("ops_app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
