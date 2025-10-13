"""土壤传感器数据采集模块"""
import os
import pandas as pd
import sys
import requests
from datetime import datetime, timedelta
import numpy as np
import json
import math

try:
    from src.utils.logger import logger
except ImportError:
    try:
        from utils.logger import logger
    except ImportError:
        import logging
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(project_root)

from utils.logger import logger

API_URL = "http://api.soil-moisture.example.com"  
try:
    from src.config.config import get_config
    config = get_config()
    DEFAULT_MAX_HUMIDITY = config.SOIL_SENSOR_DEFAULTS.get('DEFAULT_MAX_HUMIDITY', 35.5)
    DEFAULT_MIN_HUMIDITY = config.SOIL_SENSOR_DEFAULTS.get('DEFAULT_MIN_HUMIDITY', 15.2)
    DEFAULT_REAL_HUMIDITY = config.SOIL_SENSOR_DEFAULTS.get('DEFAULT_REAL_HUMIDITY', 25.0)
    DEFAULT_SAT = config.SOIL_SENSOR_DEFAULTS.get('DEFAULT_SAT', 35.5)
    DEFAULT_FC = config.SOIL_SENSOR_DEFAULTS.get('DEFAULT_FC', 25.0)
    DEFAULT_PWP = config.SOIL_SENSOR_DEFAULTS.get('DEFAULT_PWP', 15.2)
    DEFAULT_SOIL_DEPTH = config.SOIL_SENSOR_DEFAULTS.get('DEFAULT_SOIL_DEPTH', 30.0)
    HUMIDITY_10CM_DEFAULT = config.SOIL_SENSOR_DEFAULTS.get('HUMIDITY_10CM_DEFAULT', 15.0)
    HUMIDITY_20CM_DEFAULT = config.SOIL_SENSOR_DEFAULTS.get('HUMIDITY_20CM_DEFAULT', 20.0)
    HUMIDITY_30CM_DEFAULT = config.SOIL_SENSOR_DEFAULTS.get('HUMIDITY_30CM_DEFAULT', 25.0)
    
    SOIL_API_URL = config.API_CONFIG.get('SOIL_API_URL', 'https://iland.zoomlion.com/open-sharing-platform/zlapi/')
    SOIL_API_KEY = config.API_CONFIG.get('SOIL_API_KEY', 'dWCkcdbdSeMqHyMQmZruWzwHR30cspVH')
    
    API_URL = SOIL_API_URL
    logger.info("成功加载土壤传感器配置")
except Exception as e:
    DEFAULT_MAX_HUMIDITY = 35.5
    DEFAULT_MIN_HUMIDITY = 15.2
    DEFAULT_REAL_HUMIDITY = 25.0
    DEFAULT_SAT = 35.5
    DEFAULT_FC = 25.0
    DEFAULT_PWP = 15.2
    DEFAULT_SOIL_DEPTH = 30.0
    HUMIDITY_10CM_DEFAULT = 15.0
    HUMIDITY_20CM_DEFAULT = 20.0
    HUMIDITY_30CM_DEFAULT = 25.0
    SOIL_API_URL = 'https://iland.zoomlion.com/open-sharing-platform/zlapi/'
    SOIL_API_KEY = 'dWCkcdbdSeMqHyMQmZruWzwHR30cspVH'
    logger.warning(f"加载配置失败，使用硬编码默认值: {e}")

