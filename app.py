"""
Main Flask application for WeChat Work bot
"""
import os
import json
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from config import config
from wechat_api import WeChatWorkAPI
from file_analyzer import FileAnalyzer


def create_app(config_name='default'):
    """Application factory"""
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Create upload folder if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Initialize WeChat Work API
    wechat_api = WeChatWorkAPI(
        corp_id=app.config['WECHAT_CORP_ID'],
        corp_secret=app.config['WECHAT_CORP_SECRET'],
        agent_id=app.config['WECHAT_AGENT_ID']
    )
    
    # Initialize file analyzer
    file_analyzer = FileAnalyzer()
    
    # Store file sessions (in production, use Redis or database)
    file_sessions = {}
    
    def allowed_file(filename):
        """Check if file extension is allowed"""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']
    
    @app.route('/')
    def index():
        """Health check endpoint"""
        return jsonify({
            'status': 'running',
            'service': 'WeChat Work File Analysis Bot',
            'version': '1.0.0'
        })
    
    @app.route('/wechat/callback', methods=['GET', 'POST'])
    def wechat_callback():
        """WeChat Work callback endpoint"""
        if request.method == 'GET':
            # URL verification
            msg_signature = request.args.get('msg_signature', '')
            timestamp = request.args.get('timestamp', '')
            nonce = request.args.get('nonce', '')
            echostr = request.args.get('echostr', '')
            
            # Verify and return echostr
            verified = wechat_api.verify_url(
                msg_signature, timestamp, nonce, echostr, 
                app.config['WECHAT_TOKEN']
            )
            return verified if verified else 'Verification failed', 200
        
        elif request.method == 'POST':
            # Handle incoming messages
            xml_data = request.data.decode('utf-8')
            message = wechat_api.parse_message(xml_data)
            
            msg_type = message.get('MsgType', '')
            from_user = message.get('FromUserName', '')
            
            # Handle different message types
            if msg_type == 'text':
                content = message.get('Content', '')
                # Store instruction for this user
                file_sessions[from_user] = {
                    'instruction': content,
                    'files': []
                }
                wechat_api.send_text_message(
                    from_user, 
                    f"已收到指令: {content}\n请上传两个需要对比的文件。"
                )
            
            elif msg_type == 'file':
                # Handle file upload
                media_id = message.get('MediaId', '')
                # WeCom may use FileName or Title depending on type
                file_name = message.get('FileName') or message.get('Title') or 'unknown_file'
                
                # Initialize session if not exists
                if from_user not in file_sessions:
                    file_sessions[from_user] = {
                        'instruction': '对比两个文件的差异',
                        'files': []
                    }
                
                # Download file
                file_path = os.path.join(
                    app.config['UPLOAD_FOLDER'], 
                    f"{from_user}_{len(file_sessions[from_user]['files'])}_{secure_filename(file_name)}"
                )
                
                if wechat_api.download_media(media_id, file_path):
                    file_sessions[from_user]['files'].append(file_path)
                    
                    files_count = len(file_sessions[from_user]['files'])
                    
                    if files_count < 2:
                        wechat_api.send_text_message(
                            from_user,
                            f"已收到文件 {files_count}/2，请继续上传第二个文件。"
                        )
                    elif files_count == 2:
                        # Run analysis in background thread to avoid callback timeout
                        import threading
                        file1, file2 = file_sessions[from_user]['files']

                        def _do_analysis_and_reply(u: str, f1: str, f2: str, session_key: str):
                            try:
                                if f1.lower().endswith('.csv') and f2.lower().endswith('.csv'):
                                    out = file_analyzer.analyze_battle_merit_change(f1, f2)
                                    if out.get('success'):
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
                                        def _slash_fmt(ts: str) -> str:
                                            parts = ts.split(' ')
                                            if len(parts) == 2:
                                                d, hm = parts
                                                d_parts = d.split('-')
                                                if len(d_parts) == 3:
                                                    d = '/'.join(d_parts)
                                                return f"{d} {hm}"
                                            return ts
                                        display_title = f"战功统计 { _slash_fmt(earlier_no_sec) } → { _slash_fmt(later_no_sec) }"
                                        out_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'output')
                                        os.makedirs(out_dir, exist_ok=True)
                                        high_th = int(os.environ.get('HIGH_DELTA_THRESHOLD', '5000'))
                                        pngs = FileAnalyzer.save_grouped_tables_as_images(out['rows'], out_dir, title_prefix, display_title, high_delta_threshold=high_th)
                                        if pngs:
                                            wechat_api.send_text_message(u, f"分析完成，共生成{len(pngs)}张分组图片，即将发送…")
                                            for p in pngs:
                                                up = wechat_api.upload_image(p)
                                                if up.get('errcode') == 0 and up.get('media_id'):
                                                    wechat_api.send_image_message(u, up['media_id'])
                                            return
                                # Fallback generic diff
                                instruction = file_sessions.get(session_key, {}).get('instruction', '对比两个文件的差异')
                                result = file_analyzer.analyze_files(f1, f2, instruction)
                                wechat_api.send_text_message(u, result.get('report', '分析完成。'))
                            except Exception as e:
                                wechat_api.send_text_message(u, f"分析失败: {e}")
                            finally:
                                # Clean up files and session
                                sess = file_sessions.pop(session_key, None)
                                if sess and 'files' in sess:
                                    for f in sess['files']:
                                        try:
                                            os.remove(f)
                                        except:
                                            pass

                        wechat_api.send_text_message(from_user, "已收到两份文件，开始分析处理，请稍候…")
                        threading.Thread(target=_do_analysis_and_reply, args=(from_user, file1, file2, from_user), daemon=True).start()
                else:
                    wechat_api.send_text_message(from_user, "文件下载失败，请重试。")
            
            return 'success'
    
    @app.route('/api/analyze', methods=['POST'])
    def analyze_files():
        """API endpoint for file analysis (for testing/direct API usage)"""
        try:
            # Check if files are in the request
            if 'file1' not in request.files or 'file2' not in request.files:
                return jsonify({
                    'success': False,
                    'error': 'Both file1 and file2 are required'
                }), 400
            
            file1 = request.files['file1']
            file2 = request.files['file2']
            instruction = request.form.get('instruction', '对比两个文件的差异')
            
            # Validate files
            if file1.filename == '' or file2.filename == '':
                return jsonify({
                    'success': False,
                    'error': 'Both files must have valid filenames'
                }), 400
            
            if not (allowed_file(file1.filename) and allowed_file(file2.filename)):
                return jsonify({
                    'success': False,
                    'error': f'File types not allowed. Allowed types: {app.config["ALLOWED_EXTENSIONS"]}'
                }), 400
            
            # Save files
            filename1 = secure_filename(file1.filename)
            filename2 = secure_filename(file2.filename)
            file1_path = os.path.join(app.config['UPLOAD_FOLDER'], f'temp_1_{filename1}')
            file2_path = os.path.join(app.config['UPLOAD_FOLDER'], f'temp_2_{filename2}')
            
            file1.save(file1_path)
            file2.save(file2_path)
            
            # Analyze files
            result = file_analyzer.analyze_files(file1_path, file2_path, instruction)
            
            # Clean up
            try:
                os.remove(file1_path)
                os.remove(file2_path)
            except:
                pass
            
            return jsonify(result)
            
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    return app


if __name__ == '__main__':
    # Get configuration from environment
    config_name = os.environ.get('FLASK_ENV', 'development')
    app = create_app(config_name)
    
    # Run the application
    app.run(
        host=app.config['HOST'],
        port=app.config['PORT'],
        debug=app.config['DEBUG']
    )
