"""Reusable routines for running file analysis jobs."""
from __future__ import annotations

import os
import threading
from typing import Protocol, Sequence

from file_analyzer import FileAnalyzer
from sanbot.session_store import SessionStore, Session, DEFAULT_INSTRUCTION


class WeChatMessenger(Protocol):
    """Protocol describing the methods needed from a WeChat client."""

    def send_text_message(self, user_id: str, content: str):
        ...

    def upload_image(self, file_path: str):
        ...

    def send_image_message(self, user_id: str, media_id: str):
        ...


def _cleanup_files(file_paths: Sequence[str]) -> None:
    for file_path in file_paths:
        try:
            os.remove(file_path)
        except OSError:
            pass


def _format_time_window(earlier: str, later: str, metric_label: str) -> str:
    def _trim_seconds(ts_str: str) -> str:
        parts = ts_str.strip().split(" ")
        if len(parts) == 2 and parts[1].count(":") >= 2:
            date_part, time_part = parts
            hh_mm = ":".join(time_part.split(":")[:2])
            return f"{date_part} {hh_mm}"
        return ts_str

    def _slash_fmt(ts: str) -> str:
        parts = ts.split(" ")
        if len(parts) == 2:
            d, hm = parts
            d_parts = d.split("-")
            if len(d_parts) == 3:
                d = "/".join(d_parts)
            return f"{d} {hm}"
        return ts

    earlier_no_sec = _trim_seconds(earlier)
    later_no_sec = _trim_seconds(later)
    display_title = f"{metric_label}统计 {_slash_fmt(earlier_no_sec)} → {_slash_fmt(later_no_sec)}"
    title_prefix = (
        f"{metric_label}统计_{earlier_no_sec.replace(':', '').replace(' ', '_')}"
        f"_至_{later_no_sec.replace(':', '').replace(' ', '_')}"
    )
    return title_prefix, display_title


def _send_group_images(
    wechat_client: WeChatMessenger,
    user_id: str,
    csv_payload,
    output_dir: str,
    high_delta_threshold: int,
    value_field: str,
    value_label: str,
):
    os.makedirs(output_dir, exist_ok=True)
    earlier_ts = csv_payload.get('earlier_ts', '')
    later_ts = csv_payload.get('later_ts', '')
    title_prefix, display_title = _format_time_window(earlier_ts, later_ts, value_label)
    images = FileAnalyzer.save_grouped_tables_as_images(  # type: ignore[attr-defined]
        csv_payload.get('rows', []),
        output_dir,
        title_prefix,
        display_title,
        value_field,
        value_label,
        high_delta_threshold=high_delta_threshold,
    )
    if not images:
        return False
    wechat_client.send_text_message(user_id, f"分析完成，共生成{len(images)}张分组图片，即将发送…")
    for path in images:
        upload_resp = wechat_client.upload_image(path)
        if upload_resp.get('errcode') == 0 and upload_resp.get('media_id'):
            wechat_client.send_image_message(user_id, upload_resp['media_id'])
    return True


def start_analysis_job(
    user_id: str,
    session_store: SessionStore,
    file_analyzer: FileAnalyzer,
    wechat_client: WeChatMessenger,
    output_root: str,
    high_delta_threshold: int = 5000,
) -> bool:
    """Kick off a background analysis job when two files are ready.

    Returns True if the job was scheduled, False otherwise.
    """

    snapshot = session_store.snapshot(user_id)
    if not snapshot or len(snapshot.files) < 2:
        return False

    def worker(snapshot_copy: Session):
        session = session_store.pop(user_id) or snapshot_copy
        files = list(session.files)
        try:
            file1, file2 = files[:2]
            instruction = (session.instruction or '').strip()
            csv_ready = file1.lower().endswith('.csv') and file2.lower().endswith('.csv')
            metric_handlers = {
                '战功差': file_analyzer.analyze_battle_merit_change,
                '势力值': file_analyzer.analyze_power_value_change,
            }
            if instruction in metric_handlers:
                if not csv_ready:
                    wechat_client.send_text_message(user_id, f"指令【{instruction}】仅支持CSV文件，请重新发送。")
                    _cleanup_files(files)
                    return
                csv_result = metric_handlers[instruction](file1, file2)
                if not csv_result.get('success'):
                    wechat_client.send_text_message(user_id, csv_result.get('error') or '分析失败，请稍后重试。')
                    _cleanup_files(files)
                    return
                value_field = csv_result.get('value_field')
                value_label = csv_result.get('value_label', instruction)
                if not value_field or not value_label:
                    wechat_client.send_text_message(user_id, '分析结果缺少必要字段，请检查CSV。')
                    _cleanup_files(files)
                    return
                csv_result['earlier_ts'] = csv_result.get('earlier_ts', '')
                csv_result['later_ts'] = csv_result.get('later_ts', '')
                success = _send_group_images(
                    wechat_client,
                    user_id,
                    csv_result,
                    os.path.join(output_root, 'output'),
                    high_delta_threshold,
                    value_field,
                    value_label,
                )
                if success:
                    _cleanup_files(files)
                    return
                wechat_client.send_text_message(user_id, '未生成有效图表，请确认CSV包含数据。')
                _cleanup_files(files)
                return
            instruction = instruction or DEFAULT_INSTRUCTION
            result = file_analyzer.analyze_files(file1, file2, instruction)
            message = result.get('report') or result.get('error') or '分析完成。'
            wechat_client.send_text_message(user_id, message)
        except Exception as exc:  # noqa: BLE001
            wechat_client.send_text_message(user_id, f"分析失败: {exc}")
        finally:
            _cleanup_files(files)

    wechat_client.send_text_message(user_id, "已收到两份文件，开始分析处理，请稍候…")
    threading.Thread(target=worker, args=(snapshot,), daemon=True).start()
    return True