"""获取土壤湿度数据(极值、饱和含水量SAT和凋萎系数PWP)"""
def get_soil_moisture_data(device_id):
    """
    获取土壤湿度数据，包括极值数据(max_humidity, min_humidity)和土壤参数(SAT, PWP)
    Args:
        device_id (str): 设备ID     
    Returns:
        tuple: (max_humidity, min_humidity, SAT, PWP)
    """
    end_date = datetime.now()
    try:
        start_year = config.DATA_QUERY_RANGES.get('MOISTURE_DATA_START_YEAR', 2024)
        start_month = config.DATA_QUERY_RANGES.get('MOISTURE_DATA_START_MONTH', 7)
        start_day = config.DATA_QUERY_RANGES.get('MOISTURE_DATA_START_DAY', 1)
        start_date = datetime(start_year, start_month, start_day)
        logger.info(f"使用配置的日期范围: {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
    except Exception as e:
        start_date = datetime(2024, 7, 1)
        logger.warning(f"无法获取配置的日期范围，使用默认值: {e}")
    
    start_day = start_date.strftime("%Y-%m-%d")
    end_day = end_date.strftime("%Y-%m-%d")
    
    url = "https://iland.zoomlion.com/open-sharing-platform/zlapi/soilTestingApi/v1/getDailyAvg"
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded', 
        'Authorization': SOIL_API_KEY
    }
    data = {
        'deviceCode': f"{device_id}",
        'startDay': start_day,
        'endDay': end_day
    }
    
    logger.info(f"获取土壤湿度数据: 使用日期范围 {start_day} 到 {end_day}")
    
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        history_data = response.json()

        if history_data.get('code') == 0 and 'data' in history_data:
            soil_data = history_data['data']
            
            if not soil_data: 
                logger.warning("API返回的数据列表为空")
                return DEFAULT_MAX_HUMIDITY, DEFAULT_MIN_HUMIDITY, DEFAULT_SAT, DEFAULT_PWP
                
            soil_data_dt = pd.DataFrame(soil_data)
            soil_data_dt['soilHumidity10Value'] = pd.to_numeric(soil_data_dt['soilHumidity10Value'], errors='coerce')
            soil_data_dt['soilHumidity20Value'] = pd.to_numeric(soil_data_dt['soilHumidity20Value'], errors='coerce')
            soil_data_dt['soilHumidity30Value'] = pd.to_numeric(soil_data_dt['soilHumidity30Value'], errors='coerce')
            
            soil_data_dt = soil_data_dt[(soil_data_dt['soilHumidity10Value'] >= 10) & 
                                        (soil_data_dt['soilHumidity20Value'] >= 10) & 
                                        (soil_data_dt['soilHumidity30Value'] >= 10)]
            
            if len(soil_data_dt) == 0:
                logger.warning("过滤异常值后无有效数据")
                return DEFAULT_MAX_HUMIDITY, DEFAULT_MIN_HUMIDITY, DEFAULT_SAT, DEFAULT_PWP
                
            soil_data_dt['dt'] = pd.to_datetime(soil_data_dt['dt'], errors='coerce')
            soil_data_dt.sort_values('dt', inplace=True)

            max_10 = soil_data_dt['soilHumidity10Value'].max()
            max_20 = soil_data_dt['soilHumidity20Value'].max()
            max_30 = soil_data_dt['soilHumidity30Value'].max()
            
            min_10 = soil_data_dt['soilHumidity10Value'].min()
            min_20 = soil_data_dt['soilHumidity20Value'].min()
            min_30 = soil_data_dt['soilHumidity30Value'].min()
            
            if pd.isna([max_10, max_20, max_30, min_10, min_20, min_30]).any():
                logger.warning("计算出的值包含NaN值,使用默认值")
                return DEFAULT_MAX_HUMIDITY, DEFAULT_MIN_HUMIDITY, DEFAULT_SAT, DEFAULT_PWP
                
            max_humidity = round((max_30 + max_30 + max_30) / 3, 2)
            min_humidity = round((min_30 + min_30 + min_30) / 3, 2)
            
            sat = round((max_30 + max_30 + max_30) / 3, 2)  # 饱和含水量SAT
            pwp = round((min_30 + min_30 + min_30) / 3, 2)  # 凋萎点PWP
            
            if max_humidity <= min_humidity or max_humidity > 45 or min_humidity < 10 or sat <= pwp or sat > 50 or pwp < 10:
                logger.warning(f"计算出的值不合理(max={max_humidity}, min={min_humidity}, SAT={sat}, PWP={pwp})，使用默认值")
                return DEFAULT_MAX_HUMIDITY, DEFAULT_MIN_HUMIDITY, DEFAULT_SAT, DEFAULT_PWP

            logger.info(f"获取土壤湿度数据: max={max_humidity}, min={min_humidity}, SAT={sat}, PWP={pwp}")
            return max_humidity, min_humidity, sat, pwp
        else:
            logger.error("API返回无效数据或错误")
            return DEFAULT_MAX_HUMIDITY, DEFAULT_MIN_HUMIDITY, DEFAULT_SAT, DEFAULT_PWP
    except Exception as e:
        logger.error(f"获取土壤湿度数据失败: {str(e)}")
        
        return DEFAULT_MAX_HUMIDITY, DEFAULT_MIN_HUMIDITY, DEFAULT_SAT, DEFAULT_PWP

