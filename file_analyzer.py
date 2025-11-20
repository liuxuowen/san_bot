"""
File analysis utilities for comparing files and generating reports
"""
import os
import re
import json
import difflib
import random
from datetime import datetime
from typing import Tuple, Dict, Any, List

import pandas as pd


def _load_font(size: int) -> object:
    from PIL import ImageFont

    candidates = (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    )
    for font_name in candidates:
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            continue
    return ImageFont.load_default()


class FileAnalyzer:
    """Handles file comparison and analysis"""
    
    def __init__(self):
        self.supported_formats = ['txt', 'csv', 'json', 'xlsx', 'xls']
    
    def analyze_files(self, file1_path: str, file2_path: str, instruction: str) -> Dict[str, Any]:
        """
        Analyze and compare two files based on the given instruction
        
        Args:
            file1_path: Path to the first file
            file2_path: Path to the second file
            instruction: Instruction for comparison
            
        Returns:
            Dictionary containing analysis results
        """
        try:
            # Determine file types
            file1_ext = os.path.splitext(file1_path)[1].lower().lstrip('.')
            file2_ext = os.path.splitext(file2_path)[1].lower().lstrip('.')
            
            # Read file contents
            content1 = self._read_file(file1_path, file1_ext)
            content2 = self._read_file(file2_path, file2_ext)
            
            # Perform comparison based on instruction
            comparison_result = self._compare_contents(content1, content2, instruction)
            
            # Generate report
            report = self._generate_report(
                file1_path, file2_path, instruction, comparison_result
            )
            
            return {
                'success': True,
                'report': report,
                'details': comparison_result
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'report': f"分析失败: {str(e)}"
            }
    
    def _read_file(self, file_path: str, file_ext: str) -> str:
        """Read file content based on file type"""
        if file_ext in ['txt', 'csv']:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        elif file_ext == 'json':
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.dumps(json.load(f), indent=2, ensure_ascii=False)
        elif file_ext in ['xlsx', 'xls']:
            try:
                import pandas as pd
                df = pd.read_excel(file_path)
                return df.to_string()
            except Exception:
                return "Excel文件读取失败"
        else:
            with open(file_path, 'rb') as f:
                return f.read().decode('utf-8', errors='ignore')
    
    def _compare_contents(self, content1: str, content2: str, instruction: str) -> Dict[str, Any]:
        """Compare file contents based on instruction"""
        instruction_lower = instruction.lower()
        
        # Split contents into lines for comparison
        lines1 = content1.splitlines()
        lines2 = content2.splitlines()
        
        # Calculate differences
        differ = difflib.Differ()
        diff = list(differ.compare(lines1, lines2))
        
        # Count changes
        added_lines = [line for line in diff if line.startswith('+ ')]
        removed_lines = [line for line in diff if line.startswith('- ')]
        common_lines = [line for line in diff if line.startswith('  ')]
        
        # Calculate similarity
        matcher = difflib.SequenceMatcher(None, content1, content2)
        similarity = matcher.ratio() * 100
        
        return {
            'total_lines_file1': len(lines1),
            'total_lines_file2': len(lines2),
            'added_lines': len(added_lines),
            'removed_lines': len(removed_lines),
            'common_lines': len(common_lines),
            'similarity_percentage': round(similarity, 2),
            'diff_preview': diff[:20],  # First 20 lines of diff
            'instruction': instruction
        }
    
    def _generate_report(self, file1: str, file2: str, instruction: str, 
                        comparison: Dict[str, Any]) -> str:
        """Generate a formatted report of the comparison"""
        report = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
文件对比分析报告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 分析指令: {instruction}

📁 文件信息:
  文件1: {os.path.basename(file1)}
  文件2: {os.path.basename(file2)}

📊 对比结果:
  • 文件1总行数: {comparison['total_lines_file1']}
  • 文件2总行数: {comparison['total_lines_file2']}
  • 相似度: {comparison['similarity_percentage']}%
  • 新增行数: {comparison['added_lines']}
  • 删除行数: {comparison['removed_lines']}
  • 相同行数: {comparison['common_lines']}

