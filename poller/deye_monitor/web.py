"""Setup and status web app (port 8088 by default). Runs the poller in the background."""

import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import load_config, save_config
from .discovery import list_serial_ports, local_ip, scan_loggers
from .service import Poller

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.poller = Poller(load_config())
    app.state.poller.start()
    yield
    app.state.poller.stop()


app = FastAPI(title="Deye Pi Monitor", lifespan=lifespan, docs_url=None, redoc_url=None)
security = HTTPBasic(auto_error=False)


def require_admin(request: Request, creds: HTTPBasicCredentials | None = Depends(security)) -> None:
    password = request.app.state.poller.cfg.admin_password
    if not password:
        return
    if creds is None or not (secrets.compare_digest(creds.username, "admin")
                             and secrets.compare_digest(creds.password, password)):
        raise HTTPException(401, "Log in as admin", headers={"WWW-Authenticate": 'Basic realm="Deye monitor"'})


def poller(request: Request) -> Poller:
    return request.app.state.poller


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/", dependencies=[Depends(require_admin)])
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/status", dependencies=[Depends(require_admin)])
def status(p: Poller = Depends(poller)) -> dict:
    cfg = p.cfg
    ip = local_ip()
    builtin_broker = cfg.mqtt_host in ("localhost", "127.0.0.1", "mosquitto")
    return {
        **p.status(),
        "settings": {**cfg.editable(), "mqtt_password": None},
        "has_mqtt_password": bool(cfg.mqtt_password),
        "grafana_url": f"http://{ip}:{cfg.grafana_port}",
        "home_assistant": {
            "broker": ip if builtin_broker else cfg.mqtt_host,
            "port": cfg.mqtt_port,
            "username": cfg.mqtt_user,
            "password": cfg.mqtt_password if builtin_broker else None,
            "builtin": builtin_broker,
            "device_id": cfg.device_id,
        },
    }


@app.post("/api/scan", dependencies=[Depends(require_admin)])
def scan() -> dict:
    return {"loggers": scan_loggers()}


@app.get("/api/serial-ports", dependencies=[Depends(require_admin)])
def serial_ports() -> dict:
    return {"ports": list_serial_ports()}


def _candidate(p: Poller, body: dict):
    changes = dict(body)
    if not changes.get("mqtt_password"):
        changes.pop("mqtt_password", None)   # blank = keep the stored password
    try:
        return p.cfg.updated(changes)
    except (TypeError, ValueError) as e:
        raise HTTPException(422, str(e))


@app.post("/api/test", dependencies=[Depends(require_admin)])
def test(body: dict, p: Poller = Depends(poller)) -> dict:
    cfg = _candidate(p, body)
    try:
        values = p.test(cfg)
    except SystemExit as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        log.info("connection test failed: %s", e)
        return {"ok": False, "error": str(e) or type(e).__name__}
    return {"ok": True, "values": values}


@app.post("/api/settings", dependencies=[Depends(require_admin)])
def save(body: dict, p: Poller = Depends(poller)) -> dict:
    cfg = _candidate(p, body)
    save_config(cfg)
    p.apply(cfg)
    log.info("settings saved: %s", {**cfg.editable(), "mqtt_password": "***"})
    return {"ok": True}