def save_extremum_humidity_data(device_id):
    """获取土壤湿度极值数据（向后兼容）"""
    max_humidity, min_humidity, _, _ = get_soil_moisture_data(device_id)
    return max_humidity, min_humidity

def get_sat_pwp_data(device_id):
    """获取饱和含水量和凋萎系数数据（向后兼容）"""
    _, _, sat, pwp = get_soil_moisture_data(device_id)
    return sat, pwp

"""获取实时土壤湿度数据"""
def save_real_humidity_data(field_id):
    url = "https://iland.zoomlion.com/open-sharing-platform/zlapi/irrigationApi/v2/getSoilLast"
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded', 
        'Authorization': SOIL_API_KEY
    }
    data = {'sectionID': f"{field_id}"}
    
    logger.info(f"获取实时土壤湿度数据: field_id={field_id}")
    
    try:
        logger.info(f"调用API获取实时土壤湿度: url={url}, data={data}")
        response = requests.post(url, headers=headers, data=data, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"获取实时土壤湿度失败: HTTP状态码 {response.status_code}")
            return DEFAULT_REAL_HUMIDITY
        
        try:
            logger.info(f"实时湿度API完整响应: {response.text}")
        except Exception as e:
            logger.error(f"打印API响应时出错: {str(e)}")
        
        resp_json = response.json()
        logger.info(f"响应JSON结构: {json.dumps(resp_json, ensure_ascii=False)}")
        
        if 'code' not in resp_json:
            logger.error(f"实时湿度API响应缺少'code'字段")
            return DEFAULT_REAL_HUMIDITY
        
        if resp_json.get('code') == 0:
            if 'data' not in resp_json:
                logger.error(f"实时湿度API响应缺少data字段,响应结构: {resp_json}")
                return DEFAULT_REAL_HUMIDITY
                
            if not resp_json['data']:
                logger.error(f"实时湿度API响应data字段为空,响应结构: {resp_json}")
                return DEFAULT_REAL_HUMIDITY
                
            logger.info(f"data字段内容: {resp_json['data']}")           
            real_humidity_data = resp_json.get('data')[0]
            logger.info(f"实时湿度数据字段: {list(real_humidity_data.keys())}")
            
            if 'soilHumidity30Value' not in real_humidity_data:
                logger.error(f"实时湿度API响应缺少必要字段: {list(real_humidity_data.keys())}")
                
                humidity_fields = [key for key in real_humidity_data.keys() if 'humidity' in key.lower() or 'soil' in key.lower()]
                logger.info(f"可能的湿度字段: {humidity_fields}")
                
                if humidity_fields:
                    alt_field = humidity_fields[0]
                    logger.info(f"尝试使用替代字段: {alt_field}")
                    try:
                        real_humidity = round(float(real_humidity_data[alt_field]), 2)
                        logger.info(f"使用替代字段 {alt_field} 成功获取湿度: {real_humidity}%")
                        return real_humidity
                    except (ValueError, TypeError) as e:
                        logger.error(f"替代字段值转换失败: {str(e)}")
                        
                return DEFAULT_REAL_HUMIDITY
            
            
            try:
                real_humidity = round(float(real_humidity_data['soilHumidity30Value']), 2)
                
                if real_humidity < 0 or real_humidity > 100:
                    logger.warning(f"实时湿度值超出合理范围: {real_humidity}%，使用默认值替代")
                    return DEFAULT_REAL_HUMIDITY
                    
                if 'msgTimeStr' in real_humidity_data:
                    try:
                        real_humidity_data['msgTimeStr'] = pd.to_datetime(real_humidity_data['msgTimeStr'], unit='ms')
                        logger.info(f"获取实时土壤湿度数据: {real_humidity}%, 时间: {real_humidity_data['msgTimeStr']}")
                    except Exception as e:
                        logger.warning(f"时间戳转换失败: {str(e)}")
                        logger.info(f"获取实时土壤湿度数据: {real_humidity}%")
                else:
                    logger.info(f"获取实时土壤湿度数据: {real_humidity}%")
                    
                return real_humidity
                
            except (ValueError, TypeError) as e:
                logger.error(f"实时湿度值转换失败: {str(e)}, 原始值: {real_humidity_data.get('soilHumidity30Value')}")
                return DEFAULT_REAL_HUMIDITY
        else:
            logger.error(f"实时湿度API返回错误: code={resp_json.get('code')}, msg={resp_json.get('msg', '无错误信息')}")
            return DEFAULT_REAL_HUMIDITY
        
    except requests.RequestException as e:
        logger.error(f"获取实时土壤湿度HTTP请求失败: {str(e)}")
        return DEFAULT_REAL_HUMIDITY
    except json.JSONDecodeError as e:
        logger.error(f"实时湿度API响应解析JSON失败: {str(e)}")
        return DEFAULT_REAL_HUMIDITY
    except Exception as e:
        logger.error(f"获取实时土壤湿度数据失败: {str(e)}")
        return DEFAULT_REAL_HUMIDITY

