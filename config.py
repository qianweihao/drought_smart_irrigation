import os
import sys
import logging
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

project_root = os.path.dirname(os.path.abspath(__file__))

# 配置验证函数
def validate_date_format(date_str):
    """验证日期格式是否符合YYYY/MM/DD格式"""
    try:
        datetime.strptime(date_str, '%Y/%m/%d')
        return True
    except ValueError:
        return False

def validate_number_range(value, min_val, max_val):
    """验证数值是否在指定范围内"""
    try:
        return min_val <= float(value) <= max_val
    except (ValueError, TypeError):
        return False

def validate_config(config_dict):
    """验证配置项的有效性"""
    validation_errors = []
    
    # 验证模拟时间范围
    for date_key in ['SIM_START_TIME', 'SIM_END_TIME', 'IRR_START_DATE', 'IRR_END_DATE']:
        if date_key in config_dict and not validate_date_format(config_dict[date_key]):
            validation_errors.append(f"{date_key}格式错误,应为YYYY/MM/DD")
    
    # 验证土壤参数范围
    soil_params = {
        'SOIL_FIELD_CAPACITY': (0, 1),
        'SOIL_WILTING_POINT': (0, 1),
        'SOIL_SATURATION': (0, 1),
        'SOIL_KSAT': (0, 10000),
        'SOIL_PENETRABILITY': (0, 100)
    }
    
    for param, (min_val, max_val) in soil_params.items():
        if param in config_dict and not validate_number_range(config_dict[param], min_val, max_val):
            validation_errors.append(f"{param}超出有效范围({min_val}-{max_val})")
    
    return validation_errors

