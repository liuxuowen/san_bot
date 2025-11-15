"""
File analysis utilities for comparing files and generating reports
"""
import os
import re
import json
import difflib
from datetime import datetime
from typing import Tuple, Dict, Any, List

import pandas as pd


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
        m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2})时(\d{1,2})分(\d{1,2})秒", base)
        if not m:
            raise ValueError(f"无法从文件名解析时间戳: {filename}")
        y, mo, d, h, mi, s = map(int, m.groups())
        return datetime(y, mo, d, h, mi, s)

    @staticmethod
    def _read_member_stats_csv(path: str) -> pd.DataFrame:
        """Read CSV and return DataFrame with columns: 成员, 战功总量, 分组"""
        df = pd.read_csv(path, encoding='utf-8', skipinitialspace=True)
        df.columns = df.columns.str.strip()
        # Keep only needed columns, handle if some are missing
        needed = ['成员', '战功总量', '分组']
        for col in needed:
            if col not in df.columns:
                raise ValueError(f"CSV缺少必要列: {col} ({path})")
        df = df[needed].copy()
        # Normalize types
        df['成员'] = df['成员'].astype(str).str.strip()
        df['分组'] = df['分组'].astype(str).str.strip().replace({'': '未分组'})
        df['战功总量'] = pd.to_numeric(df['战功总量'], errors='coerce').fillna(0).astype(int)
        # Drop duplicate members by keeping the max 战功总量 (defensive)
        df = df.sort_values('战功总量').drop_duplicates(subset=['成员'], keep='last').reset_index(drop=True)
        return df

    def analyze_battle_merit_change(self, file1_path: str, file2_path: str) -> Dict[str, Any]:
        """
        比对两个同盟统计CSV，按文件名中的时间戳识别先后，
        统计在此时间段内每位成员的 战功总量 差值，并按 分组、差值 排序输出。

        Returns dict with keys: success, earlier, later, range, rows (list of dicts)
        """
        try:
            t1 = self._parse_cn_timestamp_from_filename(file1_path)
            t2 = self._parse_cn_timestamp_from_filename(file2_path)
            # Determine earlier and later
            if t1 <= t2:
                earlier_path, later_path = file1_path, file2_path
                earlier_ts, later_ts = t1, t2
            else:
                earlier_path, later_path = file2_path, file1_path
                earlier_ts, later_ts = t2, t1

            df_early = self._read_member_stats_csv(earlier_path)
            df_late = self._read_member_stats_csv(later_path)

            early = df_early.rename(columns={'战功总量': '战功总量_早', '分组': '分组_早'})
            late = df_late.rename(columns={'战功总量': '战功总量_晚', '分组': '分组_晚'})

            # Inner join: only keep members that exist in both files
            merged = pd.merge(early, late, on='成员', how='inner')
            # Determine group preference: later > earlier > 未分组
            merged['分组'] = merged['分组_晚'].fillna(merged['分组_早']).fillna('未分组')
            merged['战功总量_早'] = pd.to_numeric(merged['战功总量_早'], errors='coerce').fillna(0)
            merged['战功总量_晚'] = pd.to_numeric(merged['战功总量_晚'], errors='coerce').fillna(0)
            merged['战功总量差值'] = (merged['战功总量_晚'] - merged['战功总量_早']).astype(int)

            # Build output
            result = merged[['成员', '分组', '战功总量差值']].copy()
            # Sort by group (asc) then diff (desc)
            result = result.sort_values(by=['分组', '战功总量差值'], ascending=[True, False]).reset_index(drop=True)

            # Pack rows for return
            rows: List[Dict[str, Any]] = result.to_dict(orient='records')
            return {
                'success': True,
                'earlier': earlier_path,
                'later': later_path,
                'earlier_ts': earlier_ts.isoformat(sep=' '),
                'later_ts': later_ts.isoformat(sep=' '),
                'range': f"{earlier_ts} ~ {later_ts}",
                'rows': rows
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def save_grouped_tables_as_images(
        result_rows: List[Dict[str, Any]],
        out_dir: str,
        title_prefix: str,
        display_title: str,
        high_delta_threshold: int = 5000,
    ) -> List[str]:
        """Render grouped result rows as table images (one PNG per 分组),
        highlighting rows with 战功总量差值 > high_delta_threshold.
        display_title: human-readable title (dates may contain '/') used in figure, while
        title_prefix is used for filename construction (kept filesystem-safe).
        """
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.table import Table

        # Font config for Chinese
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
        plt.rcParams['axes.unicode_minus'] = False

        os.makedirs(out_dir, exist_ok=True)
        import pandas as pd
        df = pd.DataFrame(result_rows)
        saved_paths: List[str] = []
        # Prepare aggregation stats (excluding '未分组')
        group_stats: List[Dict[str, Any]] = []

        for group, subdf in df.groupby('分组', sort=True):
            # Skip '未分组' for statistics and per-group image generation
            if str(group) == '未分组':
                continue
            # Ensure per-group sorting by 差值降序
            view = subdf[['成员', '战功总量差值']].sort_values('战功总量差值', ascending=False).reset_index(drop=True)

            # Figure size heuristic based on rows; allocate top padding for title
            rows = len(view) + 1  # + header
            cols = 2
            cell_h = 0.42
            cell_w = 2.8
            top_pad_frac = 0.18  # more space for two-line title
            fig_h = max(3.5, rows * cell_h)
            fig_w = max(6.0, cols * cell_w)
            fig, ax = plt.subplots(figsize=(fig_w, fig_h))
            ax.axis('off')

            # Place table within bbox leaving space on top for the title
            the_table = ax.table(cellText=[[str(x) for x in row] for row in view.values],
                                  colLabels=list(view.columns),
                                  cellLoc='center',
                                  loc='center',
                                  bbox=[0.0, 0.0, 1.0, 1.0 - top_pad_frac])
            the_table.auto_set_font_size(False)
            the_table.set_fontsize(10)
            the_table.scale(1, 1.15)

            # Title above table region - multi-line
            title_text = f"{display_title}\n{group} 组 ({len(view)})"
            ax.text(0.5, 1.0 - top_pad_frac/2, title_text,
                    ha='center', va='center', transform=ax.transAxes, fontsize=12, fontweight='bold', linespacing=1.3)

            # Highlight by threshold: 战功总量差值 > high_delta_threshold
            try:
                high_rows = view.index[view['战功总量差值'] > int(high_delta_threshold)].tolist()
                for i in high_rows:
                    r = i + 1  # offset for header row
                    for c in range(cols):
                        cell = the_table[(r, c)]
                        # Only change background color; keep borders same as non-highlighted cells
                        cell.set_facecolor('#FFF4CC')
            except Exception:
                pass

            # Additional highlight for zero-delta members using another color
            try:
                zero_rows = view.index[view['战功总量差值'] == 0].tolist()
                for i in zero_rows:
                    r = i + 1  # offset for header row
                    for c in range(cols):
                        cell = the_table[(r, c)]
                        cell.set_facecolor('#E6F7FF')  # light blue for zero change
            except Exception:
                pass

            safe_group = str(group).replace('/', '_').replace('\\', '_')
            out_path = os.path.join(out_dir, f"{title_prefix}_分组_{safe_group}.png")
            plt.savefig(out_path, bbox_inches='tight', dpi=200)
            plt.close(fig)
            saved_paths.append(out_path)

            # Collect aggregation metrics
            total_count = len(view)
            avg_delta = float(view['战功总量差值'].mean()) if total_count else 0.0
            zero_count = int((view['战功总量差值'] == 0).sum())
            group_stats.append({
                '分组名称': group,
                '有效成员人数': total_count,
                '平均战功差值': round(avg_delta, 2),
                '狗混子人数': zero_count
            })

        # Create aggregated stats image if any stats collected
        if group_stats:
            stats_df = pd.DataFrame(group_stats)
            # Sort by 平均战功差值 desc
            stats_df = stats_df.sort_values('平均战功差值', ascending=False).reset_index(drop=True)

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
    parser = argparse.ArgumentParser(description='同盟成员战功总量差值分析')
    parser.add_argument('--file1', type=str, help='CSV文件1路径（含中文时间戳）')
    parser.add_argument('--file2', type=str, help='CSV文件2路径（含中文时间戳）')
    args = parser.parse_args()

    root = os.path.dirname(os.path.abspath(__file__))
    f1, f2 = (args.file1, args.file2) if (args.file1 and args.file2) else _auto_find_two_csvs_in_test_data(root)

    analyzer = FileAnalyzer()
    out = analyzer.analyze_battle_merit_change(f1, f2)
    if not out.get('success'):
        print(f"分析失败: {out.get('error')}")
        raise SystemExit(1)

    print(f"时间范围: {out['earlier_ts']} -> {out['later_ts']}")
    print(f"文件顺序: 早={os.path.basename(out['earlier'])} 晚={os.path.basename(out['later'])}")
    print("结果（仅保留两边同时存在的成员）")
    print("结果（成员, 战功总量差值, 分组），按分组与差值排序：")
    for row in out['rows']:
        print(f"{row['成员']}, {row['战功总量差值']}, {row['分组']}")

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
    pngs = FileAnalyzer.save_grouped_tables_as_images(out['rows'], out_dir, title_prefix, display_title, high_delta_threshold=high_th)
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

