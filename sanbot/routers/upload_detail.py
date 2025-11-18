"""Detailed upload data view routes."""
from __future__ import annotations

from flask import Blueprint, current_app, request, render_template_string
from itsdangerous import BadSignature, URLSafeSerializer

from sanbot.db import get_upload_with_members


def create_upload_detail_blueprint(app_config):
    bp = Blueprint("upload_detail", __name__)
    serializer = URLSafeSerializer(app_config["SECRET_KEY"], salt="sanbot-upload-link")

    detail_template = """
    <!DOCTYPE html>
    <html lang=\"zh\">
    <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1" />
        <title>同盟数据详情</title>
        <style>
            body { font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; margin:0; padding:16px; background:#f7f7f7; }
            .card { max-width: 900px; margin:auto; background:#fff; padding:20px 24px; border-radius:12px; box-shadow:0 4px 12px rgba(0,0,0,0.06); }
            h1 { font-size:20px; margin:0 0 16px; }
            table { width:100%; border-collapse: collapse; font-size:13px; }
            th, td { padding:6px 8px; border:1px solid #e5e5e5; text-align:center; }
            th { background:#fafafa; font-weight:600; }
            .meta { font-size:13px; color:#555; margin-bottom:12px; }
            .back { display:inline-block; margin-bottom:16px; color:#1677ff; text-decoration:none; }
            .back:hover { text-decoration:underline; }
            .empty { padding:24px; text-align:center; color:#777; }
        </style>
    </head>
    <body>
      <div class=\"card\">
        <a class=\"back\" href=\"/sanbot/service/upload?token={{ token }}\">← 返回我的数据</a>
        {% if error %}
          <p class=\"empty\">{{ error }}</p>
        {% else %}
          <h1>同盟数据详情</h1>
          <p class=\"meta\">时间：{{ upload.ts }} ｜ 成员数：{{ upload.member_count }} ｜ 上传时间：{{ upload.created_at }}</p>
          <div style=\"overflow-x:auto;\">
            <table>
              <thead>
                <tr>
                  <th>成员</th>
                  <th>贡献排名</th>
                  <th>贡献总量</th>
                  <th>战功总量</th>
                  <th>助攻总量</th>
                  <th>捐献总量</th>
                  <th>势力值</th>
                  <th>分组</th>
                </tr>
              </thead>
              <tbody>
                {% for m in members %}
                <tr>
                  <td>{{ m.member_name }}</td>
                  <td>{{ m.contrib_rank if m.contrib_rank is not none else '-' }}</td>
                  <td>{{ m.contrib_total }}</td>
                  <td>{{ m.battle_total }}</td>
                  <td>{{ m.assist_total }}</td>
                  <td>{{ m.donate_total }}</td>
                  <td>{{ m.power_value }}</td>
                  <td>{{ m.group_name }}</td>
                </tr>
                {% endfor %}
                {% if not members %}
                <tr><td colspan=8 class=\"empty\">暂无成员数据</td></tr>
                {% endif %}
              </tbody>
            </table>
          </div>
        {% endif %}
      </div>
    </body>
    </html>
    """

    @bp.route("/upload-detail", methods=["GET"])
    def upload_detail():
        token = request.args.get("token", "")
        upload_id = request.args.get("upload_id", "")
        if not token or not upload_id:
            return ("缺少必要参数。", 400)
        try:
            payload = serializer.loads(token, max_age=1800)
        except BadSignature:
            return ("链接已失效，请重新获取。", 400)
        user_id = payload.get("user_id")
        if not user_id:
            return ("无法识别用户。", 400)
        if not upload_id.isdigit():
            return ("上传ID无效。", 400)
        upload_row, members = get_upload_with_members(current_app.config, user_id, int(upload_id))
        if not upload_row:
            return render_template_string(detail_template, error="记录不存在或无权限。", token=token, upload=None, members=[])
        return render_template_string(detail_template, error=None, token=token, upload=upload_row, members=members)

    return bp