class Config:
    """统一配置类"""
    
    # 基础配置
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    TESTING = os.getenv('TESTING', 'False').lower() == 'true'
    
    # API配置
    API_VERSION = os.getenv('API_VERSION', 'v1')
    API_PREFIX = os.getenv('API_PREFIX', '')
    
    # 安全配置
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-jwt-secret-key-here')
    
    # 目录配置
    APP_DIR = os.path.join(project_root, 'src')
    DATA_DIR = os.path.join(project_root, 'data')
    MODELS_DIR = os.path.join(APP_DIR, 'models')
    LOGS_DIR = os.path.join(project_root, 'logs')
    
    # 文件路径配置
    FILE_PATHS = {
        'model_output': os.path.join('data', 'model_output', 'wheat2024.out'),
        'growth_stages': os.path.join('data', 'model_output', 'growth_stages.csv'), 
        'root_depth': os.path.join('data', 'growth', 'root_depth.csv'),
        'weather_data': os.path.join('data', 'weather', 'irrigation_weather.csv'),
        'soil_profile': os.path.join('data', 'soil', 'irrigation_soilprofile_sim.csv')
    }
    
    # 邮件配置
    EMAIL_CONFIG = {
        'from_email': os.getenv('EMAIL_FROM'),
        'password': os.getenv('EMAIL_PASSWORD'),
        'smtp_server': os.getenv('SMTP_SERVER', 'smtp.qq.com'),
        'smtp_port': int(os.getenv('SMTP_PORT', 465))
    }

    # 作物参数-ETc-FAO
    CROP_PARAMS = {
        'Kcbini': float(os.getenv('KCBINI', 0.15)),#初始期基础作物系数
        'Kcbmid': float(os.getenv('KCBMID', 1.10)),#盛长期基础作物系数
        'Kcbend': float(os.getenv('KCBEND', 0.20)),#末期基础作物系数
        'Lini': int(os.getenv('LINI', 20)), #初始期天数
        'Ldev': int(os.getenv('LDEV', 90)), #速生期天数
        'Lmid': int(os.getenv('LMID', 70)), #盛长期天数
        'Lend': int(os.getenv('LEND', 32)), #末期天数
        'hmax': float(os.getenv('HMAX', 1)) #株高
    }

    # 土壤参数-ETc-FAO
    SOIL_PARAMS = {
        'thetaFC': float(os.getenv('THETA_FC', 0.250)),
        'thetaWP': float(os.getenv('THETA_WP', 0.152)),
        'theta0': float(os.getenv('THETA_0', 0.355)),
        'Zrini': float(os.getenv('ZR_INI', 0.20)),#取0.2-0.3m
        'Zrmax': float(os.getenv('ZR_MAX', 1.5)),#按中等情况设定，冬小麦通常 1.2–1.5m；深厚壤土、无障碍的土壤可取 1.8–2.0m；若有硬结层/浅土，保守用 0.8–1.0m
        'pbase': float(os.getenv('P_BASE', 0.55)),#无胁迫亏缺比例的基值，冬小麦基准值0.55
        'Ze': float(os.getenv('ZE', 0.10)),#表层蒸发土层厚度，0.10–0.15m
        'REW': float(os.getenv('REW', 9)) #易蒸发水量，粗质（砂/壤砂）：6–7mm;中等（壤土/粉壤/壤壤）：8–10mm;细质（粘壤/粘土）：10–12mm
    }

    # 灌溉决策基础参数配置-irrigation_service
    IRRIGATION_CONFIG = {
        'DEFAULT_FIELD_ID': os.getenv('DEFAULT_FIELD_ID', '1810564502987649024'),#田块id
        'DEFAULT_DEVICE_ID': os.getenv('DEFAULT_DEVICE_ID', '16031600028481'),#设备id
        'SOIL_DEPTH_CM': int(os.getenv('SOIL_DEPTH_CM', 30)),
        'MAX_FORECAST_DAYS': int(os.getenv('MAX_FORECAST_DAYS', 15)),
        'IRRIGATION_THRESHOLD': float(os.getenv('IRRIGATION_THRESHOLD', 0.6)),#基础灌溉阈值
        'MIN_EFFECTIVE_IRRIGATION': float(os.getenv('MIN_EFFECTIVE_IRRIGATION', 5.0)),#最小灌溉量
        # 灌溉量分档配置
        'IRRIGATION_LEVELS': [0, 5, 10, 15, 20, 25, 30, 40, 50],
        # 降雨相关阈值
        'MIN_RAIN_AMOUNT': float(os.getenv('MIN_RAIN_AMOUNT', 5.0)),
        'RAIN_FORECAST_DAYS': int(os.getenv('RAIN_FORECAST_DAYS', 3)),
        # 根系深度阈值-用于判断根系深度系数
        'ROOT_DEPTH_THRESHOLD': float(os.getenv('ROOT_DEPTH_THRESHOLD', 0.3)),
        # 最大单次灌溉量
        'MAX_SINGLE_IRRIGATION': float(os.getenv('MAX_SINGLE_IRRIGATION', 30.0)),
        # 数据验证范围
        'HUMIDITY_MIN_RANGE': float(os.getenv('HUMIDITY_MIN_RANGE', 0.0)),
        'HUMIDITY_MAX_RANGE': float(os.getenv('HUMIDITY_MAX_RANGE', 100.0)),
        # 最小预测数据天数
        'MIN_FORECAST_DATA_DAYS': int(os.getenv('MIN_FORECAST_DATA_DAYS', 3))
    }
    
    # 多田块-设备配置（支持多个田块和设备的管理）
    # 注意：每个田块的 field_id 应该是唯一的，如果多个田块使用相同的 field_id，
    # get_device_id_by_field 函数会返回第一个匹配的田块配置
    # 
    # 土壤参数配置说明：
    # 1. 使用手动配置的参数：
    #    - 设置 use_manual_soil_params=True
    #    - 在 soil_params 中提供 sat, fc, pwp 的值（单位：%）
    #    - 此时会忽略 sat_pwp_period 和 fc_period 的配置
    # 2. 使用统计方法（历史数据计算）：
    #    - 设置 use_manual_soil_params=False 或不设置此字段
    #    - 配置 sat_pwp_period 和 fc_period 指定历史数据查询时间段
    #    - 系统会根据历史数据统计计算 SAT、FC、PWP
    FIELDS_CONFIG = [
        {
            'field_id': '1810564865283239936',
            'device_id': '61725612366342',
            'field_name': 'F1',
            'crop_type': '小麦（百农1316）',
            'area': 12,  # 面积（亩）
            'description': '大户试验地（对照）',
            # 是否使用手动配置的土壤参数（True=手动配置，False或不设置=统计方法）
            'use_manual_soil_params': True,  # 设置为 True 时使用下面的 soil_params，False 时使用统计方法
            # 手动配置的土壤参数（仅在 use_manual_soil_params=True 时生效）
            'soil_params': {
                 'sat': 35.5,  # 饱和含水量（%）
                 'fc': 25.0,   # 田间持水量（%）
                 'pwp': 15.2   # 萎蔫点（%）
            },
            # SAT/PWP 历史数据查询时间段（用于统计SAT/PWP，仅在 use_manual_soil_params=False 时生效）
            'sat_pwp_period': {
                'start_date': '2025-08-01',  # 开始日期
                'end_date': None,  # None表示到当前日期
            },
            # FC 历史数据查询时间段（用于统计FC，仅在 use_manual_soil_params=False 时生效）
            'fc_period': {
                'start_date': '2025-11-16',
                'end_date': '2025-11-17',
            }
        },
        {
            'field_id': '1810565402921709568', 
            'device_id': '61725612366235',
            'field_name': 'F2',
            'crop_type': '小麦（百农1316）',
            'area': 12,
            'description': '大户试验地（决策组）',
            'use_manual_soil_params': True,  
            'soil_params': {
                'sat': 35.5,
                'fc': 25.0,
                'pwp': 15.2
            },
            'sat_pwp_period': {
                'start_date': '2025-08-01',
                'end_date': None,
            },
            'fc_period': {
                'start_date': '2025-11-16',
                'end_date': '2025-11-17',
            }
        },
        {
            'field_id': '1810565648737284096', 
            'device_id': '61725612366292',
            'field_name': 'F3',
            'crop_type': '小麦（百农1316）',
            'area': 12,
            'description': '大户试验地（决策组）',
            'use_manual_soil_params': True, 
            'soil_params': {
                'sat': 35.5,
                'fc': 25.0,
                'pwp': 15.2
            },
            'sat_pwp_period': {
                'start_date': '2025-08-01',
                'end_date': None,
            },
            'fc_period': {
                'start_date': '2025-11-16',
                'end_date': '2025-11-17',
            }
        },
        {
            'field_id': '1988864752989945856', 
            'device_id': '61725612366375',
            'field_name': 'F4',
            'crop_type': '小麦（百农1316）',
            'area': 12,
            'description': '大户试验地（决策组）',
            'use_manual_soil_params': True,  
            'soil_params': {
                'sat': 35.5,
                'fc': 25.0,
                'pwp': 15.2
            },
            'sat_pwp_period': {
                'start_date': '2025-08-01',
                'end_date': None,
            },
            'fc_period': {
                'start_date': '2025-11-16',
                'end_date': '2025-11-17',
            }
        },
        {
            'field_id': '1988865235397820416', 
            'device_id': '61725612366383',
            'field_name': 'F5',
            'crop_type': '小麦（百农1316）',
            'area': 12,
            'description': '大户试验地（决策组）',
            'use_manual_soil_params': True,  
            'soil_params': {
                'sat': 35.5,
                'fc': 25.0,
                'pwp': 15.2
            },
            'sat_pwp_period': {
                'start_date': '2025-08-01',
                'end_date': None,
            },
            'fc_period': {
                'start_date': '2025-11-16',
                'end_date': '2025-11-17',
            }
        },
        #...
    ]
    
    @classmethod
    def validate_fields_config(cls):
        """验证 FIELDS_CONFIG 配置的有效性
        
        检查：
        - 是否有重复的 field_id
        - 是否有缺失的必需字段
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if not cls.FIELDS_CONFIG:
            logger.warning("FIELDS_CONFIG 为空，将使用默认田块配置")
            return
        
        field_ids = []
        for i, field in enumerate(cls.FIELDS_CONFIG):
            field_id = field.get('field_id')
            device_id = field.get('device_id')
            field_name = field.get('field_name', f'田块{i+1}')
            
            # 检查必需字段
            if not field_id:
                logger.error(f"FIELDS_CONFIG[{i}] 缺少 field_id")
            if not device_id:
                logger.warning(f"FIELDS_CONFIG[{i}] ({field_name}) 缺少 device_id")
            
            # 检查重复的 field_id
            if field_id in field_ids:
                logger.warning(f"⚠️ 发现重复的 field_id: {field_id} (田块: {field_name})")
                logger.warning(f"   get_device_id_by_field 将返回第一个匹配的配置")
            else:
                field_ids.append(field_id)
        
        logger.info(f"FIELDS_CONFIG 验证完成，共 {len(cls.FIELDS_CONFIG)} 个田块配置")
    
    @classmethod
    def get_field_config(cls, field_id):
        """根据田块ID获取田块配置"""
        for field in cls.FIELDS_CONFIG:
            if field.get('field_id') == field_id:
                return field
        return None
    
    @classmethod
    def get_field_data_periods(cls, field_id):
        """获取田块的历史数据查询时间段配置
        
        返回:
            dict: {
                'sat_pwp': {'start_date': str, 'end_date': str or None},
                'fc': {'start_date': str, 'end_date': str}
            }
        """
        field_config = cls.get_field_config(field_id)
        
        if field_config:
            # 使用田块特定的时间段配置
            sat_pwp_period = field_config.get('sat_pwp_period', {})
            fc_period = field_config.get('fc_period', {})
            
            return {
                'sat_pwp': {
                    'start_date': sat_pwp_period.get('start_date'),
                    'end_date': sat_pwp_period.get('end_date')  # None表示到当前日期
                },
                'fc': {
                    'start_date': fc_period.get('start_date'),
                    'end_date': fc_period.get('end_date')
                }
            }
        else:
            # 使用全局默认配置
            query_ranges = cls.DATA_QUERY_RANGES
            return {
                'sat_pwp': {
                    'start_date': f"{query_ranges['MOISTURE_DATA_START_YEAR']}-{query_ranges['MOISTURE_DATA_START_MONTH']:02d}-{query_ranges['MOISTURE_DATA_START_DAY']:02d}",
                    'end_date': None
                },
                'fc': {
                    'start_date': f"{query_ranges['FC_DATA_START_YEAR']}-{query_ranges['FC_DATA_START_MONTH']:02d}-{query_ranges['FC_DATA_START_DAY']:02d}",
                    'end_date': f"{query_ranges['FC_DATA_END_YEAR']}-{query_ranges['FC_DATA_END_MONTH']:02d}-{query_ranges['FC_DATA_END_DAY']:02d}"
                }
            }
    
    @classmethod
    def get_field_soil_params(cls, field_id):
        """获取田块的手动配置的土壤参数
        
        如果田块配置了 use_manual_soil_params=True 且提供了 soil_params，
        则返回手动配置的参数；否则返回 None，表示使用统计方法计算
        
        返回:
            dict or None: {
                'sat': float,  # 饱和含水量（%）
                'fc': float,   # 田间持水量（%）
                'pwp': float   # 萎蔫点（%）
            } 或 None
        """
        field_config = cls.get_field_config(field_id)
        
        if not field_config:
            return None
        
        # 检查是否启用手动配置
        use_manual = field_config.get('use_manual_soil_params', False)
        if not use_manual:
            return None
        
        # 获取手动配置的土壤参数
        soil_params = field_config.get('soil_params', {})
        if not soil_params:
            return None
        
        # 验证参数是否完整
        sat = soil_params.get('sat')
        fc = soil_params.get('fc')
        pwp = soil_params.get('pwp')
        
        if sat is None or fc is None or pwp is None:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"田块 {field_id} 启用了手动土壤参数，但参数不完整，将使用统计方法")
            return None
        
        # 确保参数是数值类型
        try:
            return {
                'sat': float(sat),
                'fc': float(fc),
                'pwp': float(pwp)
            }
        except (ValueError, TypeError) as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"田块 {field_id} 的土壤参数格式错误: {e}，将使用统计方法")
            return None
    
    # 灌溉决策生育阶段系数配置
    GROWTH_STAGE_COEFFICIENTS = {
        "播种-出苗期": 0.6,
        "出苗-分蘖期": 0.7,
        "分蘖-越冬期": 0.8,
        "返青-拔节期": 0.9,
        "拔节-抽穗期": 1.0,
        "抽穗-成熟期": 0.9
    }

    # 根系深度系数配置
    ROOT_DEPTH_COEFFICIENTS = {
        "播种-出苗期": 0.3,
        "出苗-分蘖期": 0.5,
        "分蘖-越冬期": 0.7,
        "返青-拔节期": 0.9,
        "拔节-抽穗期": 1.0,
        "抽穗-成熟期": 1.0
    }

    # 灌溉服务默认系数配置
    DEFAULT_COEFFICIENTS = {
        'root_depth': float(os.getenv('DEFAULT_ROOT_DEPTH_COEFF', 1.0)),#当无法从aquacrop获取根系深度时，使用1.0作为中性系数
        'growth_stage': float(os.getenv('DEFAULT_GROWTH_STAGE_COEFF', 1.0)),#当无法从aquacrop获取生育阶段时，使用1.0作为中性系数
        'irrigation_threshold': float(os.getenv('DEFAULT_IRRIGATION_THRESHOLD_COEFF', 0.6))
    }

    # 告警配置
    ALERT_CONFIG = {
        'HUMIDITY_LOW_THRESHOLD': float(os.getenv('HUMIDITY_LOW_THRESHOLD', 0.3)),
        'HUMIDITY_HIGH_THRESHOLD': float(os.getenv('HUMIDITY_HIGH_THRESHOLD', 0.8)),
        'ALERT_EMAIL_RECIPIENTS': os.getenv('ALERT_EMAIL_RECIPIENTS', '').split(',')
    }

    # 墒情传感器默认值配置-soil_sensor
    SOIL_SENSOR_DEFAULTS = {
        # 默认数据配置
        'DEFAULT_MAX_HUMIDITY': float(os.getenv('DEFAULT_MAX_HUMIDITY', 35.5)),#次优先使用
        'DEFAULT_MIN_HUMIDITY': float(os.getenv('DEFAULT_MIN_HUMIDITY', 15.2)),#次优先使用
        'DEFAULT_REAL_HUMIDITY': float(os.getenv('DEFAULT_REAL_HUMIDITY', 25.0)),#次优先使用
        'DEFAULT_SAT': float(os.getenv('DEFAULT_SAT', 35.5)),#优先使用
        'DEFAULT_FC': float(os.getenv('DEFAULT_FC', 25.0)),#优先使用
        'DEFAULT_PWP': float(os.getenv('DEFAULT_PWP', 15.2)),#优先使用
        'DEFAULT_SOIL_DEPTH': float(os.getenv('DEFAULT_SOIL_DEPTH', 30.0)),
        'HUMIDITY_10CM_DEFAULT': float(os.getenv('HUMIDITY_10CM_DEFAULT', 15.0)),#完全降级
        'HUMIDITY_20CM_DEFAULT': float(os.getenv('HUMIDITY_20CM_DEFAULT', 20.0)),#完全降级
        'HUMIDITY_30CM_DEFAULT': float(os.getenv('HUMIDITY_30CM_DEFAULT', 25.0)),#完全降级
        
        # API配置
        'API_TIMEOUT': int(os.getenv('API_TIMEOUT', 15)),
        'API_MAX_RETRIES': int(os.getenv('API_MAX_RETRIES', 3)),
        'API_MAX_WAIT_TIME': int(os.getenv('API_MAX_WAIT_TIME', 10)),
        'HEALTH_CHECK_TIMEOUT': int(os.getenv('HEALTH_CHECK_TIMEOUT', 5)),
        
        # 熔断器配置
        'CIRCUIT_BREAKER_FAILURE_THRESHOLD': int(os.getenv('CIRCUIT_BREAKER_FAILURE_THRESHOLD', 5)),
        'CIRCUIT_BREAKER_RECOVERY_TIMEOUT': int(os.getenv('CIRCUIT_BREAKER_RECOVERY_TIMEOUT', 60)),
        
        # 重试策略配置
        'RETRY_TOTAL': int(os.getenv('RETRY_TOTAL', 2)),
        'RETRY_BACKOFF_FACTOR': float(os.getenv('RETRY_BACKOFF_FACTOR', 1.0)),
        
        # 历史数据配置
        'DEFAULT_HISTORY_DAYS': int(os.getenv('DEFAULT_HISTORY_DAYS', 30)),
        'SMOOTH_WINDOW': int(os.getenv('SMOOTH_WINDOW', 3))
    }

    # 灌溉服务默认土壤参数配置-irrigation_service
    DEFAULT_SOIL_PARAMS = {
        'fc': float(os.getenv('DEFAULT_SOIL_FC', 25.0)),
        'sat': float(os.getenv('DEFAULT_SOIL_SAT', 35.5)),
        'pwp': float(os.getenv('DEFAULT_SOIL_PWP', 15.2)),
        'depth_cm': float(os.getenv('DEFAULT_SOIL_DEPTH_CM', 30.0)) #用于土壤湿度计算
    }
    
    # API配置
    API_CONFIG = {
        'SOIL_API_URL': os.getenv('SOIL_API_URL', 'https://iland.zoomlion.com/open-sharing-platform/zlapi/'),
        'SOIL_API_KEY': os.getenv('SOIL_API_KEY', 'dWCkcdbdSeMqHyMQmZruWzwHR30cspVH'),
        # API查询参数配置
        'MAX_DAYS_RANGE': int(os.getenv('API_MAX_DAYS_RANGE', 365)),  # 最大查询天数范围
        'DEFAULT_DAYS': int(os.getenv('API_DEFAULT_DAYS', 30)),       # 默认查询天数
        'ET_DATA_MIN_COLUMNS': int(os.getenv('ET_DATA_MIN_COLUMNS', 20))  # ET数据文件最小列数要求
    }

    # 墒情传感器数据查询范围-默认值兜底
    DATA_QUERY_RANGES = {
        # 传感器极值/SAT/PWP数据查询日期设定
        'MOISTURE_DATA_START_YEAR': int(os.getenv('MOISTURE_DATA_START_YEAR', 2025)),
        'MOISTURE_DATA_START_MONTH': int(os.getenv('MOISTURE_DATA_START_MONTH', 8)),
        'MOISTURE_DATA_START_DAY': int(os.getenv('MOISTURE_DATA_START_DAY', 1)),
        # 传感器FC数据查询日期设定
        'FC_DATA_START_YEAR': int(os.getenv('FC_DATA_START_YEAR', 2025)),
        'FC_DATA_START_MONTH': int(os.getenv('FC_DATA_START_MONTH', 11)),
        'FC_DATA_START_DAY': int(os.getenv('FC_DATA_START_DAY', 16)),
        'FC_DATA_END_YEAR': int(os.getenv('FC_DATA_END_YEAR', 2025)),
        'FC_DATA_END_MONTH': int(os.getenv('FC_DATA_END_MONTH', 11)),
        'FC_DATA_END_DAY': int(os.getenv('FC_DATA_END_DAY', 17)),
    }
    
    # AquaCrop模型模拟配置
    AQUACROP_CONFIG = {
        # 模拟时间范围
        'SIM_START_TIME': os.getenv('AQUACROP_SIM_START_TIME', '2025/11/15'),
        'SIM_END_TIME': os.getenv('AQUACROP_SIM_END_TIME', '2026/6/15'),
        
        # 作物参数
        'CROP_NAME': os.getenv('AQUACROP_CROP_NAME', 'Wheat'),
        'PLANTING_DATE': os.getenv('AQUACROP_PLANTING_DATE', '11/15'),
        
        # 土壤基本物理参数
        'SOIL_TEXTURE':os.getenv('AQUACROP_SOIL_TEXTURE', 'custom'),
        'SOIL_KSAT': float(os.getenv('AQUACROP_SOIL_KSAT', 590)),
        'SOIL_PENETRABILITY': float(os.getenv('AQUACROP_SOIL_PENETRABILITY', 100)),
        # 土壤水力特征参数（备用）-优先使用soil_senso计算结果
        'SOIL_FIELD_CAPACITY': float(os.getenv('AQUACROP_SOIL_FC', 0.250)),
        'SOIL_WILTING_POINT': float(os.getenv('AQUACROP_SOIL_WP', 0.152)),
        'SOIL_SATURATION': float(os.getenv('AQUACROP_SOIL_SAT', 0.355)),
        # 灌溉管理
        'IRR_FREQUENCY': os.getenv('AQUACROP_IRR_FREQUENCY', '30D'),
        'IRR_DEPTH': float(os.getenv('AQUACROP_IRR_DEPTH', 30)),
        
        # 初始水分含量
        'INITIAL_WC_TYPE': os.getenv('AQUACROP_INITIAL_WC_TYPE', 'Prop'),
        'INITIAL_WC_METHOD': os.getenv('AQUACROP_INITIAL_WC_METHOD', 'Layer'),
        'INITIAL_WC_DEPTH_LAYER': [1], 
        'INITIAL_WC_VALUE': ['FC'],    
        
        # 文件路径
        'WEATHER_INPUT_CSV': os.getenv('AQUACROP_WEATHER_INPUT', 'data/weather/irrigation_weather.csv'),
        'WEATHER_OUTPUT_TXT': os.getenv('AQUACROP_WEATHER_OUTPUT', 'data/weather/aquacrop_weather.txt'),
        'OUTPUT_DIR': os.getenv('AQUACROP_OUTPUT_DIR', 'data/model_output'),
        'IMAGES_DIR': os.getenv('AQUACROP_IMAGES_DIR', 'src/static/images'),
        'STATIC_URL_PREFIX': os.getenv('AQUACROP_STATIC_URL_PREFIX', '/static/'),
        
        # ETo估算方法配置
        'ETO_METHOD': os.getenv('AQUACROP_ETO_METHOD', 'hargreaves_simplified'),  # 'observed'|'hargreaves_simplified'|'hargreaves_fao56'
        'LATITUDE': float(os.getenv('AQUACROP_LATITUDE', 35.3)),  # 河南新乡纬度，用于FAO-56计算
        'ELEVATION': float(os.getenv('AQUACROP_ELEVATION', 80.0)),  # 河南新乡海拔，用于FAO-56计算
        
        # 生育阶段定义-冠层覆盖度
        'GROWTH_STAGES_CANOPY_COVER': [
            {"阶段": "播种-出苗期", "min_cc": 0, "max_cc": 0.07},
            {"阶段": "出苗-分蘖期", "min_cc": 0.07, "max_cc": 0.3},
            {"阶段": "分蘖-越冬期", "min_cc": 0.3, "max_cc": 0.5},
            {"阶段": "返青-拔节期", "min_cc": 0.5, "max_cc": 0.8},
            {"阶段": "拔节-抽穗期", "min_cc": 0.8, "max_cc": 0.95},
            {"阶段": "抽穗-成熟期", "min_cc": 0.95, "max_cc": 1.0}
        ],
        # 生育阶段定义-DAP（备用）
        'GROWTH_STAGES_DAP': [
            {"阶段": "播种-出苗期", "开始DAP": 0, "结束DAP": 13},
            {"阶段": "出苗-分蘖期", "开始DAP": 14, "结束DAP": 45},
            {"阶段": "分蘖-越冬期", "开始DAP": 46, "结束DAP": 60},
            {"阶段": "返青-拔节期", "开始DAP": 61, "结束DAP": 95},
            {"阶段": "拔节-抽穗期", "开始DAP": 96, "结束DAP": 175},
            {"阶段": "抽穗-成熟期", "开始DAP": 176, "结束DAP": 230}
        ]
    }
    
    # 灌溉阈值配置
    AQUACROP_IRRIGATION_CONFIG = {
        # 灌溉方法选择：1=阈值触发，3=预定义计划
        'IRRIGATION_METHOD': int(os.getenv('AQUACROP_IRRIGATION_METHOD', 1)),
        # SMT参数
        'SMT': [
            float(os.getenv('SMT_INITIAL', 80)),      # 初期阶段
            float(os.getenv('SMT_DEVELOPMENT', 85)),  # 发育期
            float(os.getenv('SMT_MID', 90)),          # 中期阶段
            float(os.getenv('SMT_LATE', 80))          # 末期阶段
        ],
        'MAX_IRRIGATION_DEPTH': float(os.getenv('MAX_IRRIGATION_DEPTH', 25)),  # 最大灌溉深度(mm)
        'IRRIGATION_EFFICIENCY': float(os.getenv('IRRIGATION_EFFICIENCY', 85))  # 灌溉效率(%)
    }
    
    # FAO数据输入输出配置
    FAO_CONFIG = {
        # 输出文件
        'PAR_FILE': os.getenv('FAO_PAR_FILE', 'wheat2024.par'),
        'OUTPUT_FILE': os.getenv('FAO_OUTPUT_FILE', 'wheat2024.out'),
        'SUMMARY_FILE': os.getenv('FAO_SUMMARY_FILE', 'wheat2024.sum'),
        
        # 数据文件
        'WEATHER_FILE': os.getenv('FAO_WEATHER_FILE', 'data/weather/irrigation_weather.csv'),
        'TEMP_WEATHER_FILE': os.getenv('FAO_TEMP_WEATHER_FILE', 'data/weather/drought_irrigation.wth'),
        'FIXED_WEATHER_FILE': os.getenv('FAO_FIXED_WEATHER_FILE', 'data/weather/drought_irrigation_fixed.wth'),
        'SOIL_FILE': os.getenv('FAO_SOIL_FILE', 'data/soil/irrigation_soilprofile_sim.csv'),
        'SOIL_OUTPUT_FILE': os.getenv('FAO_SOIL_OUTPUT_FILE', 'data/soil/drought_irrigation.sol'),
        
        # ETref数据集成配置
        'FAO_OUTPUT_FILE': os.getenv('FAO_ETREF_OUTPUT_FILE', 'wheat2024.out'),  # FAO模型输出文件路径
        'USE_FAO_ETREF': os.getenv('USE_FAO_ETREF', 'true').lower() == 'true',  # 是否使用FAO模型的ETref数据
        'ETREF_FALLBACK_METHOD': os.getenv('ETREF_FALLBACK_METHOD', 'hargreaves_simplified')  # FAO数据不可用时的回退方法
    }
    
    # 天气模块配置
    WEATHER_CONFIG = {
        # 基础参数
        'latitude': float(os.getenv('WEATHER_LATITUDE', 35.0)),
        'longitude': float(os.getenv('WEATHER_LONGITUDE', 113.0)),
        'elevation': float(os.getenv('WEATHER_STATION_ELEVATION', 100.0)),

        # 位置参数
        'wind_height': float(os.getenv('WEATHER_STATION_WIND_HEIGHT', 2.0)),
        'reference_crop': os.getenv('WEATHER_STATION_REFERENCE_CROP', 'S'),

        # 作物信息
        'crop_type': os.getenv('CROP_TYPE', 'wheat'),
        
        # 小麦生长季配置
        'wheat_season_start_month': int(os.getenv('WHEAT_START_MONTH', 11)),
        'wheat_season_start_day': int(os.getenv('WHEAT_START_DAY', 15)),
        'wheat_season_end_month': int(os.getenv('WHEAT_END_MONTH', 6)),
        'wheat_season_end_day': int(os.getenv('WHEAT_END_DAY', 15)),
        
        # 玉米生长季配置
        'corn_season_start_month': int(os.getenv('CORN_START_MONTH', 7)),
        'corn_season_start_day': int(os.getenv('CORN_START_DAY', 1)),
        'corn_season_end_month': int(os.getenv('CORN_END_MONTH', 9)),
        'corn_season_end_day': int(os.getenv('CORN_END_DAY', 30)),
        
        # 棉花生长季配置
        'cotton_season_start_month': int(os.getenv('COTTON_START_MONTH', 4)),
        'cotton_season_start_day': int(os.getenv('COTTON_START_DAY', 10)),
        'cotton_season_end_month': int(os.getenv('COTTON_END_MONTH', 10)),
        'cotton_season_end_day': int(os.getenv('COTTON_END_DAY', 31)),
        
        # 通用配置
        'history_years': int(os.getenv('WEATHER_HISTORY_YEARS', 5)),
        'api_timeout': int(os.getenv('WEATHER_API_TIMEOUT', 15)),
        'max_retries': int(os.getenv('WEATHER_MAX_RETRIES', 3))
    }

    
    def __init__(self):
        """初始化配置，确保目录存在并验证配置有效性"""
        for directory in [self.DATA_DIR, self.LOGS_DIR, 
                          os.path.join(project_root, self.AQUACROP_CONFIG['OUTPUT_DIR']),
                          os.path.join(project_root, self.AQUACROP_CONFIG['IMAGES_DIR'])]:
            try:
                if not os.path.exists(directory):
                    os.makedirs(directory)
            except Exception as e:
                logging.warning(f"无法创建目录 {directory}: {str(e)}")
        
        # 验证AquaCrop配置
        errors = validate_config(self.AQUACROP_CONFIG)
        if errors:
            logging.warning(f"AquaCrop配置验证警告: {', '.join(errors)}")

# 配置环境映射
class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True

class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False

class TestingConfig(Config):
    """测试环境配置"""
    TESTING = True
    DEBUG = True

# 环境配置映射
config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

def get_config():
    """获取当前环境的配置"""
    env = os.getenv('FLASK_ENV', 'default')
    return config_by_name.get(env, DevelopmentConfig)

# 导出当前配置实例，便于直接导入
current_config = get_config()

# 确保配置可以被导入
if __name__ == "__main__":
    print("配置加载成功")
    cfg = current_config()
    print(f"环境: {os.getenv('FLASK_ENV', 'default')}")
    print(f"应用目录: {cfg.APP_DIR}")
    print(f"数据目录: {cfg.DATA_DIR}")
    print(f"模型目录: {cfg.MODELS_DIR}")
    print(f"日志目录: {cfg.LOGS_DIR}")