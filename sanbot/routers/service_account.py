"""Routes for handling WeChat Service Account callbacks."""
from __future__ import annotations

import logging
import os
import re
import threading
import numpy as np
import pandas as pd
from typing import Any

from flask import Blueprint, current_app, request, render_template_string, redirect, jsonify, send_file, render_template
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
    set_user_selected_season,
    get_user_selected_season,
    list_map_resources_by_scenario,
)

# --- Constants ---

COPPER_COORD_MIN = 1
COPPER_COORD_MAX = 1500
COPPER_MAX_ATTEMPTS = 3
COPPER_SLAVE_RADIUS_LIMIT = 100
COPPER_SLAVE_NEAR_RADIUS = 5
COPPER_SLAVE_CLUSTER_RADIUS = 20
COPPER_SLAVE_MAX_ATTEMPTS = 3

COMMAND_SEPARATORS = r"[，,/\s]+"
COPPER_COMMAND_LEVEL_MAP: dict[str, str | None] = {
    "铜": None,
    "8铜": "8铜",
    "9铜": "9铜",
    "10铜": "10铜",
}
COPPER_SLAVE_COMMANDS = {"迁城"}

SEASON_CHOICE_MAP = {
    "1": {"code": "S1", "label": "S1", "scenario": "S1"},
    "2": {"code": "英雄命世", "label": "英雄命世", "scenario": "英雄命世"},
}
SEASON_CODE_TO_LABEL = {item["code"]: item["label"] for item in SEASON_CHOICE_MAP.values()}
SEASON_CODE_TO_SCENARIO = {item["code"]: item["scenario"] for item in SEASON_CHOICE_MAP.values()}

# --- Templates ---

WELCOME_TEMPLATE_DEFAULT = """欢迎关注！本服务号的功能纯纯为爱发电，敬请期待更多能力，目前功能：\n功能1：<a href="{upload_link}">同盟数据管理（同盟管理）</a>\n功能2：资源州找铜（见底部菜单）"""



# --- Helper Functions ---

def _offset_to_cube(x_val: int, y_val: int) -> tuple[int, int, int]:
    z_val = y_val - (x_val + (x_val & 1)) // 2
    y_cube = -x_val - z_val
    return x_val, y_cube, z_val

def _hex_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    ax, ay, az = _offset_to_cube(a[0], a[1])
    bx, by, bz = _offset_to_cube(b[0], b[1])
    return max(abs(ax - bx), abs(ay - by), abs(az - bz))

class _TemplateDefaults(dict):
    def __missing__(self, key):
        return ""

# --- Service Manager Class ---

