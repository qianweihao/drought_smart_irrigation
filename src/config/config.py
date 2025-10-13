import os
import sys
import logging

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.append(project_root)

try:
    from config import Config, get_config, current_config
    
    logging.info("成功从项目根目录导入配置")
    
    # 重新导出所需的类和函数，保持向后兼容
    __all__ = ['Config', 'get_config', 'current_config']
    
except ImportError as e:
    logging.error(f"无法从项目根目录导入配置: {str(e)}")
    raise 