"""获取田间持水量(FC)"""
def get_field_capacity_data(device_id):
    try:
        # 从配置获取日期范围
        start_year = config.DATA_QUERY_RANGES.get('FC_DATA_START_YEAR', 2024)
        start_month = config.DATA_QUERY_RANGES.get('FC_DATA_START_MONTH', 10)
        start_day = config.DATA_QUERY_RANGES.get('FC_DATA_START_DAY', 15)
        
        end_year = config.DATA_QUERY_RANGES.get('FC_DATA_END_YEAR', 2024)
        end_month = config.DATA_QUERY_RANGES.get('FC_DATA_END_MONTH', 10)
        end_day = config.DATA_QUERY_RANGES.get('FC_DATA_END_DAY', 31)
        
        start_date = datetime(start_year, start_month, start_day)
        end_date = datetime(end_year, end_month, end_day)
        logger.info(f"使用配置的日期范围: {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
    except Exception as e:
        # 如果配置获取失败，使用默认值
        start_date = datetime(2024, 10, 15)
        end_date = datetime(2024, 10, 31)
        logger.warning(f"无法获取配置的日期范围，使用默认值: {e}")
    
    start_day = start_date.strftime("%Y-%m-%d")
    end_day = end_date.strftime("%Y-%m-%d")
    
    url = "https://iland.zoomlion.com/open-sharing-platform/zlapi/soilTestingApi/v1/getDailyAvg"
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded', 
        'Authorization': SOIL_API_KEY
    }
    data = {
        'deviceCode': f"{device_id}",
        'startDay': start_day,
        'endDay': end_day
    }
    
    logger.info(f"获取田间持水量(FC)数据: 使用日期范围 {start_day} 到 {end_day}")
    
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        history_data = response.json()

        if history_data.get('code') == 0 and 'data' in history_data:
            soil_data = history_data['data']
            
            if not soil_data: 
                logger.warning("获取田间持水量FC: API返回的数据列表为空")
                return DEFAULT_FC
                
            soil_data_dt = pd.DataFrame(soil_data)
            soil_data_dt['soilHumidity10Value'] = pd.to_numeric(soil_data_dt['soilHumidity10Value'], errors='coerce')
            soil_data_dt['soilHumidity20Value'] = pd.to_numeric(soil_data_dt['soilHumidity20Value'], errors='coerce')
            soil_data_dt['soilHumidity30Value'] = pd.to_numeric(soil_data_dt['soilHumidity30Value'], errors='coerce')
            
            soil_data_dt = soil_data_dt[(soil_data_dt['soilHumidity10Value'] > 0) & 
                                        (soil_data_dt['soilHumidity20Value'] > 0) & 
                                        (soil_data_dt['soilHumidity30Value'] > 0)]
            
            if len(soil_data_dt) == 0:
                logger.warning("获取田间持水量FC: 过滤0值后无有效数据")
                return DEFAULT_FC
                
            soil_data_dt['dt'] = pd.to_datetime(soil_data_dt['dt'], errors='coerce')
            soil_data_dt.sort_values('dt', inplace=True)

            min_10 = soil_data_dt['soilHumidity10Value'].min()
            min_20 = soil_data_dt['soilHumidity20Value'].min()
            min_30 = soil_data_dt['soilHumidity30Value'].min()
            
            if pd.isna([min_10, min_20, min_30]).any():
                logger.warning("获取田间持水量FC: 计算出的值包含NaN值,使用默认值")
                return DEFAULT_FC
            fc = round((min_30 + min_30 + min_30) / 3, 2)  
            if fc < 5 or fc > 35:
                logger.warning(f"获取田间持水量FC: 计算出的值不合理(FC={fc})，使用默认值")
                return DEFAULT_FC

            logger.info(f"获取田间持水量: FC={fc}")
            return fc
        else:
            logger.error("获取田间持水量FC: API返回无效数据或错误")
            return DEFAULT_FC
    except Exception as e:
        logger.error(f"获取田间持水量失败: {str(e)}")
        return DEFAULT_FC

