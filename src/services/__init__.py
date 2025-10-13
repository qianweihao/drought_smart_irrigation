# services包初始化文件
from .irrigation_service import IrrigationService

__all__ = ['IrrigationService']

# 导出需要在其他文件中直接使用的函数
# 这些函数在routes.py中被直接导入
def make_irrigation_decision(field_id, max_humidity, min_humidity, real_humidity):
    """生成灌溉决策的包装函数"""
    from .irrigation_service import IrrigationService
    from src.config import Config
    
    irrigation_service = IrrigationService(Config)
    return irrigation_service.make_irrigation_decision(field_id, max_humidity, min_humidity, real_humidity)

def get_soil_data_for_decision(max_humidity, min_humidity, real_humidity):
    """获取用于决策的土壤数据"""
    from .irrigation_service import IrrigationService
    from src.config import Config
    
    irrigation_service = IrrigationService(Config)
    return irrigation_service.calculate_soil_humidity_differences(max_humidity, real_humidity, min_humidity)