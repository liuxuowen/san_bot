"""Routes for handling WeChat Work callbacks."""
from __future__ import annotations

import os
from flask import Blueprint, request
from werkzeug.utils import secure_filename

from file_analyzer import FileAnalyzer
from sanbot.services.analysis import start_analysis_job
from sanbot.session_store import SessionStore, DEFAULT_INSTRUCTION
from wechat_api import WeChatWorkAPI


def create_wecom_blueprint(
    app_config,
    file_analyzer: FileAnalyzer,
    wechat_api: WeChatWorkAPI,
    session_store: SessionStore,
):
    bp = Blueprint("wechat_work", __name__)
    upload_folder = app_config["UPLOAD_FOLDER"]
    high_delta_threshold = app_config.get("HIGH_DELTA_THRESHOLD", 5000)

    def _handle_text_message(user_id: str, content: str):
        session_store.set_instruction(user_id, content or DEFAULT_INSTRUCTION)
        wechat_api.send_text_message(user_id, f"已收到指令: {content}\n请上传两个需要对比的文件。")

    def _handle_file_message(user_id: str, media_id: str, file_name: str | None):
        safe_name = secure_filename(file_name or "unknown_file")
        file_path = os.path.join(
            upload_folder,
            f"{user_id}_{len(session_store.ensure(user_id).files)}_{safe_name}",
        )
        success, error_msg = wechat_api.download_media(media_id, file_path)
        if not success:
            wechat_api.send_text_message(
                user_id,
                f"文件下载失败（{error_msg or '未知错误'}），请重试。",
            )
            return
        files = session_store.append_file(user_id, file_path)
        if len(files) < 2:
            wechat_api.send_text_message(user_id, f"已收到文件 {len(files)}/2，请继续上传第二个文件。")
            return
        scheduled = start_analysis_job(
            user_id,
            session_store,
            file_analyzer,
            wechat_api,
            upload_folder,
            high_delta_threshold,
        )
        if not scheduled:
            wechat_api.send_text_message(user_id, "任务调度失败，请稍后重试。")

    @bp.route("/callback", methods=["GET", "POST"])
    @bp.route("/work/callback", methods=["GET", "POST"])
    def wechat_callback():  # type: ignore[override]
        if request.method == "GET":
            msg_signature = request.args.get("msg_signature", "")
            timestamp = request.args.get("timestamp", "")
            nonce = request.args.get("nonce", "")
            echostr = request.args.get("echostr", "")
            verified = wechat_api.verify_url(
                msg_signature,
                timestamp,
                nonce,
                echostr,
                app_config["WECHAT_TOKEN"],
            )
            return verified if verified else "Verification failed", 200

        xml_data = request.data.decode("utf-8")
        message = wechat_api.parse_message(xml_data)
        msg_type = message.get("MsgType", "")
        from_user = message.get("FromUserName", "")

        if msg_type == "text":
            _handle_text_message(from_user, message.get("Content", DEFAULT_INSTRUCTION))
        elif msg_type in {"file", "image"}:
            media_id = message.get("MediaId", "")
            file_name = (
                message.get("FileName")
                or message.get("Title")
                or ("image.jpg" if msg_type == "image" else "unknown_file")
            )
            if not media_id:
                wechat_api.send_text_message(from_user, "未能获取文件信息，请重新发送。")
            else:
                _handle_file_message(from_user, media_id, file_name)
        else:
            wechat_api.send_text_message(from_user, "目前仅支持文本和文件消息，请重试。")

        return "success"

    return bp
