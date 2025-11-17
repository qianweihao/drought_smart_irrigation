from flask import Flask, render_template, jsonify, redirect, url_for, request
import sys
import os
import warnings
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
import traceback
from datetime import datetime, timedelta
import numpy as np
import math

warnings.filterwarnings('ignore', category=UserWarning, module='requests')

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(project_root))

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    sys.path.insert(0, os.path.dirname(project_root))
    from config import Config
    logger.info("成功从项目根目录导入配置")
    # 验证田块配置
    try:
        Config.validate_fields_config()
    except Exception as e:
        logger.warning(f"田块配置验证失败: {e}")
except ImportError as e:
    logger.error(f"无法从项目根目录导入配置: {e}")
    logger.error(traceback.format_exc())
    
    try:
        from config.config import Config, get_config
        Config = get_config()
        logger.info("成功从本地config目录导入配置")
    except ImportError as e2:
        logger.error(f"无法从本地config目录导入配置: {e2}")
        logger.error(traceback.format_exc())
        
        class Config:
            """基本配置类"""
            DEBUG = True
            TESTING = False
            API_VERSION = 'v1'
            API_PREFIX = ''
            SECRET_KEY = 'fallback-secret-key'
        
        logger.warning("使用备用配置类")

try:
    from src.api.routes import create_routes
    logger.info("成功从src.api.routes导入路由")
except ImportError as e:
    logger.error(f"无法从src.api.routes导入API路由: {e}")
    logger.error(traceback.format_exc())
    
    try:
        from api.routes import create_routes
        logger.info("成功从本地api.routes导入路由")
    except ImportError as e:
        logger.error(f"无法导入API路由: {e}")
        logger.error(traceback.format_exc())
        def create_routes(config):
            from flask import Blueprint
            api = Blueprint('api', __name__, url_prefix='')
            logger.warning("使用空的API Blueprint")
            
            # 这是一个空的备用实现，当无法导入正常的routes.py时使用
            # 所有路由定义应当仅在routes.py中进行，这里仅作为故障安全机制
            
            return api

def create_app(config_class=Config):
    """创建并配置Flask应用"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    logger.info("正在启动智能墒情灌溉系统应用...")
    logger.info(f"项目根目录: {project_root}")
    logger.info(f"应用工作目录: {os.getcwd()}")
    
    try:
        api_blueprint = create_routes(config_class)
        
        app.register_blueprint(api_blueprint)
        logger.info(f"注册API Blueprint成功,应用路由规则: {app.url_map}")
    except Exception as e:
        logger.error(f"API Blueprint注册失败: {e}")
        logger.error(traceback.format_exc())
        logger.critical("无法加载路由,应用将没有任何有效端点!请检查routes.py文件和项目结构。")
    
    # 配置日志
    if not app.debug and not app.testing:
        logs_dir = os.path.join(os.path.dirname(project_root), 'logs')
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)
        
        log_file = os.path.join(logs_dir, 'app.log')
        file_handler = RotatingFileHandler(log_file, maxBytes=1024*1024, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        
        app.logger.info('应用启动完成')
    
    @app.errorhandler(404)
    def page_not_found(e):
        """处理404错误"""
        logger.warning(f"404错误: {request.path}")
        if request.path.startswith('/api/') or request.path == '/system_status':
            return jsonify({'status': 'error', 'message': f'API端点不存在: {request.path}'}), 404
        
        try:
            return render_template('404.html'), 404
        except Exception as template_error:
            logger.warning(f"无法渲染404.html模板: {template_error}")
            return """
            <!DOCTYPE html>
            <html>
            <head>
                <title>404 - 页面未找到</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; text-align: center; }
                    h1 { color: #d9534f; }
                    .card { border: 1px solid #d9534f; padding: 20px; margin: 0 auto; max-width: 600px; border-radius: 5px; }
                    a { color: #5bc0de; text-decoration: none; }
                    a:hover { text-decoration: underline; }
                </style>
            </head>
            <body>
                <h1>404 - 页面未找到</h1>
                <div class="card">
                    <p>您请求的页面不存在或已被移动。</p>
                    <p><a href="/">返回首页</a></p>
                </div>
            </body>
            </html>
            """, 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        """处理500错误"""
        logger.error(f"500错误: {str(e)}")
        if request.path.startswith('/api/'):
            return jsonify({'status': 'error', 'message': '服务器内部错误'}), 500
        
        try:
            return render_template('500.html'), 500
        except Exception as template_error:
            logger.warning(f"无法渲染500.html模板: {template_error}")
            return """
            <!DOCTYPE html>
            <html>
            <head>
                <title>500 - 服务器错误</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; text-align: center; }
                    h1 { color: #d9534f; }
                    .card { border: 1px solid #d9534f; padding: 20px; margin: 0 auto; max-width: 600px; border-radius: 5px; }
                    a { color: #5bc0de; text-decoration: none; }
                    a:hover { text-decoration: underline; }
                </style>
            </head>
            <body>
                <h1>500 - 服务器错误</h1>
                <div class="card">
                    <p>服务器发生内部错误，请稍后再试。</p>
                    <p><a href="/">返回首页</a></p>
                </div>
            </body>
            </html>
            """, 500
    
    return app

if __name__ == '__main__':
    app = create_app()
    print("应用路由规则:")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule.rule} [{', '.join(rule.methods)}]")
    
    app.run(debug=True, host='0.0.0.0', port=5000)