"""调取土壤参数(SAT, FC, PWP)"""
def get_soil_parameters(device_id):
    """获取土壤参数，包括饱和含水量(SAT)、田间持水量(FC)和凋萎系数(PWP)
    
    Args:
        device_id (str): 设备ID
        
    Returns:
        dict: 包含土壤参数的字典
    """
    logger.info(f"获取土壤参数: device_id={device_id}")
    
    try:
        _, _, sat, pwp = get_soil_moisture_data(device_id)
        fc = get_field_capacity_data(device_id)
        
        if not (5 <= pwp <= 25 and 25 <= sat <= 45 and pwp < sat):
            logger.warning(f"土壤参数不合理: sat={sat}, pwp={pwp}，使用默认值")
            sat = DEFAULT_SAT  
            pwp = DEFAULT_PWP 
            
        if not (pwp < fc < sat):
            logger.warning(f"田间持水量不合理: fc={fc}，使用默认值")
            fc = DEFAULT_FC 
            
        logger.info(f"成功获取土壤参数: sat={sat}, fc={fc}, pwp={pwp}")
        
        return {
            'sat': sat,
            'fc': fc,
            'pwp': pwp,
            'is_real_data': True
        }
    except Exception as e:
        logger.error(f"获取土壤参数失败: {str(e)}")
        return {
            'sat': DEFAULT_SAT,
            'fc': DEFAULT_FC,
            'pwp': DEFAULT_PWP,
            'is_real_data': False
        }

