"""
File analysis utilities for comparing files and generating reports
"""
import os
import json
import difflib
from typing import Tuple, Dict, Any


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
