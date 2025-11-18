"""Application factory and dependency wiring."""
from __future__ import annotations

import os
import logging
from flask import Flask, jsonify

from config import config
from file_analyzer import FileAnalyzer
from sanbot.routers.api import create_api_blueprint
from sanbot.routers.service_account import create_service_blueprint
from sanbot.routers.upload_detail import create_upload_detail_blueprint
from sanbot.routers.work import create_wecom_blueprint
from sanbot.session_store import SessionStore
from sanbot.wechat.service_account import WeChatServiceAPI
from wechat_api import WeChatWorkAPI
from sanbot.db import init_schema


def create_app(config_name: str = "default") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Initialize database schema (idempotent)
    try:
        init_schema(app.config)
    except Exception:
        app.logger.exception("Failed to initialize database schema")

    # Suppress or adjust werkzeug access logs based on config
    level_name = app.config.get("ACCESS_LOG_LEVEL", "ERROR").upper()
    if level_name == "NONE":
        logging.getLogger("werkzeug").disabled = True
    else:
        level = getattr(logging, level_name, logging.ERROR)
        logging.getLogger("werkzeug").setLevel(level)

    file_analyzer = FileAnalyzer()
    session_store = SessionStore()

    api_bp = create_api_blueprint(
        file_analyzer,
        app.config["UPLOAD_FOLDER"],
        app.config["ALLOWED_EXTENSIONS"],
    )
    app.register_blueprint(api_bp)

    if app.config.get("WECHAT_CORP_ID") and app.config.get("WECHAT_CORP_SECRET") and app.config.get("WECHAT_AGENT_ID"):
        wechat_work_api = WeChatWorkAPI(
            corp_id=app.config["WECHAT_CORP_ID"],
            corp_secret=app.config["WECHAT_CORP_SECRET"],
            agent_id=app.config["WECHAT_AGENT_ID"],
        )
        work_bp = create_wecom_blueprint(app.config, file_analyzer, wechat_work_api, session_store)
        app.register_blueprint(work_bp, url_prefix="/wechat")

    if app.config.get("FUWUHAO_APP_ID") and app.config.get("FUWUHAO_APP_SECRET") and app.config.get("FUWUHAO_TOKEN"):
        service_api = WeChatServiceAPI(
            app_id=app.config["FUWUHAO_APP_ID"],
            app_secret=app.config["FUWUHAO_APP_SECRET"],
            token=app.config["FUWUHAO_TOKEN"],
            encoding_aes_key=app.config.get("FUWUHAO_ENCODING_AES_KEY", ""),
        )
        service_bp = create_service_blueprint(app.config, service_api)
        app.register_blueprint(service_bp, url_prefix="/sanbot/service")
        detail_bp = create_upload_detail_blueprint(app.config)
        app.register_blueprint(detail_bp, url_prefix="/sanbot/service")

    @app.route("/")
    def index():
        return jsonify({
            "status": "running",
            "service": "San Bot",
            "version": "2.0.0",
            "channels": {
                "wechat_work": bool(app.config.get("WECHAT_CORP_ID")),
                "wechat_service": bool(app.config.get("FUWUHAO_APP_ID")),
            },
        })

    return app
