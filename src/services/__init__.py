# services包初始化文件
from .irrigation_service import IrrigationService

__all__ = ['IrrigationService']

# 导出需要在其他文件中直接使用的函数
# 这些函数在routes.py中被直接导入
def make_irrigation_decision(field_id, device_id, real_humidity):
    """生成灌溉决策的包装函数（简化版）
    
    Args:
        field_id (str): 田块ID
        device_id (str): 设备ID
        real_humidity (float): 实际土壤湿度（百分比）
    
    Returns:
        dict: 灌溉决策结果
        
    Note:
        SAT、FC、PWP 自动从传感器获取，无需传入
    """
    from .irrigation_service import IrrigationService
    from src.config import Config
    
    irrigation_service = IrrigationService(Config)
    return irrigation_service.make_irrigation_decision(field_id, device_id, real_humidity)

def get_soil_data_for_decision(field_id, device_id, real_humidity):
    """获取用于决策的土壤数据（简化版）
    
    Args:
        field_id (str): 田块ID
        device_id (str): 设备ID
        real_humidity (float): 实际土壤湿度（百分比）
    
    Returns:
        tuple: (SAT, FC, PWP, diff_max_real_mm, diff_min_real_mm, diff_com_real_mm)
        
    Note:
        SAT、FC、PWP 自动从传感器获取，无需传入
    """
    from .irrigation_service import IrrigationService
    from src.config import Config
    
    irrigation_service = IrrigationService(Config)
    return irrigation_service.calculate_soil_humidity_differences(field_id, device_id, real_humidity)