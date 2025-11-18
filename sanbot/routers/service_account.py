"""Routes for handling WeChat Service Account callbacks."""
from __future__ import annotations

import os
from flask import Blueprint, current_app, request, render_template_string, redirect
from itsdangerous import BadSignature, URLSafeSerializer
from werkzeug.utils import secure_filename

from file_analyzer import FileAnalyzer
from sanbot.services.analysis import start_analysis_job
from sanbot.session_store import SessionStore
from sanbot.wechat.service_account import WeChatServiceAPI
from sanbot.db import (
    insert_upload_with_members,
    list_uploads_by_user,
    ensure_user_exists,
    upload_exists,
    delete_upload_by_id,
)


def create_service_blueprint(
    app_config,
    file_analyzer: FileAnalyzer,
    wechat_api: WeChatServiceAPI,
    session_store: SessionStore,
):
    bp = Blueprint("wechat_service", __name__)
    upload_folder = app_config["UPLOAD_FOLDER"]
    high_delta_threshold = app_config.get("HIGH_DELTA_THRESHOLD", 5000)
    supported_commands = {
        "战功差": "分析两份CSV中的战功总量差值，按分组输出",
        "势力值": "分析两份CSV中的势力值差值，按分组输出",
    }
    unsupported_text = "暂不支持指令，目前仅支持【战功差】以及【势力值】，或发送【重置】清空当前会话"
    upload_base = app_config.get("PUBLIC_BASE_URL", "").rstrip("/")
    upload_serializer = URLSafeSerializer(app_config["SECRET_KEY"], salt="sanbot-upload-link")

    upload_template = """
    <!DOCTYPE html>
    <html lang=\"zh\">
    <head>
        <meta charset=\"utf-8\">
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
        <title>数据管理中心</title>
        <style>
            body { font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; margin: 0; padding: 20px; background: #fafafa; }
            .card { max-width: 520px; margin: auto; background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 6px 18px rgba(0,0,0,0.08); }
            .card + .card { margin-top: 16px; }
            h1 { font-size: 20px; margin-bottom: 12px; }
            label { display: block; margin-top: 16px; font-weight: 600; }
            input[type=file] { margin-top: 8px; width: 100%; padding: 14px; height: 48px; font-size: 16px; }
            button { margin-top: 24px; width: 100%; padding: 12px; background: #07c160; border: none; border-radius: 8px; color: #fff; font-size: 16px; }
            .note { margin-top: 16px; font-size: 14px; color: #666; }
            .error { color: #c0392b; margin-top: 12px; }
            .success { color: #1a7f37; margin-top: 12px; }
            /* 上传记录列表样式 */
            .uploads-list { list-style: none; padding-left: 0; margin: 0; }
            .uploads-list li {
                font-size: 13px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                white-space: nowrap;
                gap: 12px;
                padding: 8px 0;
                border-bottom: 1px solid #dcdfe6; /* 更明显的分割线 */
            }
            .upload-text { overflow: hidden; text-overflow: ellipsis; line-height: 28px; }
            .delete-btn {
                background: #fff;
                color: #c0392b;
                border: 1px solid #e5e5e5;
                border-radius: 6px;
                display: inline-flex;
                align-items: center;
                height: 28px;
                line-height: 28px;
                padding: 0 10px;
                font-size: 12px;
                margin-top: 0; /* 覆盖全局 button 顶部外边距 */
                width: auto;    /* 覆盖全局 button 宽度 */
            }
            .delete-btn:hover { background: #fff5f5; }
            .member-link { color:#1677ff; text-decoration:none; }
            .member-link:hover { text-decoration:underline; }
        </style>
    </head>
    <body>
        <div class=\"card\">
            <h1>上传同盟统计数据</h1>
            <p>上传最新同盟统计，系统会保存成员数据用于后续分析，一个账号只支持一个同盟。</p>
            {% if message %}
                <p class=\"{{ 'success' if success else 'error' }}\">{{ message }}</p>
            {% endif %}
            {% if show_form %}
            <form method=\"post\" enctype=\"multipart/form-data\">
                <input type=\"hidden\" name=\"token\" value=\"{{ token }}\" />
                <label>选择文件（可多选，三战导出的原始.csv）</label>
                <input type=\"file\" name=\"files\" accept=\".csv\" multiple />
                <button type=\"submit\">上传并保存数据</button>
                <p class=\"note\">文件名需包含导出时间（示例：同盟统计2025年11月15日23时00分32秒.csv）。</p>
            </form>
            {% endif %}
        </div>
            {% if uploads %}
            <div class="card">
                <h2>我的数据</h2>
                <ul class="uploads-list">
                {% for u in uploads %}
                    <li>
                        <span class="upload-text">{{ u.ts }}（<a class="member-link" href="/sanbot/service/upload-detail?token={{ token }}&upload_id={{ u.id }}">成员数：{{ u.member_count }}</a>）</span>
                        <form method="post" onsubmit="return confirm('确认删除该上传记录？此操作不可恢复。');" style="margin:0;">
                            <input type="hidden" name="token" value="{{ token }}" />
                            <input type="hidden" name="action" value="delete" />
                            <input type="hidden" name="upload_id" value="{{ u.id }}" />
                            <button class="delete-btn" type="submit">删除</button>
                        </form>
                    </li>
                {% endfor %}
                </ul>
            </div>
            {% endif %}
    </body>
    </html>
    """

    @bp.route("/upload-entry", methods=["GET"])
    def upload_entry():
        # Determine effective base URL: prefer configured PUBLIC_BASE_URL, fallback to request.url_root
        effective_base = upload_base
        if not effective_base:
            root = request.url_root.rstrip("/")
            if root.startswith("http://"):
                root = "https://" + root[len("http://"):]
            effective_base = root
        if not effective_base:
            return ("服务未配置 PUBLIC_BASE_URL，且无法推断站点地址。", 500)
        appid = app_config.get("FUWUHAO_APP_ID", "")
        secret = app_config.get("FUWUHAO_APP_SECRET", "")
        if not appid or not secret:
            return ("服务号未配置 AppID/Secret。", 500)

        code = request.args.get("code")
        if not code:
            from urllib.parse import quote
            redirect_uri = f"{effective_base}/sanbot/service/upload-entry"
            auth_url = (
                "https://open.weixin.qq.com/connect/oauth2/authorize"
                f"?appid={appid}&redirect_uri={quote(redirect_uri, safe='')}"
                "&response_type=code&scope=snsapi_base&state=STATE#wechat_redirect"
            )
            return redirect(auth_url)

        import requests
        try:
            token_resp = requests.get(
                "https://api.weixin.qq.com/sns/oauth2/access_token",
                params={
                    "appid": appid,
                    "secret": secret,
                    "code": code,
                    "grant_type": "authorization_code",
                },
                timeout=8,
            )
            data = token_resp.json()
            openid = data.get("openid")
            if not openid:
                current_app.logger.warning("OAuth exchange failed: %s", data)
                return ("无法获取用户身份，请重试。", 400)
        except Exception:
            current_app.logger.exception("OAuth request failed")
            return ("授权失败，请稍后重试。", 500)

        # create user if first time
        try:
            ensure_user_exists(current_app.config, openid)
        except Exception:
            current_app.logger.exception("ensure_user_exists failed")
        token = upload_serializer.dumps({"user_id": openid})
        return redirect(f"/sanbot/service/upload?token={token}")

    def _handle_text_message(user_id: str, content: str):
        if not user_id:
            return
        command = (content or "").strip()
        if command == "重置":
            current_app.logger.info("ServiceAcct reset requested by %s", user_id)
            session_store.pop(user_id)
            wechat_api.send_text_message(user_id, "已重置会话，请重新发送指令【战功差】或【势力值】。")
            return
        if command not in supported_commands:
            current_app.logger.info(
                "ServiceAcct unsupported command from %s: %s", user_id, command
            )
            wechat_api.send_text_message(user_id, unsupported_text)
            return
        current_app.logger.info(
            "ServiceAcct instruction recorded user=%s command=%s", user_id, command
        )
        session_store.pop(user_id)
        session_store.set_instruction(user_id, command)
        desc = supported_commands[command]
        message = (
            f"指令【{command}】已记录：{desc}。\n请连续上传两个CSV文件，我们会在收到第二个文件后触发分析。"
        )
        if upload_base:
            token = upload_serializer.dumps({"user_id": user_id})
            upload_link = f"{upload_base}/sanbot/service/upload?token={token}"
            message += f"\n若无法直接在公众号上传，请点击网页上传：{upload_link}"
        else:
            message += "\n（管理员可配置 PUBLIC_BASE_URL 提供网页上传入口。）"
        wechat_api.send_text_message(user_id, message)

    def _handle_file_message(user_id: str, media_id: str, raw_name: str | None, fallback_ext: str = ""):
        session_preview = session_store.ensure(user_id)
        instruction = (session_preview.instruction or "").strip()
        if instruction not in supported_commands:
            session_store.pop(user_id)
            wechat_api.send_text_message(user_id, "请先发送指令【战功差】或【势力值】后再上传文件。")
            return
        base_name = raw_name or f"upload{fallback_ext}"
        if fallback_ext and not base_name.lower().endswith(fallback_ext.lower()):
            base_name = f"{base_name}{fallback_ext}"
        safe_name = secure_filename(base_name) or f"upload{fallback_ext}"
        file_path = os.path.join(
            upload_folder,
            f"{user_id}_{len(session_preview.files)}_{safe_name}",
        )
        current_app.logger.info(
            "ServiceAcct file incoming user=%s media_id=%s name=%s target=%s", 
            user_id,
            media_id,
            raw_name,
            file_path,
        )
        success, error_msg = wechat_api.download_media(media_id, file_path)
        if not success:
            session_store.pop(user_id)
            current_app.logger.warning(
                "ServiceAcct download failed user=%s media_id=%s error=%s", 
                user_id,
                media_id,
                error_msg,
            )
            wechat_api.send_text_message(
                user_id,
                f"文件下载失败（{error_msg or '未知错误'}），会话已重置，请重新发送指令和文件。",
            )
            return
        current_app.logger.info(
            "ServiceAcct download ok user=%s media_id=%s saved=%s", user_id, media_id, file_path
        )
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
    def service_callback():  # type: ignore[override]
        timestamp = request.args.get("timestamp", "")
        nonce = request.args.get("nonce", "")
        signature = request.args.get("signature", "")

        if request.method == "GET":
            echostr = request.args.get("echostr", "")
            verified = wechat_api.verify_url(signature, timestamp, nonce, echostr)
            return verified if verified else "invalid", 200

        encrypt_type = request.args.get("encrypt_type", "raw").lower()
        if encrypt_type != "raw":
            current_app.logger.warning("Unsupported encrypt type '%s', please switch to 明文模式", encrypt_type)
            return "success"

        if not wechat_api.verify_signature(signature, timestamp, nonce):
            current_app.logger.warning("Service account signature verification failed")
            return "signature error", 403

        try:
            xml_data = request.data.decode("utf-8")
            message = wechat_api.parse_message(xml_data)
            msg_type = message.get("MsgType", "")
            from_user = message.get("FromUserName", "")

            if msg_type == "event":
                event = message.get("Event", "")
                if event.lower() == "subscribe":
                    wechat_api.send_text_message(
                        from_user,
                        "欢迎关注！本服务号的功能纯纯为爱发电，敬请期待更多能力。",
                    )
            elif msg_type == "text":
                _handle_text_message(from_user, message.get("Content", ""))
            elif msg_type in {"file", "image"}:
                media_id = (
                    message.get("MediaId")
                    or message.get("MediaID")
                    or message.get("FileKey")
                    or ""
                )
                file_name = (
                    message.get("FileName")
                    or message.get("Title")
                    or ("image.jpg" if msg_type == "image" else "upload.dat")
                )
                _, extension = os.path.splitext(file_name)
                if not extension:
                    extension = ".jpg" if msg_type == "image" else ".csv"
                if not media_id:
                    current_app.logger.warning(
                        "Missing media id for %s message: payload=%s", msg_type, message
                    )
                    if from_user:
                        wechat_api.send_text_message(from_user, "文件接收失败，请重试。")
                else:
                    _handle_file_message(from_user, media_id, file_name, extension)
            else:
                if from_user:
                    wechat_api.send_text_message(from_user, "目前仅支持发送指令与CSV文件上传，敬请期待更多能力。")
        except Exception:  # noqa: BLE001
            current_app.logger.exception("Service callback processing failed")

        return "success"

    @bp.route("/upload", methods=["GET", "POST"])
    def upload_page():
        token = request.values.get("token", "")
        if not token:
            return (
                render_template_string(
                    upload_template,
                    message="缺少 token 参数",
                    success=False,
                    show_form=False,
                    instruction="-",
                    token="",
                ),
                400,
            )
        try:
            payload = upload_serializer.loads(token, max_age=1800)
        except BadSignature:
            return (
                render_template_string(
                    upload_template,
                    message="链接已失效，请回到公众号重新获取上传入口",
                    success=False,
                    show_form=False,
                    instruction="-",
                    token="",
                ),
                400,
            )
        user_id = payload.get("user_id")
        if not user_id:
            return (
                render_template_string(
                    upload_template,
                    message="无法识别用户，链接无效。",
                    success=False,
                    show_form=False,
                    token="",
                    uploads=[],
                ),
                400,
            )

        upload_history = list_uploads_by_user(current_app.config, user_id)

        if request.method == "GET":
            # Log successful entry into data management (upload) page
            if user_id:
                current_app.logger.info("DataMgmt page access user=%s", user_id)
            return render_template_string(
                upload_template,
                message=None,
                success=False,
                show_form=True,
                token=token,
                uploads=upload_history,
            )

        # 删除操作优先处理
        action = request.form.get("action")
        if action == "delete":
            upload_id = request.form.get("upload_id")
            ok = False
            if upload_id and upload_id.isdigit():
                try:
                    ok = delete_upload_by_id(current_app.config, user_id, int(upload_id))
                except Exception:
                    current_app.logger.exception("Delete upload failed user=%s id=%s", user_id, upload_id)
            if ok:
                current_app.logger.info("DataMgmt delete user=%s id=%s result=success", user_id, upload_id)
                upload_history = list_uploads_by_user(current_app.config, user_id)
                return render_template_string(
                    upload_template,
                    message="删除成功。",
                    success=True,
                    show_form=True,
                    token=token,
                    uploads=upload_history,
                )
            else:
                current_app.logger.info("DataMgmt delete user=%s id=%s result=failure", user_id, upload_id)
                upload_history = list_uploads_by_user(current_app.config, user_id)
                return render_template_string(
                    upload_template,
                    message="删除失败：记录不存在或无权限。",
                    success=False,
                    show_form=True,
                    token=token,
                    uploads=upload_history,
                )

        files = request.files.getlist("files")
        files = [f for f in files if f and f.filename]
        if not files:
            # 不使用 400，保持表单可继续交互
            return render_template_string(
                upload_template,
                message="尚未选择任何文件，请先选择后再提交。",
                success=False,
                show_form=True,
                token=token,
                uploads=upload_history,
            )

        from file_analyzer import FileAnalyzer  # filename ts parser
        import pandas as pd
        successes = 0
        skipped = 0
        failures: list[str] = []

        for upload_file in files:
            filename = secure_filename(upload_file.filename)
            if not filename.lower().endswith(".csv"):
                failures.append(f"{filename}: 非CSV文件")
                continue
            # parse timestamp from filename
            try:
                ts = FileAnalyzer._parse_cn_timestamp_from_filename(filename)
            except Exception:
                failures.append(f"{filename}: 文件名未包含有效时间戳")
                continue
            # duplicate check
            if upload_exists(current_app.config, user_id, ts):
                skipped += 1
                continue
            # read csv
            try:
                df = pd.read_csv(upload_file, encoding="utf-8-sig", skipinitialspace=True)
            except Exception:
                failures.append(f"{filename}: CSV读取失败")
                continue

            from file_analyzer import FileAnalyzer as FA
            raw_columns = list(map(str, df.columns))
            member_col = FA._find_column(raw_columns, "成员")
            rank_col = FA._find_column(raw_columns, "贡献排名")
            contrib_col = FA._find_column(raw_columns, "贡献总量")
            battle_col = FA._find_column(raw_columns, "战功总量")
            assist_col = FA._find_column(raw_columns, "助攻总量")
            donate_col = FA._find_column(raw_columns, "捐献总量")
            power_col = FA._find_column(raw_columns, "势力值")
            group_col = FA._find_column(raw_columns, "分组")

            missing = []
            for name, col in {
                "成员": member_col,
                "贡献总量": contrib_col,
                "战功总量": battle_col,
                "助攻总量": assist_col,
                "捐献总量": donate_col,
                "势力值": power_col,
                "分组": group_col,
            }.items():
                if not col:
                    missing.append(name)
            if missing:
                failures.append(f"{filename}: 缺少必要列 {','.join(missing)}")
                continue

            df = df[[member_col, rank_col, contrib_col, battle_col, assist_col, donate_col, power_col, group_col]].copy() if rank_col else df[[member_col, contrib_col, battle_col, assist_col, donate_col, power_col, group_col]].copy()  # noqa: E501
            cols = ["成员", "贡献总量", "战功总量", "助攻总量", "捐献总量", "势力值", "分组"]
            if rank_col:
                df.columns = ["成员", "贡献排名"] + cols[1:]
            else:
                df.columns = cols

            df["成员"] = df["成员"].astype(str).str.strip()
            df["分组"] = df["分组"].astype(str).str.strip()
            if df["成员"].eq("").any():
                failures.append(f"{filename}: 存在空成员")
                continue
            for col_name in ["贡献总量", "战功总量", "助攻总量", "捐献总量", "势力值"]:
                df[col_name] = pd.to_numeric(df[col_name], errors="coerce")
                if df[col_name].isna().any():
                    failures.append(f"{filename}: 列 {col_name} 含非数字/缺失")
                    break
            else:
                if df["分组"].eq("").any():
                    failures.append(f"{filename}: 存在空分组")
                else:
                    members_payload = []
                    for _, row in df.iterrows():
                        members_payload.append(
                            {
                                "member_name": str(row["成员"]),
                                "rank": int(row["贡献排名"]) if ("贡献排名" in df.columns) and (not pd.isna(row.get("贡献排名", None))) else None,
                                "contrib_total": int(row["贡献总量"]),
                                "battle_total": int(row["战功总量"]),
                                "assist_total": int(row["助攻总量"]),
                                "donate_total": int(row["捐献总量"]),
                                "power_value": int(row["势力值"]),
                                "group_name": str(row["分组"]),
                            }
                        )
                    try:
                        insert_upload_with_members(current_app.config, user_id, ts, members_payload)
                        successes += 1
                    except Exception:
                        current_app.logger.exception("Insert upload to DB failed for %s", filename)
                        failures.append(f"{filename}: 数据库写入失败")

        # refresh history
        upload_history = list_uploads_by_user(current_app.config, user_id)
        parts = [f"成功 {successes} 个"]
        if skipped:
            parts.append(f"跳过 {skipped} 个（重复时间）")
        if failures:
            parts.append(f"失败 {len(failures)} 个：" + "; ".join(failures[:3]) + ("..." if len(failures) > 3 else ""))

        # Log upload summary before responding
        current_app.logger.info(
            "DataMgmt upload user=%s success=%d skipped=%d failed=%d", user_id, successes, skipped, len(failures)
        )
        return render_template_string(
            upload_template,
            message="，".join(parts),
            success=(successes > 0 and len(failures) == 0),
            show_form=True,
            token=token,
            uploads=upload_history,
        )

    return bp