class SoilSensor:
    def __init__(self, device_id, field_id):
        """初始化土壤传感器
        
        Args:
            device_id (str): 设备ID
            field_id (str): 地块ID
        """
        self.device_id = device_id
        self.field_id = field_id
        self.use_real_api = True
        logger.info(f"SoilSensor初始化: device_id={device_id}, field_id={field_id}, 使用真实API数据")
        
    def get_current_data(self):
        """获取当前土壤数据"""
        logger.info(f"获取当前土壤数据: device_id={self.device_id}, field_id={self.field_id}")
        
        try:
            
            max_humidity, min_humidity, sat, pwp = get_soil_moisture_data(self.device_id)
            logger.info(f"获取到土壤湿度数据: max_humidity={max_humidity}, min_humidity={min_humidity}, sat={sat}, pwp={pwp}")
            
            
            real_humidity = save_real_humidity_data(self.field_id)
            logger.info(f"获取到实时湿度数据: real_humidity={real_humidity}")
            
            #
            fc = get_field_capacity_data(self.device_id)
            logger.info(f"获取到田间持水量数据: fc={fc}")
            
            
            if not (5 <= min_humidity <= 25 and 25 <= max_humidity <= 45 and min_humidity < max_humidity):
                logger.warning(f"极值数据不合理，使用默认值替代: min_humidity={min_humidity}, max_humidity={max_humidity}")
                min_humidity = DEFAULT_MIN_HUMIDITY  
                max_humidity = DEFAULT_MAX_HUMIDITY  
                
            if not (min_humidity <= real_humidity <= 45):
                logger.warning(f"实时湿度数据不合理，使用合理值替代: real_humidity={real_humidity}")
                real_humidity = min(max(real_humidity, min_humidity), 45)
                
            if sat is None or sat <= 0:
                sat = max_humidity      
            if pwp is None or pwp <= 0:
                pwp = min_humidity  
            if fc is None or fc <= 0:
                fc = (sat + pwp) / 2 
                
            logger.info(f"使用真实数据: max_humidity={max_humidity}, min_humidity={min_humidity}, real_humidity={real_humidity}, sat={sat}, pwp={pwp}, fc={fc}")
            
            return {
                'max_humidity': max_humidity,
                'min_humidity': min_humidity,
                'real_humidity': real_humidity,
                'sat': sat,
                'fc': fc,
                'pwp': pwp,
                'is_real_data': True
            }
        except Exception as e:
            logger.error(f"获取当前土壤数据失败: {str(e)}")
            
            
            max_humidity = DEFAULT_MAX_HUMIDITY   
            min_humidity = DEFAULT_MIN_HUMIDITY   
            real_humidity = DEFAULT_REAL_HUMIDITY  
            
            logger.warning("获取真实数据失败，使用默认值")
            
            return {
                'max_humidity': max_humidity,
                'min_humidity': min_humidity,
                'real_humidity': real_humidity,
                'sat': DEFAULT_SAT,
                'fc': DEFAULT_FC, 
                'pwp': DEFAULT_PWP,
                'is_real_data': False
            }
    
    def get_history_humidity_data(self, days=30):
        """获取历史土壤湿度数据
        
        Args:
            days (int): 获取过去多少天的数据,默认30天
        
        Returns:
            pandas.DataFrame: 包含土壤湿度历史数据的DataFrame
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            start_day = start_date.strftime('%Y-%m-%d')
            end_day = end_date.strftime('%Y-%m-%d')
            
            url = "https://iland.zoomlion.com/open-sharing-platform/zlapi/soilTestingApi/v1/getDailyAvg"
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded', 
                'Authorization': SOIL_API_KEY
            }
            data = {
                'deviceCode': f"{self.device_id}",
                'startDay': start_day,
                'endDay': end_day
            }
            
            logger.info(f"尝试调用API获取历史数据: url={url}, 参数={data}")
            
            response = requests.post(url, headers=headers, data=data, timeout=15)
            
            if response.status_code != 200:
                logger.error(f"API响应状态码非200: {response.status_code}")
                return None
            
            history_data = response.json()
            
            if history_data.get('code') == 0 and 'data' in history_data and len(history_data['data']) > 0:
                soil_data = history_data['data']
                logger.info(f"获取到历史数据 {len(soil_data)} 条记录")
                
                soil_data_dt = pd.DataFrame(soil_data)
                req_columns = ['soilHumidity10Value', 'soilHumidity20Value', 'soilHumidity30Value', 'dt']
                missing_columns = [col for col in req_columns if col not in soil_data_dt.columns]
                
                if missing_columns:
                    logger.warning(f"历史数据缺少必要的列: {missing_columns}")
                    return None
                
                logger.info("数据样本(前3条):")
                for i, row in enumerate(soil_data[:3]):
                    logger.info(f"  样本 {i+1}: {row}")
                
                soil_data_dt['soilHumidity10Value'] = pd.to_numeric(soil_data_dt['soilHumidity10Value'], errors='coerce')
                soil_data_dt['soilHumidity20Value'] = pd.to_numeric(soil_data_dt['soilHumidity20Value'], errors='coerce')
                soil_data_dt['soilHumidity30Value'] = pd.to_numeric(soil_data_dt['soilHumidity30Value'], errors='coerce')
                
                if (soil_data_dt['soilHumidity10Value'].isna().all() and 
                    soil_data_dt['soilHumidity20Value'].isna().all() and 
                    soil_data_dt['soilHumidity30Value'].isna().all()):
                    logger.warning("API返回的所有湿度数据都无法转换为数值")
                    return None
                
                logger.info("转换后的数据统计:")
                for col in ['soilHumidity10Value', 'soilHumidity20Value', 'soilHumidity30Value']:
                    valid_count = soil_data_dt[col].notna().sum()
                    min_val = soil_data_dt[col].min() if valid_count > 0 else "N/A"
                    max_val = soil_data_dt[col].max() if valid_count > 0 else "N/A"
                    mean_val = soil_data_dt[col].mean() if valid_count > 0 else "N/A"
                    logger.info(f"{col}: 有效值数量={valid_count}, 最小值={min_val}, 最大值={max_val}, 平均值={mean_val}")
                
                for col in ['soilHumidity10Value', 'soilHumidity20Value', 'soilHumidity30Value']:
                    if soil_data_dt[col].isna().all():
                        alt_col = col.replace('Value', '')  
                        if alt_col in soil_data_dt.columns:
                            logger.info(f"尝试使用替代列 {alt_col} 代替 {col}")
                            soil_data_dt[col] = pd.to_numeric(soil_data_dt[alt_col], errors='coerce')
                
                if (soil_data_dt['soilHumidity10Value'].isna().all() and 
                    soil_data_dt['soilHumidity20Value'].isna().all() and 
                    soil_data_dt['soilHumidity30Value'].isna().all()):
                    logger.warning("即使尝试替代列名后,API返回的所有湿度数据仍然无法转换为数值")
                    return None
                
                soil_data_dt['date'] = pd.to_datetime(soil_data_dt['dt'], errors='coerce')
                
                for col in ['soilHumidity10Value', 'soilHumidity20Value', 'soilHumidity30Value']:
                    soil_data_dt[col] = soil_data_dt[col].clip(0, 100)  
                    if soil_data_dt[col].isna().any():
                        mean_val = soil_data_dt[col].mean()
                        if pd.isna(mean_val): 
                            if '10Value' in col:
                                default_val = HUMIDITY_10CM_DEFAULT
                            elif '20Value' in col:
                                default_val = HUMIDITY_20CM_DEFAULT
                            else:
                                default_val = HUMIDITY_30CM_DEFAULT
                            soil_data_dt[col] = soil_data_dt[col].fillna(default_val)
                        else:
                            soil_data_dt[col] = soil_data_dt[col].fillna(mean_val)
                
                for col in ['soilHumidity10Value', 'soilHumidity20Value', 'soilHumidity30Value']:
                    soil_data_dt[col] = soil_data_dt[col].rolling(window=3, min_periods=1).mean()
                
                result_df = soil_data_dt[['date', 'soilHumidity10Value', 'soilHumidity20Value', 'soilHumidity30Value']]
                
                logger.info(f"成功处理 {len(result_df)} 条历史土壤湿度数据")
                return result_df
            else:
                logger.warning(f"API返回无效数据: {history_data.get('code')}")
                return None
        except Exception as e:
            logger.error(f"获取历史湿度数据时出错: {e}")
            return None

    def get_soil_humidity_forecast(self, field_id):
        """
        获取未来15天的土壤湿度预测

        Args:
            field_id (str): 地块ID
        
        Returns:
            list: 未来15天的土壤湿度预测
        """
        forecast_data = []
        try:
            # 从配置获取预测日期范围
            start_year = config.DATA_QUERY_RANGES.get('FORECAST_DATA_START_YEAR', 2024)
            start_month = config.DATA_QUERY_RANGES.get('FORECAST_DATA_START_MONTH', 10)
            start_day = config.DATA_QUERY_RANGES.get('FORECAST_DATA_START_DAY', 15)
            
            end_year = config.DATA_QUERY_RANGES.get('FORECAST_DATA_END_YEAR', 2024)
            end_month = config.DATA_QUERY_RANGES.get('FORECAST_DATA_END_MONTH', 10)
            end_day = config.DATA_QUERY_RANGES.get('FORECAST_DATA_END_DAY', 31)
            
            start_date = datetime(start_year, start_month, start_day)
            end_date = datetime(end_year, end_month, end_day)
            logger.info(f"使用配置的预测日期范围: {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
        except Exception as e:
            # 默认使用硬编码日期
            start_date = datetime(2024, 10, 15)
            end_date = datetime(2024, 10, 31)
            logger.warning(f"无法获取配置的预测日期范围，使用默认值: {e}")
            
        # 生成日期序列

if __name__ == "__main__":
    device_id = '16031600028481'
    field_id = "1810564502987649024"
    sensor = SoilSensor(device_id, field_id)
    try:
        data = sensor.get_current_data()
        print(data)
        
        history_data = sensor.get_history_humidity_data(days=30)
        print(f"获取到 {len(history_data)} 条历史数据")
        print(history_data.head())
        
        print("\n数据统计:")
        for col in ['soilHumidity10Value', 'soilHumidity20Value', 'soilHumidity30Value']:
            print(f"{col}: 最小值={history_data[col].min():.2f}, 平均值={history_data[col].mean():.2f}, 最大值={history_data[col].max():.2f}")
    except Exception as e:
        print(f"运行时发生错误: {str(e)}")