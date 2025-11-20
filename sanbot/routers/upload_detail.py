"""Detailed upload data view routes."""
from __future__ import annotations

import json

from flask import Blueprint, current_app, request, render_template_string
from itsdangerous import BadSignature, URLSafeSerializer

from sanbot.db import get_upload_with_members, get_member_history


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
            .card { max-width: 1200px; margin:auto; background:#fff; padding:20px 24px; border-radius:12px; box-shadow:0 4px 12px rgba(0,0,0,0.06); }
            h1 { font-size:20px; margin:0 0 16px; }
            .filters { margin-bottom:12px; }
            .filters select { height:30px; border:1px solid #e5e5e5; border-radius:6px; padding:0 8px; font-size:13px; }
            table { width:100%; min-width: 1000px; border-collapse: collapse; font-size:13px; }
            th, td { padding:6px 8px; border:1px solid #e5e5e5; text-align:center; white-space: nowrap; }
            th { background:#fafafa; font-weight:600; }
            .meta { font-size:13px; color:#555; margin-bottom:12px; }
            .back { display:inline-block; margin-bottom:16px; color:#1677ff; text-decoration:none; }
            .back:hover { text-decoration:underline; }
            .empty { padding:24px; text-align:center; color:#777; }
            .member-link { color:#1677ff; text-decoration:none; }
            .member-link:hover { text-decoration:underline; }
        </style>
    </head>
    <body>
      <div class=\"card\">
        <a class=\"back\" href=\"/sanbot/service/upload?token={{ token }}\">← 返回我的数据</a>
        {% if error %}
          <p class=\"empty\">{{ error }}</p>
        {% else %}
          <h1>同盟数据详情</h1>
          <p class=\"meta\">时间：{{ upload.ts }} ｜ 成员数：{{ upload.member_count }}</p>
          <form class=\"filters\" method=\"get\" action=\"/sanbot/service/upload-detail\">
            <input type=\"hidden\" name=\"token\" value=\"{{ token }}\" />
            <input type=\"hidden\" name=\"upload_id\" value=\"{{ upload.id }}\" />
            <label style=\"font-size:13px;color:#555;margin-right:8px;\">分组筛选：</label>
            <select name=\"group\" onchange=\"this.form.submit()\">
              <option value=\"\">全部分组</option>
              {% for g in groups %}
                <option value=\"{{ g }}\" {% if selected_group == g %}selected{% endif %}>{{ g }}</option>
              {% endfor %}
            </select>
          </form>
          <div style=\"overflow-x:auto;\">
            <table>
              <thead>
                <tr>
                  <th>成员</th>
                  <th>分组</th>
                  <th>贡献排名</th>
                  <th>贡献总量</th>
                  <th>战功总量</th>
                  <th>助攻总量</th>
                  <th>捐献总量</th>
                  <th>势力值</th>
                </tr>
              </thead>
              <tbody>
                {% for m in members %}
                <tr>
                  <td><a class=\"member-link\" href=\"/sanbot/service/member-trend?token={{ token }}&member={{ m.member_name|urlencode }}&upload_id={{ upload.id }}\">{{ m.member_name }}</a></td>
                  <td>{{ m.group_name }}</td>
                  <td>{{ m.contrib_rank if m.contrib_rank is not none else '-' }}</td>
                  <td>{{ m.contrib_total }}</td>
                  <td>{{ m.battle_total }}</td>
                  <td>{{ m.assist_total }}</td>
                  <td>{{ m.donate_total }}</td>
                  <td>{{ m.power_value }}</td>
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

    trend_template = """
    <!DOCTYPE html>
    <html lang=\"zh\">
    <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>{{ member_name }} - 历史趋势</title>
        <style>
            body { font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; margin:0; padding:16px; background:#f7f7f7; }
            .card { max-width: 1200px; margin:auto; background:#fff; padding:20px 24px; border-radius:12px; box-shadow:0 4px 12px rgba(0,0,0,0.06); }
            h1 { font-size:20px; margin:0 0 12px; }
            .back { display:inline-block; margin-bottom:16px; color:#1677ff; text-decoration:none; margin-right:12px; }
            .back:hover { text-decoration:underline; }
            .meta { font-size:13px; color:#555; margin-bottom:16px; }
            .chart-wrap { position:relative; width:100%; max-width:1000px; margin-bottom:24px; }
            .table-wrap { overflow-x:auto; }
            table { width:100%; min-width:900px; border-collapse:collapse; font-size:13px; }
            th, td { padding:6px 8px; border:1px solid #e5e5e5; text-align:center; white-space:nowrap; }
            th { background:#fafafa; font-weight:600; }
            .empty { padding:24px; text-align:center; color:#777; }
            .row-highlight { background:#f0f6ff; }
        </style>
    </head>
    <body>
      <div class=\"card\">
        <div>
          <a class=\"back\" href=\"{{ data_link }}\">← 返回我的数据</a>
          {% if detail_link %}
          <a class=\"back\" href=\"{{ detail_link }}\">⇦ 返回同盟数据</a>
          {% endif %}
        </div>
        {% if error %}
          <p class=\"empty\">{{ error }}</p>
        {% else %}
          <h1>{{ member_name }} 历史趋势</h1>
          <p class="meta">共计 {{ history|length }} 次记录，趋势按上传时间升序展示，表格最新在最前。</p>
          <div class=\"chart-wrap\">
            <canvas id=\"trendChart\"></canvas>
          </div>
          <div class=\"table-wrap\">
            <table>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>战功总量</th>
                  <th>势力值</th>
                  <th>贡献总量</th>
                  <th>助攻总量</th>
                  <th>捐献总量</th>
                  <th>分组</th>
                  <th>查看详情</th>
                </tr>
              </thead>
              <tbody>
                {% for item in history_table %}
                <tr class=\"{% if item.upload_id == highlight_upload_id %}row-highlight{% endif %}\">
                  <td>{{ item.ts_label }}</td>
                  <td>{{ item.battle_total }}</td>
                  <td>{{ item.power_value }}</td>
                  <td>{{ item.contrib_total }}</td>
                  <td>{{ item.assist_total }}</td>
                  <td>{{ item.donate_total }}</td>
                  <td>{{ item.group_name }}</td>
                  <td><a class=\"back\" style=\"margin:0;\" href=\"/sanbot/service/upload-detail?token={{ token }}&upload_id={{ item.upload_id }}\">查看</a></td>
                </tr>
                {% endfor %}
                {% if not history_table %}
                <tr><td colspan=8 class=\"empty\">暂无成员历史记录</td></tr>
                {% endif %}
              </tbody>
            </table>
          </div>
        {% endif %}
      </div>
      {% if not error and history %}
      <script src=\"https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js\" crossorigin=\"anonymous\"></script>
      <script>
        const labels = {{ chart_labels|safe }};
        const battleSeries = {{ chart_battle_data|safe }};
        const powerSeries = {{ chart_power_data|safe }};
        const ctx = document.getElementById('trendChart');
        if (ctx && labels.length) {
          new Chart(ctx, {
            type: 'line',
            data: {
              labels,
              datasets: [
                {
                  label: '战功',
                  data: battleSeries,
                  borderColor: '#1677ff',
                  backgroundColor: 'rgba(22,119,255,0.12)',
                  borderWidth: 2,
                  tension: 0.2,
                  pointRadius: 3,
                },
                {
                  label: '势力值',
                  data: powerSeries,
                  borderColor: '#34c759',
                  backgroundColor: 'rgba(52,199,89,0.12)',
                  borderWidth: 2,
                  tension: 0.2,
                  pointRadius: 3,
                }
              ]
            },
            options: {
              responsive: true,
              interaction: { mode: 'index', intersect: false },
              scales: {
                x: {
                  ticks: {
                    autoSkip: true,
                    maxTicksLimit: 8
                  }
                },
                y: {
                  beginAtZero: false,
                  ticks: { precision: 0 }
                }
              }
            }
          });
        }
      </script>
      {% endif %}
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
            return render_template_string(
                detail_template,
                error="记录不存在或无权限。",
                token=token,
                upload=None,
                members=[],
                groups=[],
                selected_group="",
            )

        groups = sorted({m["group_name"] for m in members})
        selected_group = request.args.get("group", "")
        if selected_group:
            members = [m for m in members if m["group_name"] == selected_group]

        return render_template_string(
            detail_template,
            error=None,
            token=token,
            upload=upload_row,
            members=members,
            groups=groups,
            selected_group=selected_group,
        )

    @bp.route("/member-trend", methods=["GET"])
    def member_trend():
        token = request.args.get("token", "")
        raw_member = request.args.get("member", "")
        member_name = raw_member.strip()
        raw_upload_id = request.args.get("upload_id", "")
        if not token or not member_name:
            return ("缺少必要参数。", 400)
        try:
            payload = serializer.loads(token, max_age=1800)
        except BadSignature:
            return ("链接已失效，请重新获取。", 400)
        user_id = payload.get("user_id")
        if not user_id:
            return ("无法识别用户。", 400)

        history_rows = get_member_history(current_app.config, user_id, member_name)
        if not history_rows:
            return render_template_string(
                trend_template,
                token=token,
                member_name=member_name,
                history=[],
            history_table=[],
                highlight_upload_id=None,
                data_link=f"/sanbot/service/upload?token={token}",
                detail_link="",
                chart_labels="[]",
                chart_battle_data="[]",
                chart_power_data="[]",
                error="暂无该成员的历史记录。",
            )

        prepared_history: list[dict[str, object]] = []
        labels: list[str] = []
        battle_series: list[int] = []
        power_series: list[int] = []

        for row in history_rows:
            ts_value = row.get("ts")
            ts_label = ts_value.strftime("%Y-%m-%d %H:%M") if hasattr(ts_value, "strftime") else str(ts_value)
            chart_label = ts_value.strftime("%m/%d") if hasattr(ts_value, "strftime") else str(ts_value)
            prepared_history.append(
                {
                    "upload_id": row.get("upload_id"),
                    "ts_label": ts_label,
                    "battle_total": row.get("battle_total", 0),
                    "power_value": row.get("power_value", 0),
                    "contrib_total": row.get("contrib_total", 0),
                    "assist_total": row.get("assist_total", 0),
                    "donate_total": row.get("donate_total", 0),
                    "group_name": row.get("group_name", "-"),
                }
            )
            labels.append(chart_label)
            battle_series.append(int(row.get("battle_total", 0) or 0))
            power_series.append(int(row.get("power_value", 0) or 0))

        highlight_upload_id = None
        if raw_upload_id.isdigit():
            candidate = int(raw_upload_id)
            if any(item["upload_id"] == candidate for item in prepared_history):
                highlight_upload_id = candidate
        if highlight_upload_id is None:
            last_id = prepared_history[-1]["upload_id"]
            try:
                highlight_upload_id = int(last_id)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                highlight_upload_id = None

        detail_link = ""
        if highlight_upload_id is not None:
            detail_link = f"/sanbot/service/upload-detail?token={token}&upload_id={highlight_upload_id}"

        return render_template_string(
            trend_template,
            token=token,
            member_name=member_name,
                history=prepared_history,
                history_table=list(reversed(prepared_history)),
            highlight_upload_id=highlight_upload_id,
            data_link=f"/sanbot/service/upload?token={token}",
            detail_link=detail_link,
            chart_labels=json.dumps(labels),
            chart_battle_data=json.dumps(battle_series),
            chart_power_data=json.dumps(power_series),
            error=None,
        )

    return bp