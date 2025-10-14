import os
import sys
import warnings

sys.dont_write_bytecode = True
warnings.filterwarnings('ignore')

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

def check_dependencies():
    """检查必要的依赖是否已安装"""
    required_packages = [
        'flask',
        'requests',
        'urllib3',
        #'charset-normalizer',
        'pandas',
        'numpy',
        #'python-dotenv',
        #'pyjwt',
        'marshmallow',
        'pyfao56',
        'loguru'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("错误: 以下依赖包未安装:")
        for package in missing_packages:
            print(f"  - {package}")
        print("\n请运行以下命令安装依赖:")
        print("pip install -r requirements.txt")
        sys.exit(1)

def run_app():
    check_dependencies()
    
    try:
        from src.app import create_app
    except ImportError as e:
        print(f"错误: 无法导入应用: {str(e)}")
        print("请确保所有必要的文件和依赖都已正确安装")
        sys.exit(1)
    
    os.environ['FLASK_ENV'] = 'development'
    
    app = create_app()
    
    print("="*50)
    print("注册的路由:")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint:30s} {rule.methods} {rule}")
    print("="*50)
    
    app.debug = True
    
    app.run(
        host='0.0.0.0',  
        port=5000,
        debug=True,
        use_reloader=True  # 启用热重载
    )

if __name__ == '__main__':
    try:
        run_app()
    except KeyboardInterrupt:
        print("\nServer shutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"\n错误: {str(e)}")
        sys.exit(1)