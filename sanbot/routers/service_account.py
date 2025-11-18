"""Routes for handling WeChat Service Account callbacks."""
from __future__ import annotations

import logging
import os
import re

from flask import Blueprint, current_app, request, render_template_string, redirect, jsonify, send_file
from itsdangerous import BadSignature, URLSafeSerializer
from werkzeug.utils import secure_filename

from file_analyzer import FileAnalyzer
from sanbot.wechat.service_account import WeChatServiceAPI
from sanbot.db import (
    insert_upload_with_members,
    list_uploads_by_user,
    ensure_user_exists,
    upload_exists,
    delete_upload_by_id,
    get_upload_with_members,
)


def create_service_blueprint(
    app_config,
    wechat_api: WeChatServiceAPI,
):
    bp = Blueprint("wechat_service", __name__)
    upload_base = app_config.get("PUBLIC_BASE_URL", "").rstrip("/")
    upload_serializer = URLSafeSerializer(app_config["SECRET_KEY"], salt="sanbot-upload-link")
    compare_image_serializer = URLSafeSerializer(app_config["SECRET_KEY"], salt="sanbot-compare-image")
    compare_image_dir = os.path.join(app_config.get("UPLOAD_FOLDER", "/tmp"), "compare_images")
    try:
        os.makedirs(compare_image_dir, exist_ok=True)
    except OSError:
        logging.getLogger(__name__).exception("Failed to create compare_images directory")
    welcome_template = app_config.get(
        "SERVICE_WELCOME_MESSAGE",
        """欢迎关注！本服务号的功能纯纯为爱发电，敬请期待更多能力，目前功能：\n功能1：<a href=\"{upload_link}\">同盟数据管理（同盟管理）</a>\n功能2：资源州找铜""",
    )

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
                border-bottom: 1px solid #dcdfe6;
            }
            .analysis-actions { display:flex; gap:8px; margin:6px 0 0; }
            .analysis-btn { padding:6px 16px; border-radius:6px; border:1px solid #07c160; background:#07c160; color:#fff; font-size:13px; cursor:pointer; transition:opacity 0.2s ease, transform 0.1s ease; }
            .analysis-btn.is-disabled { background:#f1f1f1; border-color:#d9d9d9; color:#8c8c8c; cursor:not-allowed; opacity:0.7; }
            .analysis-btn:not(.is-disabled):active { transform: translateY(1px); }
            .upload-text { overflow: hidden; text-overflow: ellipsis; line-height: 28px; flex:1; cursor:pointer; user-select:none; display:block; outline:none; }
            .upload-text:focus-visible .upload-text-inner { box-shadow:0 0 0 2px rgba(7,193,96,0.3); }
            .upload-text-inner { display:inline-block; padding:2px 8px; border:1px solid transparent; border-radius:6px; transition:border-color 0.2s ease, background-color 0.2s ease, color 0.2s ease; }
            .upload-item.is-selected { background:rgba(7,193,96,0.05); border-radius:8px; }
            .upload-item.is-selected .upload-text-inner { border-color:#07c160; background:rgba(7,193,96,0.12); color:#075c34; font-weight:600; }
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
                <p class=\"note\">文件名需包含导出时间（示例：同盟统计2025年11月15日23时00分32秒.csv）。部分安卓设备暂不支持多选，可多次选择逐个上传。</p>
            </form>
            {% endif %}
        </div>
            {% if uploads %}
            <div class="card">
                <h2>我的数据</h2>
                <div class="analysis-actions" role="group" aria-label="数据对比分析">
                    <button type="button" class="analysis-btn is-disabled" data-action="battle" data-enabled="false" aria-disabled="true">战功</button>
                    <button type="button" class="analysis-btn is-disabled" data-action="power" data-enabled="false" aria-disabled="true">势力</button>
                    <button type="button" class="analysis-btn is-disabled" data-action="contrib" data-enabled="false" aria-disabled="true">贡献</button>
                </div>
                <ul class="uploads-list">
                {% for u in uploads %}
                    <li class="upload-item" data-upload-id="{{ u.id }}">
                        <span class="upload-text" role="button" tabindex="0" aria-pressed="false">
                            <span class="upload-text-inner">{{ u.ts }}（<a class="member-link" href="/sanbot/service/upload-detail?token={{ token }}&upload_id={{ u.id }}">成员数：{{ u.member_count }}</a>）</span>
                        </span>
                        <form class="delete-form" method="post" onsubmit="return confirm('确认删除该上传记录？此操作不可恢复。');" style="margin:0;">
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
        <script>
            (function() {
                const uploadForm = document.querySelector('form[method="post"][enctype="multipart/form-data"]');
                const uploadInput = uploadForm ? uploadForm.querySelector('input[type="file"][name="files"]') : null;
                const tokenInput = uploadForm ? uploadForm.querySelector('input[name="token"]') : null;
                let isAutoUploading = false;

                if (uploadForm && uploadInput && tokenInput) {
                    uploadInput.addEventListener('change', async () => {
                        if (isAutoUploading) {
                            return;
                        }
                        const fileList = uploadInput.files;
                        if (!fileList || !fileList.length) {
                            return;
                        }
                        const files = Array.from(fileList);
                        const uploadUrl = uploadForm.getAttribute('action') || window.location.href;
                        const formData = new FormData();
                        formData.append('token', tokenInput.value);
                        files.forEach((file) => {
                            formData.append('files', file, file.name);
                        });
                        uploadInput.value = '';
                        uploadInput.disabled = true;
                        isAutoUploading = true;
                        try {
                            const response = await fetch(uploadUrl, {
                                method: 'POST',
                                body: formData,
                                credentials: 'same-origin',
                            });
                            if (!response.ok) {
                                throw new Error('上传失败，请稍后重试。');
                            }
                            const html = await response.text();
                            document.open();
                            document.write(html);
                            document.close();
                        } catch (error) {
                            isAutoUploading = false;
                            uploadInput.disabled = false;
                            window.alert(error instanceof Error ? error.message : '上传失败，请稍后重试。');
                        }
                    });
                }

                const actionButtons = Array.from(document.querySelectorAll('.analysis-btn'));
                if (!actionButtons.length) {
                    return;
                }
                const uploadItems = Array.from(document.querySelectorAll('.upload-item'));
                const selectedIds = [];
                const compareToken = {{ token|tojson }};
                let isSubmitting = false;

                const showAlert = (message) => {
                    if (message) {
                        window.alert(message);
                    }
                };

                const updateButtons = () => {
                    const enabled = selectedIds.length === 2 && !isSubmitting;
                    actionButtons.forEach((btn) => {
                        btn.dataset.enabled = enabled ? 'true' : 'false';
                        btn.setAttribute('aria-disabled', (!enabled).toString());
                        btn.classList.toggle('is-disabled', !enabled);
                    });
                };

                const toggleSelection = (item) => {
                    if (!item || isSubmitting) {
                        return;
                    }
                    const uploadId = item.dataset.uploadId;
                    if (!uploadId) {
                        return;
                    }
                    const textEl = item.querySelector('.upload-text');
                    const isSelected = item.classList.contains('is-selected');
                    if (isSelected) {
                        item.classList.remove('is-selected');
                        if (textEl) {
                            textEl.setAttribute('aria-pressed', 'false');
                        }
                        const idx = selectedIds.indexOf(uploadId);
                        if (idx !== -1) {
                            selectedIds.splice(idx, 1);
                        }
                    } else {
                        if (selectedIds.length >= 2) {
                            return;
                        }
                        item.classList.add('is-selected');
                        if (textEl) {
                            textEl.setAttribute('aria-pressed', 'true');
                        }
                        selectedIds.push(uploadId);
                    }
                    updateButtons();
                };

                const triggerAnalysis = (btn) => {
                    if (!btn || isSubmitting) {
                        return;
                    }
                    if (btn.dataset.enabled !== 'true') {
                        showAlert('请选择两条上传记录进行对比');
                        return;
                    }
                    if (!compareToken) {
                        showAlert('页面凭证已失效，请刷新后重试。');
                        return;
                    }
                    if (selectedIds.length !== 2) {
                        showAlert('请选择两条上传记录进行对比');
                        return;
                    }
                    const action = btn.dataset.action;
                    if (!action) {
                        showAlert('无法识别的分析类型');
                        return;
                    }
                    isSubmitting = true;
                    updateButtons();

                    const payload = {
                        token: compareToken,
                        metric: action,
                        upload_ids: selectedIds.slice(0, 2),
                    };

                    fetch('/sanbot/service/compare', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(payload),
                        credentials: 'same-origin',
                    })
                        .then(async (resp) => {
                            let data = {};
                            try {
                                data = await resp.json();
                            } catch (err) {
                                data = {};
                            }
                            if (!resp.ok || data.success === false) {
                                const msg = data.message || data.error || '发起比对失败，请稍后重试。';
                                throw new Error(msg);
                            }
                            const msg = data.message || '比对任务已提交，稍后留意公众号消息。';
                            showAlert(msg);
                        })
                        .catch((error) => {
                            showAlert(error.message || '发起比对失败，请稍后重试。');
                        })
                        .finally(() => {
                            isSubmitting = false;
                            updateButtons();
                        });
                };

                uploadItems.forEach((item) => {
                    const textEl = item.querySelector('.upload-text');
                    if (!textEl) {
                        return;
                    }
                    textEl.addEventListener('click', (event) => {
                        if (event.target.closest('a')) {
                            return;
                        }
                        toggleSelection(item);
                    });
                    textEl.addEventListener('keydown', (event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            toggleSelection(item);
                        }
                    });
                });

                const actionContainer = document.querySelector('.analysis-actions');
                if (actionContainer) {
                    actionContainer.addEventListener('click', (event) => {
                        const btn = event.target.closest('.analysis-btn');
                        if (!btn) {
                            return;
                        }
                        if (btn.dataset.enabled !== 'true') {
                            showAlert('请选择两条上传记录进行对比');
                            return;
                        }
                        triggerAnalysis(btn);
                    });
                }

                updateButtons();
            })();
        </script>
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

    class _TemplateDefaults(dict):
        def __missing__(self, key):
            return ""

    def _build_welcome_message(user_id: str) -> str:
        if not user_id:
            return welcome_template
        upload_link = ""
        if upload_base:
            token = upload_serializer.dumps({"user_id": user_id})
            upload_link = f"{upload_base}/sanbot/service/upload?token={token}"
        if "{" in welcome_template and "}" in welcome_template:
            text = welcome_template.format_map(_TemplateDefaults(upload_link=upload_link))
        else:
            text = welcome_template
        if upload_link and upload_link not in text:
            text = f"{text}\n{upload_link}"
        return text.strip()

    def _handle_text_message(user_id: str, content: str):
        if not user_id:
            return
        response_text = _build_welcome_message(user_id)
        current_app.logger.info("ServiceAcct welcome message sent user=%s", user_id)
        wechat_api.send_text_message(user_id, response_text)

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
                if event.lower() == "subscribe" and from_user:
                    welcome_text = _build_welcome_message(from_user)
                    wechat_api.send_text_message(from_user, welcome_text)
                elif event.lower() == "click" and from_user:
                    event_key = (message.get("EventKey") or "").strip()
                    if event_key == "SET_SEASON_PLACEHOLDER":
                        wechat_api.send_text_message(from_user, "这个功能还没做，现在就是记录一下谁是铜奴。")
            elif msg_type == "text":
                _handle_text_message(from_user, message.get("Content", ""))
            else:
                if from_user:
                    _handle_text_message(from_user, "")
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
            rank_col = FA._find_column(raw_columns, "贡献排行")
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

            df = (
                df[[member_col, rank_col, contrib_col, battle_col, assist_col, donate_col, power_col, group_col]].copy()
                if rank_col
                else df[[member_col, contrib_col, battle_col, assist_col, donate_col, power_col, group_col]].copy()
            )
            cols = ["成员", "贡献总量", "战功总量", "助攻总量", "捐献总量", "势力值", "分组"]
            if rank_col:
                df.columns = ["成员", "贡献排行"] + cols[1:]
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
                    rank_column_present = "贡献排行" in df.columns
                    for _, row in df.iterrows():
                        rank_value = None
                        if rank_column_present:
                            raw_rank = row.get("贡献排行", None)
                            if not pd.isna(raw_rank):
                                if isinstance(raw_rank, str):
                                    raw_rank_str = raw_rank.strip()
                                else:
                                    raw_rank_str = str(raw_rank)
                                match = re.search(r"\d+", raw_rank_str)
                                if match:
                                    try:
                                        rank_value = int(match.group())
                                    except ValueError:
                                        rank_value = None
                        members_payload.append(
                            {
                                "member_name": str(row["成员"]),
                                "rank": rank_value,
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

    @bp.route("/compare", methods=["POST"])
    def compare_uploads():
        data = request.get_json(silent=True) or {}
        token = data.get("token", "")
        if not token:
            return jsonify({"success": False, "message": "缺少 token 参数。"}), 400
        try:
            payload = upload_serializer.loads(token, max_age=1800)
        except BadSignature:
            return jsonify({"success": False, "message": "链接已失效，请刷新页面后重试。"}), 400

        user_id = payload.get("user_id")
        if not user_id:
            return jsonify({"success": False, "message": "无法识别用户身份。"}), 400

        upload_ids_raw = data.get("upload_ids")
        if not isinstance(upload_ids_raw, (list, tuple)) or len(upload_ids_raw) != 2:
            return jsonify({"success": False, "message": "请选择两条上传记录进行对比。"}), 400
        try:
            upload_ids = [int(x) for x in upload_ids_raw]
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "上传记录参数格式不正确。"}), 400
        if upload_ids[0] == upload_ids[1]:
            return jsonify({"success": False, "message": "请选择两条不同的上传记录。"}), 400

        metric_key = (data.get("metric") or "").lower()
        metric_map = {
            "battle": {"metric_key": "battle_total", "column": "战功总量", "label": "战功总量"},
            "power": {"metric_key": "power_value", "column": "势力值", "label": "势力值"},
            "contrib": {"metric_key": "contrib_total", "column": "贡献总量", "label": "贡献总量"},
        }
        metric_info = metric_map.get(metric_key)
        if not metric_info:
            return jsonify({"success": False, "message": "无法识别的分析类型。"}), 400

        upload_a, members_a = get_upload_with_members(current_app.config, user_id, upload_ids[0])
        upload_b, members_b = get_upload_with_members(current_app.config, user_id, upload_ids[1])
        if not upload_a or not upload_b:
            return jsonify({"success": False, "message": "上传记录不存在或已删除。"}), 404

        ts_a = upload_a.get("ts")
        ts_b = upload_b.get("ts")
        earlier_meta = upload_a
        later_meta = upload_b
        earlier_members = members_a
        later_members = members_b
        if ts_a and ts_b and ts_a > ts_b:
            earlier_meta, later_meta = upload_b, upload_a
            earlier_members, later_members = members_b, members_a

        analyzer = FileAnalyzer()
        try:
            comparison = analyzer.analyze_member_metric_change_from_records(
                earlier_members,
                later_members,
                metric_info["metric_key"],
                metric_info["column"],
                metric_info["label"],
                earlier_meta.get("ts"),
                later_meta.get("ts"),
            )
        except Exception as exc:  # noqa: BLE001
            current_app.logger.exception("Compare analysis failed user=%s metric=%s", user_id, metric_key)
            wechat_api.send_text_message(user_id, f"{metric_info['label']}对比失败：{exc}")
            return jsonify({"success": False, "message": "分析失败，请稍后重试。"}), 500

        if not comparison.get("success"):
            message = comparison.get("error") or "分析失败，请稍后重试。"
            wechat_api.send_text_message(user_id, f"{metric_info['label']}对比失败：{message}")
            return jsonify({"success": False, "message": message}), 500

        rows = comparison.get("rows", [])
        value_field = comparison.get("value_field") or f"{metric_info['label']}差值"
        earlier_ts_value = comparison.get("earlier_ts") or earlier_meta.get("ts")
        later_ts_value = comparison.get("later_ts") or later_meta.get("ts")
        earlier_ts_display = FileAnalyzer._format_ts_shichen(earlier_ts_value) or str(earlier_ts_value or "")
        later_ts_display = FileAnalyzer._format_ts_shichen(later_ts_value) or str(later_ts_value or "")

        if not rows:
            summary = (
                f"{metric_info['label']}对比结果\n"
                f"{earlier_ts_display} → {later_ts_display}\n"
                "两次上传没有共同成员，暂无可比数据。"
            )
            wechat_api.send_text_message(user_id, summary.strip())
            return jsonify({"success": True, "message": "对比完成：暂无共同成员，已通过公众号通知。"})

        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        header_path = os.path.join(root_dir, "resources", "header.jpg")

        try:
            image_results = analyzer.save_compare_group_images(
                rows,
                value_field=value_field,
                metric_label=value_field,
                earlier_ts=earlier_ts_value,
                later_ts=later_ts_value,
                output_dir=compare_image_dir,
                header_path=header_path,
            )
        except FileNotFoundError as exc:
            current_app.logger.exception("Compare image header missing user=%s", user_id)
            wechat_api.send_text_message(user_id, f"{metric_info['label']}对比失败：缺少头图资源，请联系管理员。")
            return jsonify({"success": False, "message": str(exc)}), 500
        except Exception as exc:  # noqa: BLE001
            current_app.logger.exception("Compare image render failed user=%s", user_id)
            wechat_api.send_text_message(user_id, f"{metric_info['label']}对比失败：生成图表时出现异常。")
            return jsonify({"success": False, "message": "生成图表失败，请稍后重试。"}), 500

        if not image_results:
            wechat_api.send_text_message(user_id, f"{metric_info['label']}对比完成，但暂未生成图像结果。")
            return jsonify({"success": True, "message": "对比完成，暂无图像输出。"})

        base_url = upload_base or request.url_root.rstrip("/")
        if not base_url:
            base_url = request.url_root.rstrip("/")

        link_lines = [
            f"{metric_info['label']}对比完成",
            f"{earlier_ts_display} → {later_ts_display}",
            "生成图片的有效期为30分钟，请及时下载",
        ]

        download_records: list[tuple[str, int, str]] = []
        for item in image_results:
            image_path = item.get("path") or ""
            if not image_path or not os.path.isfile(image_path):
                current_app.logger.error("Compare image missing on disk user=%s path=%s", user_id, image_path)
                continue
            filename = os.path.basename(image_path)
            group_label = item.get("group") or "未分组"
            count = int(item.get("count", 0))
            slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]+", "", group_label)
            if not slug:
                slug = "未分组"
            friendly_name = f"{metric_info['label']}对比_{slug}_{count}人.jpg"
            if len(friendly_name) > 60:
                friendly_name = f"{metric_info['label']}对比_{slug[:12]}_{count}人.jpg"
            token = compare_image_serializer.dumps({
                "user_id": user_id,
                "file": filename,
                "name": friendly_name,
            })
            download_link = f"{base_url}/sanbot/service/compare-image?token={token}"
            download_records.append((group_label, count, download_link))

        if not download_records:
            wechat_api.send_text_message(user_id, f"{metric_info['label']}对比完成，但未生成有效下载链接。")
            return jsonify({"success": False, "message": "未生成下载链接，请稍后重试。"}), 500

        for idx, (group_label, count, link) in enumerate(download_records, start=1):
            line = f"{idx}. <a href=\"{link}\">{group_label}（{count}人）</a>"
            link_lines.append(line)

        message_text = "\n".join(link_lines)
        send_resp = wechat_api.send_text_message(user_id, message_text)
        errcode = send_resp.get("errcode")
        if errcode not in (None, 0):
            errmsg = send_resp.get("errmsg") or "消息发送失败"
            current_app.logger.error(
                "Compare link message failed user=%s err=%s resp=%s",
                user_id,
                errmsg,
                send_resp,
            )
            return jsonify({"success": False, "message": errmsg}), 502

        return jsonify({"success": True, "message": "对比结果已生成，请在公众号查看下载链接。"})

    @bp.route("/compare-image", methods=["GET"])
    def download_compare_image():
        token = request.args.get("token", "")
        if not token:
            return ("缺少 token 参数。", 400)
        try:
            payload = compare_image_serializer.loads(token, max_age=1800)
        except BadSignature:
            return ("下载链接已失效，请重新发起对比。", 400)

        file_id = payload.get("file")
        if not file_id:
            return ("链接无效，缺少文件信息。", 400)

        file_path = os.path.join(compare_image_dir, file_id)
        if not os.path.isfile(file_path):
            return ("文件不存在或已删除，请重新发起对比。", 404)

        download_name = payload.get("name") or file_id
        try:
            return send_file(
                file_path,
                mimetype="image/jpeg",
                as_attachment=True,
                download_name=download_name,
            )
        except FileNotFoundError:
            return ("文件不存在或已删除，请重新发起对比。", 404)

    return bp