class ServiceAccountManager:
    def __init__(self, app_config: dict[str, Any], wechat_api: WeChatServiceAPI):
        self.app_config = app_config
        self.wechat_api = wechat_api
        
        # Configuration
        self.upload_base = app_config.get("PUBLIC_BASE_URL", "").rstrip("/")
        self.upload_serializer = URLSafeSerializer(app_config["SECRET_KEY"], salt="sanbot-upload-link")
        self.compare_image_serializer = URLSafeSerializer(app_config["SECRET_KEY"], salt="sanbot-compare-image")
        self.compare_image_dir = os.path.join(app_config.get("UPLOAD_FOLDER", "/tmp"), "compare_images")
        self.welcome_template = app_config.get("SERVICE_WELCOME_MESSAGE", WELCOME_TEMPLATE_DEFAULT)
        
        # State
        self.pending_season_users: set[str] = set()
        self.pending_season_lock = threading.RLock()
        
        self.pending_copper_requests: dict[str, dict[str, object]] = {}
        self.pending_copper_lock = threading.RLock()
        
        self.pending_copper_slave_requests: dict[str, dict[str, object]] = {}
        self.pending_copper_slave_lock = threading.RLock()

        # Initialization
        try:
            os.makedirs(self.compare_image_dir, exist_ok=True)
        except OSError:
            logging.getLogger(__name__).exception("Failed to create compare_images directory")

    # --- Core Logic: Message Handling ---

    def _build_welcome_message(self, user_id: str) -> str:
        if not user_id:
            return self.welcome_template
        upload_link = ""
        if self.upload_base:
            token = self.upload_serializer.dumps({"user_id": user_id})
            upload_link = f"{self.upload_base}/sanbot/service/upload?token={token}"
        if "{" in self.welcome_template and "}" in self.welcome_template:
            text = self.welcome_template.format_map(_TemplateDefaults(upload_link=upload_link))
        else:
            text = self.welcome_template
        if upload_link and upload_link not in text:
            text = f"{text}\n{upload_link}"
        return text.strip()

    def _cancel_pending_copper_sessions(
        self,
        user_id: str,
        *,
        cancel_radar: bool = True,
        cancel_slave: bool = True,
    ) -> None:
        if cancel_radar:
            with self.pending_copper_lock:
                self.pending_copper_requests.pop(user_id, None)
        if cancel_slave:
            with self.pending_copper_slave_lock:
                self.pending_copper_slave_requests.pop(user_id, None)

    def _validate_coordinate_or_notify(self, user_id: str, coord_x: int, coord_y: int) -> bool:
        if (
            coord_x < COPPER_COORD_MIN
            or coord_x > COPPER_COORD_MAX
            or coord_y < COPPER_COORD_MIN
            or coord_y > COPPER_COORD_MAX
        ):
            self.wechat_api.send_text_message(user_id, "坐标超出范围（1-1500），请重新输入。")
            return False
        return True

    def _get_season_or_notify(self, user_id: str, feature_label: str) -> str | None:
        try:
            season_code = get_user_selected_season(current_app.config, user_id)
        except Exception:  # noqa: BLE001
            current_app.logger.exception("%s season fetch failed user=%s", feature_label, user_id)
            self.wechat_api.send_text_message(user_id, "暂时无法获取赛季信息，请稍后重试。")
            return None
        if not season_code:
            self.wechat_api.send_text_message(user_id, "请先设置赛季，再使用相关功能。")
            self._prompt_season_selection(user_id)
            return None
        if season_code not in SEASON_CODE_TO_SCENARIO:
            self.wechat_api.send_text_message(user_id, "赛季资源配置暂不可用。")
            return None
        return season_code

    def _normalize_command_token(self, token: str) -> str:
        return token.strip().replace(" ", "")

    def _parse_command_coordinate_input(self, text: str) -> tuple[str, int, int] | None:
        cleaned = (text or "").strip()
        if not cleaned:
            return None
        parts = [segment for segment in re.split(COMMAND_SEPARATORS, cleaned) if segment]
        if len(parts) != 3:
            return None
        command_raw = parts[0].strip()
        try:
            x_val = int(parts[1])
            y_val = int(parts[2])
        except ValueError:
            return None
        return command_raw, x_val, y_val

    def _parse_coordinate_input(self, text: str) -> tuple[int, int] | None:
        cleaned = (text or "").strip()
        if not cleaned:
            return None
        parts = [segment for segment in re.split(r"[，,/\s]+", cleaned) if segment]
        if len(parts) != 2:
            return None
        try:
            x_val = int(parts[0])
            y_val = int(parts[1])
        except ValueError:
            return None
        return x_val, y_val

    def _parse_level_coordinate_input(self, text: str) -> tuple[str, int, int] | None:
        cleaned = (text or "").strip()
        if not cleaned:
            return None
        parts = [segment for segment in re.split(r"[，,\/\s]+", cleaned) if segment]
        if len(parts) != 3:
            return None
        level_raw = parts[0].strip()
        match = re.fullmatch(r"(\d+)\s*铜", level_raw)
        if not match:
            return None
        level_token = f"{match.group(1)}铜"
        try:
            x_val = int(parts[1])
            y_val = int(parts[2])
        except ValueError:
            return None
        return level_token, x_val, y_val

    # --- Feature: Season Selection ---

    def _prompt_season_selection(self, user_id: str) -> None:
        if not user_id:
            return
        try:
            current_selection = get_user_selected_season(current_app.config, user_id)
        except Exception:  # noqa: BLE001
            current_app.logger.exception("Fetch user season failed user=%s", user_id)
            current_selection = None
        current_label = SEASON_CODE_TO_LABEL.get(current_selection or "", "未设置")
        lines = [
            "赛季设置",
            "请回复数字选择赛季：",
            "1. S1",
            "2. 英雄命世",
            f"当前赛季：{current_label}",
        ]
        message = "\n".join(lines)
        with self.pending_season_lock:
            self.pending_season_users.add(user_id)
        self.wechat_api.send_text_message(user_id, message)

    # --- Feature: Copper Radar ---

    def _find_nearest_resources(
        self,
        user_id: str,
        season_code: str,
        coord: tuple[int, int],
        level_filter: str | None = None,
    ) -> tuple[str | None, list[dict[str, object]]]:
        scenario = SEASON_CODE_TO_SCENARIO.get(season_code)
        if not scenario:
            current_app.logger.warning("Copper radar scenario missing user=%s season=%s", user_id, season_code)
            return "赛季资源数据缺失，请联系管理员。", []
        try:
            rows = list_map_resources_by_scenario(current_app.config, scenario)
        except Exception:  # noqa: BLE001
            current_app.logger.exception("Copper radar query failed user=%s season=%s", user_id, season_code)
            return "查询资源数据失败，请稍后重试。", []
        if not rows:
            return "没有找到该赛季的资源数据。", []
        results: list[dict[str, object]] = []
        for row in rows:
            try:
                target = (int(row["coord_x"]), int(row["coord_y"]))
            except (KeyError, TypeError, ValueError):
                continue
            resource_text = str(row.get("resource_level", "-")).strip()
            if level_filter and not resource_text.startswith(level_filter):
                continue
            distance = _hex_distance(coord, target)
            results.append(
                {
                    "prefecture": row.get("prefecture", "-"),
                    "resource_level": resource_text or "-",
                    "coord_x": target[0],
                    "coord_y": target[1],
                    "distance": distance,
                }
            )
        ordered = sorted(results, key=lambda item: (int(item["distance"]), str(item["resource_level"]), str(item["prefecture"])))
        return None, ordered[:10]

    def _send_copper_radar_response(
        self,
        user_id: str,
        season_code: str,
        coord_x: int,
        coord_y: int,
        level_filter: str | None,
    ) -> bool:
        error, nearest = self._find_nearest_resources(user_id, season_code, (coord_x, coord_y), level_filter)
        if error:
            self.wechat_api.send_text_message(user_id, error)
            return False
        label = SEASON_CODE_TO_LABEL.get(season_code, season_code)
        header = [
            f"铜矿雷达结果（{label}）",
            f"目标坐标：{coord_x},{coord_y}",
        ]
        if level_filter:
            header.append(f"资源限定：{level_filter}")
        if not nearest:
            if level_filter:
                header.append(f"未找到附近的 {level_filter} 资源点。")
            else:
                header.append("未找到附近的资源点。")
            self.wechat_api.send_text_message(user_id, "\n".join(header))
            return True
        lines = header + [""]
        for idx, item in enumerate(nearest, start=1):
            lines.append(
                f"{idx}. {item['prefecture']} | {item['resource_level']} | 坐标 {item['coord_x']},{item['coord_y']} | 距离 {item['distance']}"
            )
        self.wechat_api.send_text_message(user_id, "\n".join(lines))
        return True

    def _prompt_copper_coordinate(self, user_id: str, season_code: str) -> None:
        label = SEASON_CODE_TO_LABEL.get(season_code, season_code)
        tips = [
            f"铜矿雷达（{label}）",
            "请输入目标坐标，范围 1-1500。",
            "支持格式：520,880 / 520，880 / 520/880 / 520 880",
        ]
        message = "\n".join(tips)
        self._cancel_pending_copper_sessions(user_id, cancel_radar=False, cancel_slave=True)
        with self.pending_copper_lock:
            self.pending_copper_requests[user_id] = {"season": season_code, "attempts": 0}
        self.wechat_api.send_text_message(user_id, message)

    def _handle_copper_coordinate_reply(self, user_id: str, text: str) -> bool:
        with self.pending_copper_lock:
            state = self.pending_copper_requests.get(user_id)
        if not state:
            return False
        season_code = str(state.get("season") or "")
        attempts_used = int(state.get("attempts") or 0)
        level_filter = None
        parsed_with_level = self._parse_level_coordinate_input(text)
        if parsed_with_level:
            level_filter, coord_x, coord_y = parsed_with_level
            parsed = (coord_x, coord_y)
        else:
            parsed = self._parse_coordinate_input(text)
        if not parsed:
            attempts_used += 1
            remaining = COPPER_MAX_ATTEMPTS - attempts_used
            with self.pending_copper_lock:
                if remaining > 0:
                    state["attempts"] = attempts_used
                    self.pending_copper_requests[user_id] = state
                else:
                    self.pending_copper_requests.pop(user_id, None)
            if remaining > 0:
                self.wechat_api.send_text_message(
                    user_id,
                    f"坐标格式无效，请重新输入，剩余{remaining}次机会。支持示例：520,880。",
                )
            else:
                self.wechat_api.send_text_message(user_id, "多次输入无效，铜矿雷达已取消，请重新点击菜单。")
            return True

        coord_x, coord_y = parsed
        if coord_x < COPPER_COORD_MIN or coord_x > COPPER_COORD_MAX or coord_y < COPPER_COORD_MIN or coord_y > COPPER_COORD_MAX:
            attempts_used += 1
            remaining = COPPER_MAX_ATTEMPTS - attempts_used
            with self.pending_copper_lock:
                if remaining > 0:
                    state["attempts"] = attempts_used
                    self.pending_copper_requests[user_id] = state
                else:
                    self.pending_copper_requests.pop(user_id, None)
            if remaining > 0:
                self.wechat_api.send_text_message(
                    user_id,
                    f"坐标超出范围（1-1500），请重新输入，剩余{remaining}次机会。",
                )
            else:
                self.wechat_api.send_text_message(user_id, "多次输入无效，铜矿雷达已取消，请重新点击菜单。")
            return True

        with self.pending_copper_lock:
            self.pending_copper_requests.pop(user_id, None)

        current_app.logger.info(
            "Copper radar input user=%s season=%s coord=%s,%s level_filter=%s",
            user_id,
            season_code,
            coord_x,
            coord_y,
            level_filter or "-",
        )
        self._send_copper_radar_response(user_id, season_code, coord_x, coord_y, level_filter)
        return True

    def _handle_copper_menu_click(self, user_id: str) -> None:
        if not user_id:
            return
        try:
            season_code = get_user_selected_season(current_app.config, user_id)
        except Exception:  # noqa: BLE001
            current_app.logger.exception("Copper radar season fetch failed user=%s", user_id)
            self.wechat_api.send_text_message(user_id, "暂时无法获取赛季信息，请稍后重试。")
            return
        if not season_code:
            with self.pending_copper_lock:
                self.pending_copper_requests.pop(user_id, None)
            with self.pending_copper_slave_lock:
                self.pending_copper_slave_requests.pop(user_id, None)
            self.wechat_api.send_text_message(user_id, "请先设置赛季，再使用铜矿雷达。")
            self._prompt_season_selection(user_id)
            return
        if season_code not in SEASON_CODE_TO_SCENARIO:
            self.wechat_api.send_text_message(user_id, "赛季资源配置暂不可用。")
            return
        current_app.logger.info("Copper radar menu clicked user=%s season=%s", user_id, season_code)
        self._prompt_copper_coordinate(user_id, season_code)

    def _handle_instruction_copper(self, user_id: str, coord_x: int, coord_y: int, level_filter: str | None) -> bool:
        if not self._validate_coordinate_or_notify(user_id, coord_x, coord_y):
            return True
        season_code = self._get_season_or_notify(user_id, "铜矿雷达")
        if not season_code:
            return True
        self._cancel_pending_copper_sessions(user_id)
        current_app.logger.info(
            "Copper radar command user=%s season=%s coord=%s,%s level_filter=%s",
            user_id,
            season_code,
            coord_x,
            coord_y,
            level_filter or "-",
        )
        self._send_copper_radar_response(user_id, season_code, coord_x, coord_y, level_filter)
        return True

    # --- Feature: Copper Slave (Migration Recommendation) ---

    def _is_eight_copper(self, level: object) -> bool:
        text = str(level or "").strip()
        return text.startswith("8") and "铜" in text

    def _infer_prefecture(self, rows: list[dict[str, object]], coord: tuple[int, int]) -> tuple[str | None, int]:
        best_prefecture = None
        best_distance = None
        for row in rows:
            try:
                candidate = (int(row.get("coord_x")), int(row.get("coord_y")))
            except (TypeError, ValueError):
                continue
            distance = _hex_distance(coord, candidate)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_prefecture = str(row.get("prefecture", ""))
        return best_prefecture, best_distance if best_distance is not None else 0

    def _compute_copper_slave_recommendation(
        self,
        user_id: str,
        season_code: str,
        coord: tuple[int, int],
    ) -> tuple[str | None, dict[str, object] | None]:
        scenario = SEASON_CODE_TO_SCENARIO.get(season_code)
        if not scenario:
            current_app.logger.warning("Copper slave scenario missing user=%s season=%s", user_id, season_code)
            return "赛季资源数据缺失，请联系管理员。", None
        try:
            rows = list_map_resources_by_scenario(current_app.config, scenario)
        except Exception:  # noqa: BLE001
            current_app.logger.exception("Copper slave query failed user=%s season=%s", user_id, season_code)
            return "查询资源数据失败，请稍后重试。", None
        if not rows:
            return "没有找到该赛季的资源数据。", None

        prepared: list[dict[str, object]] = []
        for row in rows:
            try:
                cx = int(row.get("coord_x"))
                cy = int(row.get("coord_y"))
            except (TypeError, ValueError):
                continue
            prepared.append(
                {
                    "prefecture": str(row.get("prefecture", "")),
                    "resource_level": row.get("resource_level"),
                    "coord_x": cx,
                    "coord_y": cy,
                }
            )

        prefecture, prefecture_distance = self._infer_prefecture(prepared, coord)
        if not prefecture:
            return "无法识别目标坐标所属郡，请确认坐标是否正确。", None

        same_pref = [row for row in prepared if row.get("prefecture") == prefecture]
        if not same_pref:
            return "当前郡未找到资源数据。", None

        eight_points = [row for row in same_pref if self._is_eight_copper(row.get("resource_level"))]
        same_pref_coords = [(int(row["coord_x"]), int(row["coord_y"])) for row in same_pref]
        other_pref_coords = [
            (int(row["coord_x"]), int(row["coord_y"]))
            for row in prepared
            if row.get("prefecture") != prefecture
        ]

        other_relevant_coords = [
            pt
            for pt in other_pref_coords
            if _hex_distance(coord, pt) <= COPPER_SLAVE_RADIUS_LIMIT + COPPER_SLAVE_CLUSTER_RADIUS + 20
        ]

        eight_points_coords = [(int(row["coord_x"]), int(row["coord_y"])) for row in eight_points]
        eight_points_relevant = [
            pt
            for pt in eight_points_coords
            if _hex_distance(coord, pt) <= COPPER_SLAVE_RADIUS_LIMIT + COPPER_SLAVE_CLUSTER_RADIUS
        ]

        if not eight_points_relevant:
            eight_points_relevant = eight_points_coords

        # --- Vectorized Optimization Start ---
        
        # 1. Prepare coordinates arrays
        same_pref_arr = np.array(same_pref_coords) # (M, 2)
        other_relevant_arr = np.array(other_relevant_coords) if other_relevant_coords else np.empty((0, 2))
        eight_points_arr = np.array(eight_points_relevant) if eight_points_relevant else np.empty((0, 2))
        
        # 2. Generate candidate grid
        x_min = max(COPPER_COORD_MIN, coord[0] - COPPER_SLAVE_RADIUS_LIMIT)
        x_max = min(COPPER_COORD_MAX, coord[0] + COPPER_SLAVE_RADIUS_LIMIT)
        y_min = max(COPPER_COORD_MIN, coord[1] - COPPER_SLAVE_RADIUS_LIMIT)
        y_max = min(COPPER_COORD_MAX, coord[1] + COPPER_SLAVE_RADIUS_LIMIT)
        
        x_range = np.arange(x_min, x_max + 1)
        y_range = np.arange(y_min, y_max + 1)
        xx, yy = np.meshgrid(x_range, y_range)
        candidates = np.stack([xx.ravel(), yy.ravel()], axis=1) # (N, 2)
        
        if len(candidates) == 0:
             return "距离目标 100 以内未找到合适的迁城坐标。", None

        # Helper for vectorized distance
        def get_hex_dist_vec(pts_a, pts_b):
            # pts_a: (N, 2), pts_b: (M, 2)
            # x is col 0, y is col 1
            xa, ya = pts_a[:, 0], pts_a[:, 1]
            xb, yb = pts_b[:, 0], pts_b[:, 1]
            
            za = ya - (xa + (xa & 1)) // 2
            ya_cube = -xa - za
            cube_a = np.stack([xa, ya_cube, za], axis=1) # (N, 3)
            
            zb = yb - (xb + (xb & 1)) // 2
            yb_cube = -xb - zb
            cube_b = np.stack([xb, yb_cube, zb], axis=1) # (M, 3)
            
            # (N, 1, 3) - (1, M, 3) -> (N, M, 3)
            diff = np.abs(cube_a[:, None, :] - cube_b[None, :, :])
            return np.max(diff, axis=2) # (N, M)

        # 3. Filter by distance to target
        target_arr = np.array([coord])
        dists_to_target = get_hex_dist_vec(candidates, target_arr)[:, 0]
        
        mask_target = dists_to_target <= COPPER_SLAVE_RADIUS_LIMIT
        candidates = candidates[mask_target]
        dists_to_target = dists_to_target[mask_target]
        
        if len(candidates) == 0:
             return "距离目标 100 以内未找到合适的迁城坐标。", None

        # 4. Filter by Prefecture
        # Distance to nearest same-pref
        dists_same_matrix = get_hex_dist_vec(candidates, same_pref_arr)
        min_dists_same = np.min(dists_same_matrix, axis=1)
        
        if len(other_relevant_arr) > 0:
            dists_other_matrix = get_hex_dist_vec(candidates, other_relevant_arr)
            min_dists_other = np.min(dists_other_matrix, axis=1)
            # Keep if dist_same <= dist_other (strictly, code said: if dist_other < dist_same: continue. So keep if dist_other >= dist_same)
            mask_pref = min_dists_other >= min_dists_same
            
            candidates = candidates[mask_pref]
            dists_to_target = dists_to_target[mask_pref]
            min_dists_same = min_dists_same[mask_pref]
            
        if len(candidates) == 0:
             return "距离目标 100 以内未找到合适的迁城坐标。", None

        # 5. Count 8-Copper
        near_counts = np.zeros(len(candidates), dtype=int)
        far_counts = np.zeros(len(candidates), dtype=int)
        
        if len(eight_points_arr) > 0:
            dists_eight = get_hex_dist_vec(candidates, eight_points_arr)
            
            mask_near = dists_eight <= COPPER_SLAVE_NEAR_RADIUS
            mask_far = (dists_eight > COPPER_SLAVE_NEAR_RADIUS) & (dists_eight <= COPPER_SLAVE_CLUSTER_RADIUS)
            
            near_counts = np.sum(mask_near, axis=1)
            far_counts = np.sum(mask_far, axis=1)
            
        # 6. Rank and return
        results = []
        for i in range(len(candidates)):
            results.append({
                "coord_x": int(candidates[i, 0]),
                "coord_y": int(candidates[i, 1]),
                "distance_to_target": int(dists_to_target[i]),
                "eight_count": int(near_counts[i] + far_counts[i]),
                "near_eight_count": int(near_counts[i]),
                "far_eight_count": int(far_counts[i]),
                "dist_same_pref": int(min_dists_same[i]),
            })
            
        ranked = sorted(
            results,
            key=lambda item: (
                -item["near_eight_count"],
                -item["far_eight_count"],
                item["distance_to_target"],
                item["dist_same_pref"],
                item["coord_x"],
                item["coord_y"],
            ),
        )
        # --- Vectorized Optimization End ---

        def _collect_neighbors(center: tuple[int, int]) -> list[dict[str, int]]:
            details: list[dict[str, int]] = []
            for point in eight_points_relevant:
                dist_val = _hex_distance(center, point)
                if dist_val <= COPPER_SLAVE_CLUSTER_RADIUS:
                    details.append(
                        {
                            "coord_x": point[0],
                            "coord_y": point[1],
                            "distance": dist_val,
                        }
                    )
            return sorted(details, key=lambda item: (item["distance"], item["coord_x"], item["coord_y"]))

        best = dict(ranked[0])
        best_center = (best["coord_x"], best["coord_y"])
        best_neighbors = _collect_neighbors(best_center)

        best["prefecture"] = prefecture
        best["target_coord"] = {"coord_x": coord[0], "coord_y": coord[1]}
        best["neighbors"] = best_neighbors
        best["distance_to_target"] = best.get("distance_to_target", 0)
        best["eight_count"] = best.get("eight_count", 0)
        best["near_eight_count"] = best.get("near_eight_count", 0)
        best["far_eight_count"] = best.get("far_eight_count", 0)
        best["ranked_candidates"] = [dict(item) for item in ranked[:5]]
        best["prefecture_distance"] = prefecture_distance
        return None, best

    def _send_copper_slave_recommendation(
        self,
        user_id: str,
        season_code: str,
        coord_x: int,
        coord_y: int,
    ) -> bool:
        current_app.logger.info(
            "Copper slave computation start user=%s season=%s coord=%s,%s",
            user_id,
            season_code,
            coord_x,
            coord_y,
        )
        self.wechat_api.send_text_message(
            user_id,
            "任务启动，预计耗时约 5-10 秒，请耐心等待。",
        )

        error, recommendation = self._compute_copper_slave_recommendation(user_id, season_code, (coord_x, coord_y))
        if error:
            self.wechat_api.send_text_message(user_id, error)
            return False
        if not recommendation:
            self.wechat_api.send_text_message(user_id, "未找到合适的迁城坐标，请尝试更换目标位置。")
            return False

        label = SEASON_CODE_TO_LABEL.get(season_code, season_code)
        prefecture = recommendation.get("prefecture", "-")
        target_info = recommendation.get("target_coord", {})
        best_x = recommendation.get("coord_x")
        best_y = recommendation.get("coord_y")
        distance = recommendation.get("distance_to_target")
        eight_count = recommendation.get("eight_count", 0)
        near_count = recommendation.get("near_eight_count", 0)
        far_count = recommendation.get("far_eight_count", 0)
        neighbors = recommendation.get("neighbors", [])
        total_20 = near_count + far_count if recommendation.get("far_eight_count") is not None else eight_count

        lines = [
            f"铜奴迁城推荐（{label}）",
            f"目标A：{target_info.get('coord_x')},{target_info.get('coord_y')}（{prefecture}）",
            "",
            f"推荐迁城点：{best_x},{best_y}（距A {distance}，5格内8铜 {near_count} 块，20格内8铜 {total_20} 块）",
        ]

        if eight_count:
            lines.append("附近 8 铜分布：")
            for idx, neighbor in enumerate(neighbors[:10], start=1):
                lines.append(
                    f"{idx}. 坐标 {neighbor['coord_x']},{neighbor['coord_y']} | 距离 {neighbor['distance']}"
                )
        else:
            lines.append("附近未找到 8 铜，可考虑扩大范围或更换坐标。")

        extra_candidates = recommendation.get("ranked_candidates", [])[1:3]
        if extra_candidates:
            lines.append("")
            lines.append("备选坐标：")
            for item in extra_candidates:
                lines.append(
                    f"- {item['coord_x']},{item['coord_y']}（距A {item['distance_to_target']}，5格 {item.get('near_eight_count', 0)} 块，20格 {item.get('near_eight_count', 0) + item.get('far_eight_count', 0)} 块）"
                )

        self.wechat_api.send_text_message(user_id, "\n".join(lines))
        return True

    def _schedule_copper_slave_task(
        self,
        user_id: str,
        season_code: str,
        coord_x: int,
        coord_y: int,
        *,
        source: str,
    ) -> None:
        app_obj = current_app._get_current_object()

        def _worker() -> None:
            with app_obj.app_context():
                try:
                    self._send_copper_slave_recommendation(user_id, season_code, coord_x, coord_y)
                finally:
                    with self.pending_copper_slave_lock:
                        entry = self.pending_copper_slave_requests.get(user_id)
                        if entry and entry.get("source") == source:
                            self.pending_copper_slave_requests.pop(user_id, None)

        thread = threading.Thread(
            target=_worker,
            name=f"copper-slave-{user_id}",
            daemon=True,
        )
        thread.start()

    def _prompt_copper_slave_coordinate(self, user_id: str, season_code: str) -> None:
        label = SEASON_CODE_TO_LABEL.get(season_code, season_code)
        tips = [
            f"铜奴迁城推荐（{label}）",
            "请输入目标坐标A，范围 1-1500。",
            "支持格式：520,880 / 520，880 / 520/880 / 520 880",
            "我们会在同郡范围内寻找 20 格内 8 铜最多的点（距离A ≤ 100）。",
        ]
        message = "\n".join(tips)
        self._cancel_pending_copper_sessions(user_id, cancel_radar=True, cancel_slave=True)
        with self.pending_copper_slave_lock:
            self.pending_copper_slave_requests[user_id] = {"season": season_code, "attempts": 0}
        self.wechat_api.send_text_message(user_id, message)

    def _handle_copper_slave_reply(self, user_id: str, text: str) -> bool:
        with self.pending_copper_slave_lock:
            state = self.pending_copper_slave_requests.get(user_id)
        if not state:
            return False
        if state.get("in_progress"):
            self.wechat_api.send_text_message(
                user_id,
                "任务仍在计算，请稍候。",
            )
            return True
        season_code = str(state.get("season") or "")
        attempts_used = int(state.get("attempts") or 0)

        parsed = self._parse_coordinate_input(text)
        if not parsed:
            attempts_used += 1
            remaining = COPPER_SLAVE_MAX_ATTEMPTS - attempts_used
            with self.pending_copper_slave_lock:
                if remaining > 0:
                    state["attempts"] = attempts_used
                    self.pending_copper_slave_requests[user_id] = state
                else:
                    self.pending_copper_slave_requests.pop(user_id, None)
            if remaining > 0:
                self.wechat_api.send_text_message(
                    user_id,
                    f"坐标格式无效，请重新输入，剩余{remaining}次机会。支持示例：520,880。",
                )
            else:
                self.wechat_api.send_text_message(user_id, "多次输入无效，已取消铜奴推荐，请重新点击菜单。")
            return True

        coord_x, coord_y = parsed
        if coord_x < COPPER_COORD_MIN or coord_x > COPPER_COORD_MAX or coord_y < COPPER_COORD_MIN or coord_y > COPPER_COORD_MAX:
            attempts_used += 1
            remaining = COPPER_SLAVE_MAX_ATTEMPTS - attempts_used
            with self.pending_copper_slave_lock:
                if remaining > 0:
                    state["attempts"] = attempts_used
                    self.pending_copper_slave_requests[user_id] = state
                else:
                    self.pending_copper_slave_requests.pop(user_id, None)
            if remaining > 0:
                self.wechat_api.send_text_message(
                    user_id,
                    f"坐标超出范围（1-1500），请重新输入，剩余{remaining}次机会。",
                )
            else:
                self.wechat_api.send_text_message(user_id, "多次输入无效，已取消铜奴推荐，请重新点击菜单。")
            return True

        with self.pending_copper_slave_lock:
            state["in_progress"] = True
            state["source"] = state.get("source", "reply")
            self.pending_copper_slave_requests[user_id] = state
        self._schedule_copper_slave_task(
            user_id,
            season_code,
            coord_x,
            coord_y,
            source="reply",
        )
        return True

    def _handle_copper_slave_menu_click(self, user_id: str) -> None:
        if not user_id:
            return
        try:
            season_code = get_user_selected_season(current_app.config, user_id)
        except Exception:  # noqa: BLE001
            current_app.logger.exception("Copper slave season fetch failed user=%s", user_id)
            self.wechat_api.send_text_message(user_id, "暂时无法获取赛季信息，请稍后重试。")
            return
        if not season_code:
            with self.pending_copper_lock:
                self.pending_copper_requests.pop(user_id, None)
            with self.pending_copper_slave_lock:
                self.pending_copper_slave_requests.pop(user_id, None)
            self.wechat_api.send_text_message(user_id, "请先设置赛季，再使用铜奴推荐。")
            self._prompt_season_selection(user_id)
            return
        if season_code not in SEASON_CODE_TO_SCENARIO:
            self.wechat_api.send_text_message(user_id, "赛季资源配置暂不可用。")
            return
        current_app.logger.info("Copper slave menu clicked user=%s season=%s", user_id, season_code)
        self._prompt_copper_slave_coordinate(user_id, season_code)

    def _handle_instruction_slave(self, user_id: str, coord_x: int, coord_y: int) -> bool:
        with self.pending_copper_slave_lock:
            existing = self.pending_copper_slave_requests.get(user_id)
            if existing and existing.get("in_progress"):
                self.wechat_api.send_text_message(user_id, "任务仍在计算，请稍候。")
                return True
        if not self._validate_coordinate_or_notify(user_id, coord_x, coord_y):
            return True
        season_code = self._get_season_or_notify(user_id, "铜奴迁城推荐")
        if not season_code:
            return True
        self._cancel_pending_copper_sessions(user_id)
        with self.pending_copper_slave_lock:
            self.pending_copper_slave_requests[user_id] = {
                "season": season_code,
                "in_progress": True,
                "source": "instruction",
            }
        self._schedule_copper_slave_task(
            user_id,
            season_code,
            coord_x,
            coord_y,
            source="instruction",
        )
        return True

    # --- Feature: Instructions ---

    def _send_instruction_help(self, user_id: str) -> None:
        self._cancel_pending_copper_sessions(user_id)
        current_app.logger.info("Instruction help requested user=%s", user_id)
        lines = [
            "指令说明",
            "格式：指令 坐标X 坐标Y（分隔符支持空格、逗号、顿号、斜杠）",
            "坐标范围：1-1500",
            "",
            "铜 / 8铜 / 9铜 / 10铜 + 坐标 → 铜矿雷达查询",
            "迁城 + 坐标 → 铜奴迁城推荐",
            "",
            "示例：",
            "铜 520 880",
            "8铜，520，880",
            "迁城/520/880",
        ]
        self.wechat_api.send_text_message(user_id, "\n".join(lines))

    def _handle_instruction_command(self, user_id: str, command_raw: str, coord_x: int, coord_y: int) -> bool:
        token = self._normalize_command_token(command_raw)
        current_app.logger.info(
            "Instruction command received user=%s token=%s coord=%s,%s",
            user_id,
            token or command_raw,
            coord_x,
            coord_y,
        )
        if token in COPPER_COMMAND_LEVEL_MAP:
            level_filter = COPPER_COMMAND_LEVEL_MAP[token]
            return self._handle_instruction_copper(user_id, coord_x, coord_y, level_filter)
        if token in COPPER_SLAVE_COMMANDS:
            return self._handle_instruction_slave(user_id, coord_x, coord_y)
        self.wechat_api.send_text_message(
            user_id,
            "未识别的指令，请发送“铜 520 880”或“迁城 520 880”等格式，可点击菜单查看说明。",
        )
        current_app.logger.info(
            "Instruction command rejected user=%s token=%s",
            user_id,
            token or command_raw,
        )
        return True

    # --- Main Handlers ---

    def handle_text_message(self, user_id: str, content: str):
        if not user_id:
            return
        text = (content or "").strip()
        with self.pending_season_lock:
            awaiting_selection = user_id in self.pending_season_users
            if awaiting_selection:
                self.pending_season_users.discard(user_id)
        if awaiting_selection:
            choice = SEASON_CHOICE_MAP.get(text)
            if choice:
                try:
                    set_user_selected_season(current_app.config, user_id, choice["code"])
                    current_app.logger.info(
                        "Season selection success user=%s season=%s", user_id, choice["code"]
                    )
                    self.wechat_api.send_text_message(user_id, f"赛季已设置为 {choice['label']}。")
                except Exception:  # noqa: BLE001
                    current_app.logger.exception("Season selection save failed user=%s", user_id)
                    self.wechat_api.send_text_message(user_id, "赛季设置失败，请稍后重试。")
            else:
                current_app.logger.info(
                    "Season selection invalid user=%s input=%s", user_id, text
                )
                self.wechat_api.send_text_message(
                    user_id,
                    "赛季设置未生效，请重新点击菜单并回复 1 或 2。",
                )
            return

        command_payload = self._parse_command_coordinate_input(text)
        if command_payload:
            command_token, cmd_x, cmd_y = command_payload
            if self._handle_instruction_command(user_id, command_token, cmd_x, cmd_y):
                return

        if self._handle_copper_slave_reply(user_id, text):
            return

        if self._handle_copper_coordinate_reply(user_id, text):
            return

        if self._parse_coordinate_input(text):
            self._send_instruction_help(user_id)
            return

        self._send_instruction_help(user_id)

    def handle_callback(self):
        timestamp = request.args.get("timestamp", "")
        nonce = request.args.get("nonce", "")
        signature = request.args.get("signature", "")

        if request.method == "GET":
            echostr = request.args.get("echostr", "")
            verified = self.wechat_api.verify_url(signature, timestamp, nonce, echostr)
            return verified if verified else "invalid", 200

        encrypt_type = request.args.get("encrypt_type", "raw").lower()
        if encrypt_type != "raw":
            current_app.logger.warning("Unsupported encrypt type '%s', please switch to 明文模式", encrypt_type)
            return "success"

        if not self.wechat_api.verify_signature(signature, timestamp, nonce):
            current_app.logger.warning("Service account signature verification failed")
            return "signature error", 403

        try:
            xml_data = request.data.decode("utf-8")
            message = self.wechat_api.parse_message(xml_data)
            msg_type = message.get("MsgType", "")
            from_user = message.get("FromUserName", "")

            if msg_type == "event":
                event = message.get("Event", "")
                if event.lower() == "subscribe" and from_user:
                    welcome_text = self._build_welcome_message(from_user)
                    self.wechat_api.send_text_message(from_user, welcome_text)
                elif event.lower() == "click" and from_user:
                    event_key = (message.get("EventKey") or "").strip()
                    if event_key == "SET_SEASON_PLACEHOLDER":
                        self._cancel_pending_copper_sessions(from_user)
                        self._prompt_season_selection(from_user)
                    elif event_key == "FIND_COPPER":
                        self._handle_copper_menu_click(from_user)
                    elif event_key == "COPPER_SLAVE":
                        self._handle_copper_slave_menu_click(from_user)
                    elif event_key == "INSTRUCTIONS":
                        self._send_instruction_help(from_user)
            elif msg_type == "text":
                self.handle_text_message(from_user, message.get("Content", ""))
            else:
                if from_user:
                    self.handle_text_message(from_user, "")
        except Exception:  # noqa: BLE001
            current_app.logger.exception("Service callback processing failed")

        return "success"

    def handle_upload_entry(self):
        # Determine effective base URL: prefer configured PUBLIC_BASE_URL, fallback to request.url_root
        effective_base = self.upload_base
        if not effective_base:
            root = request.url_root.rstrip("/")
            if root.startswith("http://"):
                root = "https://" + root[len("http://"):]
            effective_base = root
        if not effective_base:
            return ("服务未配置 PUBLIC_BASE_URL，且无法推断站点地址。", 500)
        appid = self.app_config.get("FUWUHAO_APP_ID", "")
        secret = self.app_config.get("FUWUHAO_APP_SECRET", "")
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
        token = self.upload_serializer.dumps({"user_id": openid})
        return redirect(f"/sanbot/service/upload?token={token}")

    def handle_upload_page(self):
        token = request.values.get("token", "")
        if not token:
            return (
                render_template(
                    "upload.html",
                    message="缺少 token 参数",
                    success=False,
                    show_form=False,
                    instruction="-",
                    token="",
                ),
                400,
            )
        try:
            payload = self.upload_serializer.loads(token, max_age=1800)
        except BadSignature:
            return (
                render_template(
                    "upload.html",
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
                render_template(
                    "upload.html",
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
            return render_template(
                "upload.html",
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
                return render_template(
                    "upload.html",
                    message="删除成功。",
                    success=True,
                    show_form=True,
                    token=token,
                    uploads=upload_history,
                )
            else:
                current_app.logger.info("DataMgmt delete user=%s id=%s result=failure", user_id, upload_id)
                upload_history = list_uploads_by_user(current_app.config, user_id)
                return render_template(
                    "upload.html",
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
            return render_template(
                "upload.html",
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
        return render_template(
            "upload.html",
            message="，".join(parts),
            success=(successes > 0 and len(failures) == 0),
            show_form=True,
            token=token,
            uploads=upload_history,
        )

    def handle_compare(self):
        # Support both JSON (legacy) and Form (new)
        data = request.get_json(silent=True) or request.form
        token = data.get("token", "")
        if not token:
            return jsonify({"success": False, "message": "缺少 token 参数。"}), 400
        try:
            payload = self.upload_serializer.loads(token, max_age=1800)
        except BadSignature:
            return jsonify({"success": False, "message": "链接已失效，请刷新页面后重试。"}), 400

        user_id = payload.get("user_id")
        if not user_id:
            return jsonify({"success": False, "message": "无法识别用户身份。"}), 400

        upload_ids_raw = data.get("upload_ids")
        # Handle form list input or JSON list
        if not upload_ids_raw and "upload_ids[]" in data:
             upload_ids_raw = request.form.getlist("upload_ids[]")
        
        if not upload_ids_raw and isinstance(data, dict) and "upload_ids" in data:
             upload_ids_raw = data["upload_ids"]

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
            return jsonify({"success": False, "message": "分析失败，请稍后重试。"}), 500

        if not comparison.get("success"):
            message = comparison.get("error") or "分析失败，请稍后重试。"
            return jsonify({"success": False, "message": message}), 500

        rows = comparison.get("rows", [])
        value_field = comparison.get("value_field") or f"{metric_info['label']}差值"
        earlier_ts_value = comparison.get("earlier_ts") or earlier_meta.get("ts")
        later_ts_value = comparison.get("later_ts") or later_meta.get("ts")
        earlier_ts_display = FileAnalyzer._format_ts_shichen(earlier_ts_value) or str(earlier_ts_value or "")
        later_ts_display = FileAnalyzer._format_ts_shichen(later_ts_value) or str(later_ts_value or "")

        if not rows:
            return jsonify({"success": True, "message": "对比完成：暂无共同成员。"}), 200

        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        header_path = os.path.join(root_dir, "resources", "header.jpg")

        try:
            image_results = analyzer.save_compare_group_images(
                rows,
                value_field=value_field,
                metric_label=value_field,
                earlier_ts=earlier_ts_value,
                later_ts=later_ts_value,
                output_dir=self.compare_image_dir,
                header_path=header_path,
            )
        except FileNotFoundError as exc:
            current_app.logger.exception("Compare image header missing user=%s", user_id)
            return jsonify({"success": False, "message": str(exc)}), 500
        except Exception as exc:  # noqa: BLE001
            current_app.logger.exception("Compare image render failed user=%s", user_id)
            return jsonify({"success": False, "message": "生成图表失败，请稍后重试。"}), 500

        if not image_results:
            return jsonify({"success": True, "message": "对比完成，暂无图像输出。"}), 200

        base_url = self.upload_base or request.url_root.rstrip("/")
        if not base_url:
            base_url = request.url_root.rstrip("/")

        # Prepare data for template
        images_data = []
        for item in image_results:
            image_path = item.get("path") or ""
            if not image_path or not os.path.isfile(image_path):
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
            
            token = self.compare_image_serializer.dumps({
                "user_id": user_id,
                "file": filename,
                "name": friendly_name,
            })
            download_link = f"{base_url}/sanbot/service/compare-image?token={token}"
            
            images_data.append({
                "group": group_label,
                "count": count,
                "url": download_link,
                "filename": friendly_name
            })

        # Sort images: "全盟" first, then by count descending
        images_data.sort(key=lambda x: (0 if x["group"] == "全盟" else 1, -x["count"]))

        return render_template(
            "compare_result.html",
            token=token,
            metric_label=metric_info['label'],
            earlier_ts=earlier_ts_display,
            later_ts=later_ts_display,
            images=images_data
        )

    def handle_download_image(self):
        token = request.args.get("token", "")
        if not token:
            return ("缺少 token 参数。", 400)
        try:
            payload = self.compare_image_serializer.loads(token, max_age=1800)
        except BadSignature:
            return ("下载链接已失效，请重新发起对比。", 400)

        file_id = payload.get("file")
        if not file_id:
            return ("链接无效，缺少文件信息。", 400)

        file_path = os.path.join(self.compare_image_dir, file_id)
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
        except Exception:
            current_app.logger.exception("Image download failed")
            return ("文件下载失败，请稍后重试。", 500)

def create_service_blueprint(
    app_config,
    wechat_api: WeChatServiceAPI,
):
    bp = Blueprint("wechat_service", __name__)
    manager = ServiceAccountManager(app_config, wechat_api)

    @bp.route("/callback", methods=["GET", "POST"])
    def service_callback():
        return manager.handle_callback()

    @bp.route("/upload-entry", methods=["GET"])
    def upload_entry():
        return manager.handle_upload_entry()

    @bp.route("/upload", methods=["GET", "POST"])
    def upload_page():
        return manager.handle_upload_page()

    @bp.route("/compare", methods=["POST"])
    def compare_uploads():
        return manager.handle_compare()

    @bp.route("/compare-image", methods=["GET"])
    def download_compare_image():
        return manager.handle_download_image()

    return bp