📝 结论:
"""
        
        # Generate conclusion based on similarity
        similarity = comparison['similarity_percentage']
        if similarity >= 95:
            report += "  两个文件内容基本相同，差异极小。"
        elif similarity >= 80:
            report += "  两个文件内容相似度较高，存在部分差异。"
        elif similarity >= 50:
            report += "  两个文件内容存在明显差异，但仍有相似之处。"
        else:
            report += "  两个文件内容差异较大。"
        
        report += f"\n\n  新增内容: {comparison['added_lines']} 行"
        report += f"\n  删除内容: {comparison['removed_lines']} 行"
        
        report += "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        return report

    # -------------------- Custom CSV Analysis for Alliance Stats --------------------
    @staticmethod
    def _parse_cn_timestamp_from_filename(filename: str) -> datetime:
        """Parse Chinese datetime from filename like 同盟统计YYYY年MM月DD日HH时MM分SS秒.csv"""
        base = os.path.basename(filename)
        name, _ = os.path.splitext(base)
        name = re.sub(r"\(\d+\)$", "", name)
        m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2})时(\d{1,2})分(\d{1,2})秒", name)
        if m:
            y, mo, d, h, mi, s = map(int, m.groups())
            return datetime(y, mo, d, h, mi, s)

        digits = re.search(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", name)
        if digits:
            y, mo, d, h, mi, s = map(int, digits.groups())
            return datetime(y, mo, d, h, mi, s)

        raise ValueError(f"无法从文件名解析时间戳: {filename}")

    @staticmethod
    def _normalize_header(name: str) -> str:
        return re.sub(r"\s+", "", str(name).replace('\ufeff', '').strip())

    @classmethod
    def _find_column(cls, columns: List[str], target: str) -> str | None:
        normalized_target = cls._normalize_header(target)
        for column in columns:
            if cls._normalize_header(column) == normalized_target:
                return column
        return None

    @classmethod
    def _read_member_stats_csv(cls, path: str, metric_column: str) -> pd.DataFrame:
        """Read CSV and return DataFrame with columns: 成员, 指标列, 分组"""
        df = pd.read_csv(path, encoding='utf-8-sig', skipinitialspace=True)
        raw_columns = list(map(str, df.columns))
        member_col = cls._find_column(raw_columns, '成员')
        metric_col = cls._find_column(raw_columns, metric_column)
        group_col = cls._find_column(raw_columns, '分组')
        if not member_col or not metric_col or not group_col:
            missing = []
            if not member_col:
                missing.append('成员')
            if not metric_col:
                missing.append(metric_column)
            if not group_col:
                missing.append('分组')
            raise ValueError(f"CSV缺少必要列: {','.join(missing)} ({path})。实际列: {', '.join(raw_columns)}")
        df = df[[member_col, metric_col, group_col]].copy()
        df.columns = ['成员', metric_column, '分组']
        df['成员'] = df['成员'].astype(str).str.strip()
        df['分组'] = df['分组'].astype(str).str.strip().replace({'': '未分组'})
        df[metric_column] = pd.to_numeric(df[metric_column], errors='coerce').fillna(0).astype(int)
        df = df.sort_values(metric_column).drop_duplicates(subset=['成员'], keep='last').reset_index(drop=True)
        return df

    @staticmethod
    def _calculate_member_metric_diff(
        df_early: pd.DataFrame,
        df_late: pd.DataFrame,
        metric_column: str,
        metric_display_name: str,
    ) -> Dict[str, Any]:
        required_cols = {'成员', metric_column, '分组'}
        if not required_cols.issubset(df_early.columns) or not required_cols.issubset(df_late.columns):
            missing = required_cols - set(df_early.columns)
            missing |= required_cols - set(df_late.columns)
            raise ValueError(f"成员数据缺少必要列: {', '.join(sorted(missing))}")

        early = df_early.rename(columns={metric_column: 'metric_early', '分组': '分组_早'}).copy()
        late = df_late.rename(columns={metric_column: 'metric_late', '分组': '分组_晚'}).copy()

        merged = pd.merge(early, late, on='成员', how='inner')
        if merged.empty:
            return {
                'success': True,
                'rows': [],
                'value_field': f"{metric_display_name}差值",
                'value_label': metric_display_name,
            }

        merged['分组'] = merged['分组_晚'].fillna(merged['分组_早']).replace({'': '未分组'}).fillna('未分组')
        merged['metric_early'] = pd.to_numeric(merged['metric_early'], errors='coerce').fillna(0)
        merged['metric_late'] = pd.to_numeric(merged['metric_late'], errors='coerce').fillna(0)
        merged['metric_diff'] = (merged['metric_late'] - merged['metric_early']).astype(int)

        metric_field = f"{metric_display_name}差值"
        result = (
            merged[['成员', '分组', 'metric_diff']]
            .rename(columns={'metric_diff': metric_field})
            .sort_values(by=['分组', metric_field], ascending=[True, False])
            .reset_index(drop=True)
        )
        rows: List[Dict[str, Any]] = result.to_dict(orient='records')
        return {
            'success': True,
            'rows': rows,
            'value_field': metric_field,
            'value_label': metric_display_name,
        }

    @staticmethod
    def _coerce_datetime(value) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if value is None:
            return None
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value)
            except Exception:
                return None
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            candidates = [
                text,
                text.replace("/", "-") if "/" in text else text,
            ]
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d",
                "%Y/%m/%d %H:%M:%S",
                "%Y/%m/%d %H:%M",
                "%Y/%m/%d",
            ]
            for candidate in candidates:
                try:
                    return datetime.fromisoformat(candidate)
                except Exception:
                    for fmt in formats:
                        try:
                            return datetime.strptime(candidate, fmt)
                        except Exception:
                            continue
            return None
        return None

    @classmethod
    def _format_ts_shichen(cls, value) -> str:
        dt = cls._coerce_datetime(value)
        if not dt:
            return ""
        hour = dt.hour
        shichen_map = {
            23: "子",
            0: "子",
            1: "丑",
            2: "丑",
            3: "寅",
            4: "寅",
            5: "卯",
            6: "卯",
            7: "辰",
            8: "辰",
            9: "巳",
            10: "巳",
            11: "午",
            12: "午",
            13: "未",
            14: "未",
            15: "申",
            16: "申",
            17: "酉",
            18: "酉",
            19: "戌",
            20: "戌",
            21: "亥",
            22: "亥",
        }
        shichen = shichen_map.get(hour, "子")
        return f"{dt.year}年{dt.month}月{dt.day}日{shichen}时"

    def save_compare_group_images(
        self,
        rows: List[Dict[str, Any]],
        value_field: str,
        metric_label: str,
        earlier_ts,
        later_ts,
        output_dir: str,
        header_path: str,
    ) -> List[Dict[str, Any]]:
        from uuid import uuid4
        from PIL import Image, ImageDraw

        os.makedirs(output_dir, exist_ok=True)
        try:
            header_img = Image.open(header_path).convert('RGB')
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"缺少头图文件：{header_path}") from exc

        target_width = 600
        resample_attr = getattr(Image, "Resampling", None)
        resample_filter = resample_attr.LANCZOS if resample_attr else getattr(Image, "LANCZOS", Image.BICUBIC)
        if header_img.width != target_width:
            scale = target_width / header_img.width
            new_height = max(1, int(header_img.height * scale))
            header_img = header_img.resize((target_width, new_height), resample_filter)

        width = target_width
        header_height = header_img.height
        top_margin = 0
        content_bg = (255, 248, 220)
        header_row_bg = (255, 236, 196)
        alternate_row_bg = (242, 244, 248)
        text_primary = (48, 55, 65)
        text_muted = (90, 99, 117)
        positive_color = (200, 21, 35)
        negative_color = (24, 102, 54)
        highlight_high_bg = (255, 230, 180)
        highlight_zero_bg = (207, 224, 255)
        member_text_color = (70, 94, 122)

        try:
            high_threshold = int(os.environ.get("HIGH_DELTA_THRESHOLD", "5000"))
        except ValueError:
            high_threshold = 5000

        title_font = _load_font(22)
        table_header_font = _load_font(26)
        table_font = _load_font(24)
        idiom_title_font = _load_font(22)
        idiom_body_font = _load_font(20)

        def measure(font, text: str) -> tuple[int, int]:
            try:
                bbox = font.getbbox(text)
                return bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception:
                size = getattr(font, 'size', 24)
                return len(text) * size, size

        def wrap_text(font, text: str, max_width: int) -> list[str]:
            if not text:
                return []
            lines: list[str] = []
            current = ""
            for ch in text:
                candidate = current + ch
                width, _ = measure(font, candidate)
                if current and width > max_width:
                    lines.append(current)
                    current = ch
                else:
                    current = candidate
            if current:
                lines.append(current)
            return lines

        title_line_height = measure(title_font, '字')[1]
        header_line_height = measure(table_header_font, '字')[1]
        row_line_height = measure(table_font, '字')[1]

        padding_x = 36
        padding_bottom = 72
        title_gap = 44
        table_gap = 24
        row_height = row_line_height + 18
        header_height_content = header_line_height + 18

        earlier_label = self._format_ts_shichen(earlier_ts) or self._format_ts_shichen(earlier_ts or '')
        later_label = self._format_ts_shichen(later_ts) or self._format_ts_shichen(later_ts or '')

        groups: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            group_name = str(row.get('分组', '')).strip() or '未分组'
            groups.setdefault(group_name, []).append(row)

        image_results: List[Dict[str, Any]] = []

        if not groups:
            return image_results

        import re

        table_left = padding_x
        table_right = width - padding_x
        index_col_width = 60
        value_col_width = 190
        max_text_width = width - 2 * padding_x
        metric_text = metric_label or value_field
        is_battle_metric = "战功" in metric_text
        is_contrib_metric = "贡献" in metric_text

        idioms_list: list[dict[str, str]] = []
        idioms_path = os.path.join(os.path.dirname(header_path), "idioms100.json")
        try:
            with open(idioms_path, "r", encoding="utf-8") as idiom_file:
                idioms_raw = json.load(idiom_file)
                if isinstance(idioms_raw, dict) and "三国成语大全" in idioms_raw:
                    source = idioms_raw.get("三国成语大全", [])
                else:
                    source = idioms_raw if isinstance(idioms_raw, list) else []
                idioms_list = [entry for entry in source if isinstance(entry, dict)]
        except Exception:
            idioms_list = []

        def render_group_image(group_name: str, group_rows: List[Dict[str, Any]]) -> None:
            if not group_rows:
                return
            ordered_rows = sorted(group_rows, key=lambda r: int(r.get(value_field, 0)), reverse=True)
            rows_count = len(ordered_rows)

            idiom_entry = random.choice(idioms_list) if idioms_list else None
            idiom_lines: list[tuple[object, str]] = []
            if idiom_entry:
                idiom_phrase = str(idiom_entry.get('成语', '')).strip()
                idiom_story = str(idiom_entry.get('典故', '')).strip()
                if idiom_phrase:
                    idiom_lines.append((idiom_title_font, f"{idiom_phrase}"))
                if idiom_story:
                    story_lines = wrap_text(idiom_body_font, f"典故：{idiom_story}", max_text_width)
                    idiom_lines.extend((idiom_body_font, line) for line in story_lines)

            idiom_top_padding = 24 if idiom_lines else 0
            idiom_bottom_padding = 18 if idiom_lines else 0
            idiom_line_gap = 6
            idiom_block_height = idiom_top_padding + idiom_bottom_padding
            for idx, (font_obj, _) in enumerate(idiom_lines):
                line_height = measure(font_obj, '字')[1]
                idiom_block_height += line_height
                if idx < len(idiom_lines) - 1:
                    idiom_block_height += idiom_line_gap

            content_height = (
                title_gap
                + title_line_height
                + table_gap
                + header_height_content
                + rows_count * row_height
                + idiom_block_height
                + padding_bottom
            )

            image_height = top_margin + header_height + content_height
            image = Image.new('RGB', (width, image_height), content_bg)
            image.paste(header_img, (0, top_margin))
            draw = ImageDraw.Draw(image)

            title_y = top_margin + header_height + title_gap
            group_label = group_name
            if group_label == '未分组':
                group_label = '未分组成员'
            title_text = f"{group_label} | {earlier_label} → {later_label}"
            draw.text((padding_x, title_y), title_text, font=title_font, fill=text_primary)

            table_top = title_y + title_line_height + table_gap

            draw.rectangle([table_left, table_top, table_right, table_top + header_height_content], fill=header_row_bg)
            header_center_y = table_top + header_height_content / 2
            draw.text((table_left + 16, header_center_y), '#', font=table_header_font, fill=text_muted, anchor="lm")
            member_col_left = table_left + index_col_width
            member_col_right = table_right - value_col_width
            member_center_x = (member_col_left + member_col_right) / 2
            draw.text((member_center_x, header_center_y), '成员', font=table_header_font, fill=text_muted, anchor="mm")
            value_center_x = table_right - value_col_width / 2
            draw.text((value_center_x, header_center_y), metric_label, font=table_header_font, fill=text_muted, anchor="mm")

            # horizontal line under header
            draw.line([(table_left, table_top + header_height_content), (table_right, table_top + header_height_content)], fill=text_muted, width=2)

            for idx, row in enumerate(ordered_rows, start=1):
                row_top = table_top + header_height_content + (idx - 1) * row_height
                row_bottom = row_top + row_height
                row_fill = None

                member = str(row.get('成员', '')).strip() or '-'
                try:
                    diff_value = int(row.get(value_field, 0))
                except Exception:
                    diff_value = 0
                diff_text = f"{diff_value:+d}"

                index_text = str(idx)
                index_height = measure(table_font, index_text)[1]
                member_height = measure(table_font, member)[1]
                diff_width, diff_height = measure(table_font, diff_text)

                if diff_value == 0 and (is_battle_metric or is_contrib_metric):
                    row_fill = highlight_zero_bg
                elif is_battle_metric and diff_value > high_threshold:
                    row_fill = highlight_high_bg
                elif idx % 2 == 0:
                    row_fill = alternate_row_bg

                if row_fill:
                    draw.rectangle([table_left, row_top, table_right, row_bottom], fill=row_fill)

                base_y = row_top + (row_height - member_height) / 2
                draw.text((table_left + 18, row_top + row_height / 2), index_text, font=table_font, fill=text_primary, anchor="lm")
                draw.text((member_center_x, row_top + row_height / 2), member, font=table_font, fill=member_text_color, anchor="mm")

                diff_color = text_primary
                if diff_value > 0:
                    diff_color = positive_color
                elif diff_value < 0:
                    diff_color = negative_color

                diff_x = value_center_x
                diff_y = row_top + row_height / 2
                draw.text((diff_x, diff_y), diff_text, font=table_font, fill=diff_color, anchor="mm")

                draw.line([(table_left, row_bottom), (table_right, row_bottom)], fill=(230, 230, 230), width=1)

            if idiom_lines:
                idiom_y = table_top + header_height_content + rows_count * row_height + idiom_top_padding
                for idx, (font_obj, text_line) in enumerate(idiom_lines):
                    draw.text((padding_x, idiom_y), text_line, font=font_obj, fill=member_text_color)
                    line_height = measure(font_obj, '字')[1]
                    idiom_y += line_height
                    if idx < len(idiom_lines) - 1:
                        idiom_y += idiom_line_gap

            safe_group = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]+", "_", group_name) or "group"
            file_name = f"compare_{metric_label}_{safe_group}_{uuid4().hex[:8]}.jpg"
            file_path = os.path.join(output_dir, file_name)
            image.save(
                file_path,
                format='JPEG',
                quality=78,
                subsampling=2,
                optimize=True,
                progressive=True,
            )
            image_results.append({
                'group': group_name,
                'path': file_path,
                'count': rows_count,
            })

        for group_name, group_rows in sorted(groups.items(), key=lambda item: item[0]):
            if group_name == '全盟':
                continue
            render_group_image(group_name, group_rows)

        # Append an overall view covering all members at the end.
        render_group_image('全盟', rows)

        return image_results

    @classmethod
    def _build_member_df_from_records(
        cls,
        records: List[Dict[str, Any]],
        metric_key: str,
        metric_column: str,
    ) -> pd.DataFrame:
        if not records:
            return pd.DataFrame(columns=['成员', metric_column, '分组'])

        prepared: List[Dict[str, Any]] = []
        for record in records:
            member = str(record.get('member_name', '')).strip()
            if not member:
                continue
            group_name = str(record.get('group_name', '')).strip() or '未分组'
            value_raw = record.get(metric_key, 0)
            prepared.append({'成员': member, metric_column: value_raw, '分组': group_name})

        df = pd.DataFrame(prepared, columns=['成员', metric_column, '分组'])
        if df.empty:
            return df
        df[metric_column] = pd.to_numeric(df[metric_column], errors='coerce').fillna(0).astype(int)
        df['分组'] = df['分组'].astype(str).str.strip().replace({'': '未分组'})
        df = df.sort_values(metric_column).drop_duplicates(subset=['成员'], keep='last').reset_index(drop=True)
        return df

    def _analyze_member_metric_change(
        self,
        file1_path: str,
        file2_path: str,
        metric_column: str,
        metric_display_name: str,
    ) -> Dict[str, Any]:
        try:
            t1 = self._parse_cn_timestamp_from_filename(file1_path)
            t2 = self._parse_cn_timestamp_from_filename(file2_path)
            if t1 <= t2:
                earlier_path, later_path = file1_path, file2_path
                earlier_ts, later_ts = t1, t2
            else:
                earlier_path, later_path = file2_path, file1_path
                earlier_ts, later_ts = t2, t1

            df_early = self._read_member_stats_csv(earlier_path, metric_column)
            df_late = self._read_member_stats_csv(later_path, metric_column)

            payload = self._calculate_member_metric_diff(df_early, df_late, metric_column, metric_display_name)
            payload.update(
                {
                    'earlier': earlier_path,
                    'later': later_path,
                    'earlier_ts': earlier_ts.isoformat(sep=' '),
                    'later_ts': later_ts.isoformat(sep=' '),
                    'range': f"{earlier_ts} ~ {later_ts}",
                }
            )
            return payload
        except Exception as exc:  # noqa: BLE001
            return {'success': False, 'error': str(exc)}

    def analyze_battle_merit_change(self, file1_path: str, file2_path: str) -> Dict[str, Any]:
        """按战功总量计算差值。"""
        return self._analyze_member_metric_change(file1_path, file2_path, '战功总量', '战功总量')

    def analyze_power_value_change(self, file1_path: str, file2_path: str) -> Dict[str, Any]:
        """按势力值计算差值。"""
        return self._analyze_member_metric_change(file1_path, file2_path, '势力值', '势力值')

    def analyze_contribution_change(self, file1_path: str, file2_path: str) -> Dict[str, Any]:
        """按贡献总量计算差值。"""
        return self._analyze_member_metric_change(file1_path, file2_path, '贡献总量', '贡献总量')

    def analyze_member_metric_change_from_records(
        self,
        earlier_records: List[Dict[str, Any]],
        later_records: List[Dict[str, Any]],
        metric_key: str,
        metric_column: str,
        metric_display_name: str,
        earlier_ts,
        later_ts,
    ) -> Dict[str, Any]:
        try:
            df_early = self._build_member_df_from_records(earlier_records, metric_key, metric_column)
            df_late = self._build_member_df_from_records(later_records, metric_key, metric_column)

            payload = self._calculate_member_metric_diff(df_early, df_late, metric_column, metric_display_name)
            payload.update(
                {
                    'earlier_ts': earlier_ts.isoformat(sep=' ') if hasattr(earlier_ts, 'isoformat') else str(earlier_ts),
                    'later_ts': later_ts.isoformat(sep=' ') if hasattr(later_ts, 'isoformat') else str(later_ts),
                    'range': f"{earlier_ts} ~ {later_ts}",
                }
            )
            return payload
        except Exception as exc:  # noqa: BLE001
            return {'success': False, 'error': str(exc)}

    @staticmethod
    def save_grouped_tables_as_images(
        result_rows: List[Dict[str, Any]],
        out_dir: str,
        title_prefix: str,
        display_title: str,
        value_field: str,
        value_label: str,
        high_delta_threshold: int = 5000,
    ) -> List[str]:
        import random
        import math
        from PIL import Image, ImageDraw, ImageFont

        os.makedirs(out_dir, exist_ok=True)
        import pandas as pd
        df = pd.DataFrame(result_rows)
        if df.empty or value_field not in df.columns:
            return []

        header_path = os.path.join(os.path.dirname(__file__), 'resources', 'header2.jpg')
        header_img = Image.open(header_path).convert('RGBA')
        header_w, header_h = header_img.size
        tile_height = 100
        header_tile = header_img.crop((0, 0, header_w, tile_height))

        def load_font(size: int) -> "ImageFont.ImageFont":
            for font_name in ("msyh.ttc", "msyh.ttf", "simhei.ttf"):
                try:
                    return ImageFont.truetype(font_name, size)
                except Exception:
                    continue
            return ImageFont.load_default()

        def measure_height(font: "ImageFont.ImageFont", text: str) -> float:
            try:
                bbox = font.getbbox(text)
                return float(bbox[3] - bbox[1])
            except Exception:
                return float(font.size if hasattr(font, 'size') else 0)

        def ensure_canvas(min_height: int) -> "Image.Image":
            if header_img.height >= min_height:
                return header_img.copy()
            blocks = math.ceil((min_height - header_img.height) / tile_height)
            canvas = Image.new('RGBA', (header_w, header_img.height + blocks * tile_height))
            canvas.paste(header_img, (0, 0))
            for i in range(blocks):
                canvas.paste(header_tile, (0, header_img.height + i * tile_height))
            return canvas

        def wrap_text(text: str, font: "ImageFont.ImageFont", max_width: int) -> List[str]:
            lines: List[str] = []
            current = ''
            for ch in text:
                candidate = current + ch
                try:
                    bbox = font.getbbox(candidate)
                    width = bbox[2] - bbox[0]
                except Exception:
                    width = len(candidate) * (font.size if hasattr(font, 'size') else 10)
                if current and width > max_width:
                    lines.append(current)
                    current = ch
                else:
                    current = candidate
            if current:
                lines.append(current)
            return lines

        groups_to_render: List[Tuple[str, pd.DataFrame]] = []
        all_view = df[['成员', value_field]].sort_values(value_field, ascending=False).reset_index(drop=True)
        groups_to_render.append(('全盟', all_view))
        for group, subdf in df.groupby('分组', sort=True):
            if str(group) == '未分组':
                continue
            group_view = subdf[['成员', value_field]].sort_values(value_field, ascending=False).reset_index(drop=True)
            groups_to_render.append((str(group), group_view))

        idioms_path = os.path.join(os.path.dirname(__file__), 'resources', 'idioms100.json')
        try:
            with open(idioms_path, 'r', encoding='utf-8') as f:
                idioms_json = json.load(f)
                if isinstance(idioms_json, dict) and '三国成语大全' in idioms_json:
                    idioms_list = idioms_json['三国成语大全']
                else:
                    idioms_list = idioms_json if isinstance(idioms_json, list) else []
        except Exception:
            idioms_list = []

        title_font = load_font(32)
        group_font = load_font(60)
        table_font = load_font(28)
        idiom_body_font = load_font(40)
        idiom_title_font = load_font(44)

        table_line_height = max(int(measure_height(table_font, '字')), 28)
        row_height_base = table_line_height + 18
        idiom_body_height = max(int(measure_height(idiom_body_font, '字')), 40)

        HEADER_BOTTOM_GAP = 50
        TITLE_GAP = 80
        GROUP_TITLE_GAP = 50
        TABLE_BOTTOM_PADDING = 80
        IDIOM_TOP_PADDING = 20
        IDIOM_BOTTOM_PADDING = 40
        IDIOM_LINE_SPACING = 12
        TABLE_WIDTH_RATIO = 0.72

        saved_paths: List[str] = []
        group_stats: List[Dict[str, Any]] = []

        for group, view in groups_to_render:
            group_label = '全盟' if group == '全盟' else f"{group} 组"
            table_rows = len(view)
            table_height = (table_rows + 1) * row_height_base + TABLE_BOTTOM_PADDING

            idiom_title_text = ''
            idiom_story_lines: List[str] = []
            if idioms_list:
                idiom_entry = random.choice(idioms_list)
                if isinstance(idiom_entry, dict) and '成语' in idiom_entry and '典故' in idiom_entry:
                    idiom_title_text = f"学习文化 - 【{idiom_entry['成语']}】"
                    idiom_story_lines = wrap_text(str(idiom_entry['典故']), idiom_body_font, header_w - 200)

            title1_y = header_h + HEADER_BOTTOM_GAP
            title1_h = measure_height(title_font, display_title)
            title2_y = title1_y + title1_h + TITLE_GAP
            title2_text = f"{group_label} ({len(view)})"
            title2_h = measure_height(group_font, title2_text)
            table_start_y = int(title2_y + title2_h + GROUP_TITLE_GAP)

            idiom_section_height = 0
            if idiom_title_text:
                title_height = measure_height(idiom_title_font, idiom_title_text)
                if idiom_story_lines:
                    story_height = len(idiom_story_lines) * idiom_body_height + (len(idiom_story_lines) - 1) * IDIOM_LINE_SPACING
                else:
                    story_height = 0
                idiom_section_height = IDIOM_TOP_PADDING + title_height + (IDIOM_LINE_SPACING if story_height else 0) + story_height + IDIOM_BOTTOM_PADDING

            required_height = table_start_y + table_height + idiom_section_height
            canvas = ensure_canvas(required_height)
            draw = ImageDraw.Draw(canvas)
            img_w = canvas.width

            draw.text((img_w // 2, title1_y), display_title, font=title_font, fill=(0, 0, 0, 255), anchor="mm")
            draw.text((img_w // 2, title2_y), title2_text, font=group_font, fill=(0, 0, 0, 255), anchor="mm")

            table_total_width = img_w * TABLE_WIDTH_RATIO
            cell_width = table_total_width / 2
            table_left = (img_w - table_total_width) / 2
            header_y = table_start_y
            header_center_y = header_y + row_height_base / 2
            col_centers = [table_left + cell_width / 2, table_left + 1.5 * cell_width]
            col_titles = ["成员", f"{value_label}差值"]

            for idx, title in enumerate(col_titles):
                draw.text((col_centers[idx], header_center_y), title, font=table_font, fill=(40, 40, 40, 255), anchor="mm")
                cell_left = table_left + idx * cell_width
                x0 = int(round(cell_left))
                x1 = int(round(cell_left + cell_width))
                y0 = int(round(header_y))
                y1 = int(round(header_y + row_height_base))
                draw.rectangle([x0, y0, x1, y1], outline=(80, 80, 80, 255), width=2)

            for row_idx, (member, delta) in enumerate(view[['成员', value_field]].itertuples(index=False, name=None)):
                row_top = table_start_y + (row_idx + 1) * row_height_base
                y_top = int(round(row_top))
                y_bottom = int(round(row_top + row_height_base))
                y_center = row_top + row_height_base / 2
                highlight_orange = delta == 0
                highlight_green = delta > high_delta_threshold
                for col_idx, value in enumerate((member, delta)):
                    cell_left = table_left + col_idx * cell_width
                    x0 = int(round(cell_left))
                    x1 = int(round(cell_left + cell_width))
                    if highlight_orange:
                        draw.rectangle([x0, y_top, x1, y_bottom], fill=(255, 140, 0, 180))
                    elif highlight_green:
                        draw.rectangle([x0, y_top, x1, y_bottom], fill=(144, 238, 144, 180))
                    draw.rectangle([x0, y_top, x1, y_bottom], outline=(120, 120, 120, 255), width=1)
                    draw.text((col_centers[col_idx], y_center), str(value), font=table_font, fill=(0, 0, 0, 255), anchor="mm")

            if idiom_title_text:
                idiom_top = table_start_y + table_height + IDIOM_TOP_PADDING
                title_height = measure_height(idiom_title_font, idiom_title_text)
                draw.text((img_w // 2, idiom_top + title_height / 2), idiom_title_text, font=idiom_title_font, fill=(60, 60, 60, 255), anchor="mm")
                story_start_y = idiom_top + title_height + (IDIOM_LINE_SPACING if idiom_story_lines else 0)
                for idx, line in enumerate(idiom_story_lines):
                    y_pos = story_start_y + idx * (idiom_body_height + IDIOM_LINE_SPACING)
                    draw.text((100, y_pos), line, font=idiom_body_font, fill=(60, 60, 60, 255), anchor="la")

            safe_group = group.replace('/', '_').replace('\\', '_')
            out_path = os.path.join(out_dir, f"{title_prefix}_分组_{safe_group}.png")
            canvas.save(out_path)
            saved_paths.append(out_path)

            if group != '全盟' and not view.empty:
                avg_delta = float(view[value_field].mean())
                zero_count = int((view[value_field] == 0).sum())
                group_stats.append({
                    '分组名称': group,
                    '有效成员人数': len(view),
                    '平均差值': round(avg_delta, 2),
                    '零变化人数': zero_count
                })

        if group_stats:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
            plt.rcParams['axes.unicode_minus'] = False

            stats_df = pd.DataFrame(group_stats)
            stats_df = stats_df.sort_values('平均差值', ascending=False).reset_index(drop=True)

            rows = len(stats_df) + 1
            cols = len(stats_df.columns)
            cell_h = 0.42
            cell_w = 1.6
            top_pad_frac = 0.15
            fig_h = max(3.0, rows * cell_h)
            fig_w = max(8.0, cols * cell_w)
            fig, ax = plt.subplots(figsize=(fig_w, fig_h))
            ax.axis('off')
            table = ax.table(cellText=[[str(x) for x in row] for row in stats_df.values],
                             colLabels=list(stats_df.columns),
                             cellLoc='center',
                             loc='center',
                             bbox=[0.0, 0.0, 1.0, 1.0 - top_pad_frac])
            table.auto_set_font_size(False)
            table.set_fontsize(10)
            table.scale(1, 1.15)
            ax.text(0.5, 1.0 - top_pad_frac/2,
                    f"{display_title} 分组汇总",
                    ha='center', va='center', transform=ax.transAxes, fontsize=13, fontweight='bold')
            agg_path = os.path.join(out_dir, f"{title_prefix}_分组统计汇总.png")
            plt.savefig(agg_path, bbox_inches='tight', dpi=200)
            plt.close(fig)
            saved_paths.append(agg_path)

        return saved_paths


def _auto_find_two_csvs_in_test_data(root: str) -> Tuple[str, str]:
    td = os.path.join(root, 'test_data')
    if not os.path.isdir(td):
        raise FileNotFoundError(f"未找到目录: {td}")
    files = [os.path.join(td, f) for f in os.listdir(td) if f.lower().endswith('.csv')]
    if len(files) < 2:
        raise FileNotFoundError("test_data 中少于两个CSV文件")
    # Prefer files with timestamp pattern; sort by parsed ts
    def ts_or_min(path: str) -> datetime:
        try:
            return FileAnalyzer._parse_cn_timestamp_from_filename(path)
        except Exception:
            return datetime.min
    files = sorted(files, key=ts_or_min)
    return files[-2], files[-1]


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='同盟成员指标差值分析')
    parser.add_argument('--file1', type=str, help='CSV文件1路径（含中文时间戳）')
    parser.add_argument('--file2', type=str, help='CSV文件2路径（含中文时间戳）')
    parser.add_argument('--metric', choices=['battle', 'power'], default='battle', help='battle=战功总量, power=势力值')
    args = parser.parse_args()

    root = os.path.dirname(os.path.abspath(__file__))
    f1, f2 = (args.file1, args.file2) if (args.file1 and args.file2) else _auto_find_two_csvs_in_test_data(root)

    analyzer = FileAnalyzer()
    if args.metric == 'power':
        out = analyzer.analyze_power_value_change(f1, f2)
    else:
        out = analyzer.analyze_battle_merit_change(f1, f2)
    if not out.get('success'):
        print(f"分析失败: {out.get('error')}")
        raise SystemExit(1)

    print(f"时间范围: {out['earlier_ts']} -> {out['later_ts']}")
    print(f"文件顺序: 早={os.path.basename(out['earlier'])} 晚={os.path.basename(out['later'])}")
    value_field = out.get('value_field', '差值')
    print("结果（仅保留两边同时存在的成员）")
    print(f"结果（成员, {value_field}, 分组），按分组与差值排序：")
    for row in out['rows']:
        print(f"{row['成员']}, {row[value_field]}, {row['分组']}")

    # Save grouped tables as images (truncate timestamps to minute resolution for title)
    def _trim_seconds(ts_str: str) -> str:
        parts = ts_str.strip().split(' ')
        if len(parts) == 2 and parts[1].count(':') == 2:
            date_part, time_part = parts
            hh_mm = ':'.join(time_part.split(':')[:2])
            return f"{date_part} {hh_mm}"
        return ts_str
    earlier_no_sec = _trim_seconds(out['earlier_ts'])
    later_no_sec = _trim_seconds(out['later_ts'])
    title_prefix = f"战功统计_{earlier_no_sec.replace(':','').replace(' ','_')}_至_{later_no_sec.replace(':','').replace(' ','_')}"
    # Display title with slash-style date (YYYY/MM/DD HH:MM) and without seconds
    def _slash_fmt(ts: str) -> str:
        parts = ts.split(' ')
        if len(parts) == 2:
            d, hm = parts
            d_parts = d.split('-')
            if len(d_parts) == 3:
                d = '/'.join(d_parts)  # YYYY/MM/DD
            return f"{d} {hm}"
        return ts
    display_title = f"战功统计 { _slash_fmt(earlier_no_sec) } → { _slash_fmt(later_no_sec) }"
    out_dir = os.path.join(root, 'output')
    # Allow override of high-delta threshold via env var (default 5000)
    high_th = int(os.environ.get('HIGH_DELTA_THRESHOLD', '5000'))
    pngs = FileAnalyzer.save_grouped_tables_as_images(
        out['rows'],
        out_dir,
        title_prefix,
        display_title,
        value_field,
        out.get('value_label', '指标'),
        high_delta_threshold=high_th,
    )
    print("表格图片已生成：")
    for p in pngs:
        print(p)

    # Optionally send via WeChat Work if credentials and target set
    try:
        # Try import dotenv lazily; ignore if not available
        try:
            from dotenv import load_dotenv  # type: ignore
            load_dotenv()
        except Exception:
            pass

        corp_id = os.environ.get('WECHAT_CORP_ID', '')
        corp_secret = os.environ.get('WECHAT_CORP_SECRET', '')
        agent_id = os.environ.get('WECHAT_AGENT_ID', '')
        to_user = os.environ.get('WECHAT_TO_USER', '')

        if to_user and corp_id and corp_secret and agent_id:
            try:
                from wechat_api import WeChatWorkAPI
                api = WeChatWorkAPI(corp_id, corp_secret, agent_id)
                print(f"开始推送到企业微信，目标: {to_user}")
                for path in pngs:
                    up = api.upload_image(path)
                    if up.get('errcode') == 0 and up.get('media_id'):
                        res = api.send_image_message(to_user, up['media_id'])
                        print(f"发送图片: {os.path.basename(path)} -> {res}")
                    else:
                        print(f"上传失败: {path} -> {up}")
            except Exception as e_send:
                print(f"企业微信发送失败: {e_send}")
        # Always generate a manifest regardless of sending outcome
        manifest = {
            'title': title_prefix,
            'images': pngs,
            'wecom_push': {
                'corp_id_present': bool(corp_id),
                'agent_id_present': bool(agent_id),
                'to_user_present': bool(to_user)
            },
            'usage': '设置环境变量 WECHAT_CORP_ID, WECHAT_CORP_SECRET, WECHAT_AGENT_ID, WECHAT_TO_USER 可自动推送；否则可手动使用 wechat_api 发送。'
        }
        with open(os.path.join(out_dir, f"{title_prefix}_wecom_manifest.json"), 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print("已生成WeCom消息清单JSON（包含发送配置提示）。")
    except Exception as e:
        print(f"企业微信推送步骤跳过/失败: {e}")

