#!/usr/bin/env python
"""
Test script to demonstrate the file analysis functionality
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from file_analyzer import FileAnalyzer

def create_test_files():
    """Create sample test files"""
    test_dir = '/tmp/san_bot_demo'
    os.makedirs(test_dir, exist_ok=True)
    
    # Create first test file
    file1_path = os.path.join(test_dir, 'config_old.txt')
    with open(file1_path, 'w', encoding='utf-8') as f:
        f.write("""# Application Configuration
server.port=8080
database.host=localhost
database.port=3306
database.name=myapp
cache.enabled=true
cache.size=1000
log.level=INFO
""")
    
    # Create second test file
    file2_path = os.path.join(test_dir, 'config_new.txt')
    with open(file2_path, 'w', encoding='utf-8') as f:
        f.write("""# Application Configuration
server.port=8080
database.host=localhost
database.port=5432
database.name=myapp_v2
cache.enabled=true
cache.size=2000
cache.ttl=3600
log.level=DEBUG
""")
    
    return file1_path, file2_path

def main():
    """Main test function"""
    print("=" * 60)
    print("San Bot - 文件分析演示")
    print("=" * 60)
    print()
    
    # Create test files
    print("📝 创建测试文件...")
    file1, file2 = create_test_files()
    print(f"   文件1: {file1}")
    print(f"   文件2: {file2}")
    print()
    
    # Initialize analyzer
    analyzer = FileAnalyzer()
    
    # Test 1: Basic comparison
    print("🔍 测试1: 基本文件对比")
    print("-" * 60)
    result = analyzer.analyze_files(file1, file2, "对比配置文件的差异")
    print(result['report'])
    print()
    
    # Test 2: With custom instruction
    print("🔍 测试2: 自定义指令 - 查找数据库配置变化")
    print("-" * 60)
    result = analyzer.analyze_files(file1, file2, "查找数据库配置的变化")
    print(result['report'])
    print()
    
    # Display detailed statistics
    print("📊 详细统计信息:")
    print("-" * 60)
    details = result['details']
    print(f"文件1总行数: {details['total_lines_file1']}")
    print(f"文件2总行数: {details['total_lines_file2']}")
    print(f"相似度: {details['similarity_percentage']}%")
    print(f"新增行数: {details['added_lines']}")
    print(f"删除行数: {details['removed_lines']}")
    print(f"相同行数: {details['common_lines']}")
    print()
    
    print("✅ 测试完成！")
    print("=" * 60)
    
    # Cleanup
    try:
        os.remove(file1)
        os.remove(file2)
        os.rmdir(os.path.dirname(file1))
    except:
        pass

if __name__ == '__main__':
    main()
