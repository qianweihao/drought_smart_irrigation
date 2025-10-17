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
    
    # 文件路径配置 - 使用相对路径，自动适配不同环境
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

    # 作物参数-ETc
    CROP_PARAMS = {
        'Kcbini': float(os.getenv('KCBINI', 0.15)),
        'Kcbmid': float(os.getenv('KCBMID', 1.10)),
        'Kcbend': float(os.getenv('KCBEND', 0.20)),
        'Lini': int(os.getenv('LINI', 20)),
        'Ldev': int(os.getenv('LDEV', 50)),
        'Lmid': int(os.getenv('LMID', 70)),
        'Lend': int(os.getenv('LEND', 30)),
        'hmax': float(os.getenv('HMAX', 1))
    }

    # 土壤参数-ETc
    SOIL_PARAMS = {
        'thetaFC': float(os.getenv('THETA_FC', 0.327)),
        'thetaWP': float(os.getenv('THETA_WP', 0.10)),
        'theta0': float(os.getenv('THETA_0', 0.327)),
        'Zrini': float(os.getenv('ZR_INI', 0.20)),
        'Zrmax': float(os.getenv('ZR_MAX', 1.7)),
        'pbase': float(os.getenv('P_BASE', 0.55)),
        'Ze': float(os.getenv('ZE', 0.10)),
        'REW': float(os.getenv('REW', 9))
    }

    # 灌溉决策基础参数配置
    IRRIGATION_CONFIG = {
        'DEFAULT_FIELD_ID': os.getenv('DEFAULT_FIELD_ID', '1810564502987649024'),
        'DEFAULT_DEVICE_ID': os.getenv('DEFAULT_DEVICE_ID', '16031600028481'),
        'SOIL_DEPTH_CM': int(os.getenv('SOIL_DEPTH_CM', 30)),
        'MAX_FORECAST_DAYS': int(os.getenv('MAX_FORECAST_DAYS', 15)),
        'IRRIGATION_THRESHOLD': float(os.getenv('IRRIGATION_THRESHOLD', 0.6)),
        'MIN_EFFECTIVE_IRRIGATION': float(os.getenv('MIN_EFFECTIVE_IRRIGATION', 5.0)),
        # 灌溉量分档配置
        'IRRIGATION_LEVELS': [0, 5, 10, 15, 20, 25, 30, 40, 50],
        # 降雨相关阈值
        'MIN_RAIN_AMOUNT': float(os.getenv('MIN_RAIN_AMOUNT', 5.0)),
        'RAIN_FORECAST_DAYS': int(os.getenv('RAIN_FORECAST_DAYS', 3)),
        # 根系深度阈值
        'ROOT_DEPTH_THRESHOLD': float(os.getenv('ROOT_DEPTH_THRESHOLD', 0.3)),
        # 最大单次灌溉量
        'MAX_SINGLE_IRRIGATION': float(os.getenv('MAX_SINGLE_IRRIGATION', 30.0)),
        # 数据验证范围
        'HUMIDITY_MIN_RANGE': float(os.getenv('HUMIDITY_MIN_RANGE', 0.0)),
        'HUMIDITY_MAX_RANGE': float(os.getenv('HUMIDITY_MAX_RANGE', 100.0)),
        # 最小预测数据天数
        'MIN_FORECAST_DATA_DAYS': int(os.getenv('MIN_FORECAST_DATA_DAYS', 3))
    }
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
        'root_depth': float(os.getenv('DEFAULT_ROOT_DEPTH_COEFF', 1.0)),
        'growth_stage': float(os.getenv('DEFAULT_GROWTH_STAGE_COEFF', 1.0)),
        'irrigation_threshold': float(os.getenv('DEFAULT_IRRIGATION_THRESHOLD_COEFF', 0.6))
    }

    # 告警配置
    ALERT_CONFIG = {
        'HUMIDITY_LOW_THRESHOLD': float(os.getenv('HUMIDITY_LOW_THRESHOLD', 0.3)),
        'HUMIDITY_HIGH_THRESHOLD': float(os.getenv('HUMIDITY_HIGH_THRESHOLD', 0.8)),
        'ALERT_EMAIL_RECIPIENTS': os.getenv('ALERT_EMAIL_RECIPIENTS', '').split(',')
    }

    # 墒情传感器默认值配置
    SOIL_SENSOR_DEFAULTS = {
        # 默认数据配置
        'DEFAULT_MAX_HUMIDITY': float(os.getenv('DEFAULT_MAX_HUMIDITY', 35.5)),
        'DEFAULT_MIN_HUMIDITY': float(os.getenv('DEFAULT_MIN_HUMIDITY', 15.2)),
        'DEFAULT_REAL_HUMIDITY': float(os.getenv('DEFAULT_REAL_HUMIDITY', 25.0)),
        'DEFAULT_SAT': float(os.getenv('DEFAULT_SAT', 35.5)),
        'DEFAULT_FC': float(os.getenv('DEFAULT_FC', 25.0)),
        'DEFAULT_PWP': float(os.getenv('DEFAULT_PWP', 15.2)),
        'DEFAULT_SOIL_DEPTH': float(os.getenv('DEFAULT_SOIL_DEPTH', 30.0)),
        'HUMIDITY_10CM_DEFAULT': float(os.getenv('HUMIDITY_10CM_DEFAULT', 15.0)),
        'HUMIDITY_20CM_DEFAULT': float(os.getenv('HUMIDITY_20CM_DEFAULT', 20.0)),
        'HUMIDITY_30CM_DEFAULT': float(os.getenv('HUMIDITY_30CM_DEFAULT', 25.0)),
        
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

    # 灌溉服务默认土壤参数配置
    DEFAULT_SOIL_PARAMS = {
        'fc': float(os.getenv('DEFAULT_SOIL_FC', 25.0)),
        'sat': float(os.getenv('DEFAULT_SOIL_SAT', 35.5)),
        'pwp': float(os.getenv('DEFAULT_SOIL_PWP', 15.2)),
        'depth_cm': float(os.getenv('DEFAULT_SOIL_DEPTH_CM', 30.0))
    }
    
    # API配置
    API_CONFIG = {
        'SOIL_API_URL': os.getenv('SOIL_API_URL', 'https://iland.zoomlion.com/open-sharing-platform/zlapi/'),
        'SOIL_API_KEY': os.getenv('SOIL_API_KEY', 'dWCkcdbdSeMqHyMQmZruWzwHR30cspVH')
    }

    # 墒情传感器数据查询范围
    DATA_QUERY_RANGES = {
        # 传感器极值/SAT/PWP数据查询日期设定
        'MOISTURE_DATA_START_YEAR': int(os.getenv('MOISTURE_DATA_START_YEAR', 2024)),
        'MOISTURE_DATA_START_MONTH': int(os.getenv('MOISTURE_DATA_START_MONTH', 7)),
        'MOISTURE_DATA_START_DAY': int(os.getenv('MOISTURE_DATA_START_DAY', 1)),
        # 传感器FC数据查询日期设定
        'FC_DATA_START_YEAR': int(os.getenv('FC_DATA_START_YEAR', 2024)),
        'FC_DATA_START_MONTH': int(os.getenv('FC_DATA_START_MONTH', 10)),
        'FC_DATA_START_DAY': int(os.getenv('FC_DATA_START_DAY', 15)),
        'FC_DATA_END_YEAR': int(os.getenv('FC_DATA_END_YEAR', 2024)),
        'FC_DATA_END_MONTH': int(os.getenv('FC_DATA_END_MONTH', 10)),
        'FC_DATA_END_DAY': int(os.getenv('FC_DATA_END_DAY', 31)),
    }
    
    # AquaCrop模型模拟配置
    AQUACROP_CONFIG = {
        # 模拟时间范围
        'SIM_START_TIME': os.getenv('AQUACROP_SIM_START_TIME', '2025/10/1'),
        'SIM_END_TIME': os.getenv('AQUACROP_SIM_END_TIME', '2026/6/1'),
        
        # 作物参数
        'CROP_NAME': os.getenv('AQUACROP_CROP_NAME', 'Wheat'),
        'PLANTING_DATE': os.getenv('AQUACROP_PLANTING_DATE', '10/15'),
        
        # 土壤基本物理参数
        'SOIL_TEXTURE':os.getenv('AQUACROP_SOIL_TEXTURE', 'custom'),
        'SOIL_KSAT': float(os.getenv('AQUACROP_SOIL_KSAT', 590)),
        'SOIL_PENETRABILITY': float(os.getenv('AQUACROP_SOIL_PENETRABILITY', 100)),
        # 土壤水力特征参数（备用）
        'SOIL_FIELD_CAPACITY': float(os.getenv('AQUACROP_SOIL_FC', 0.287)),
        'SOIL_WILTING_POINT': float(os.getenv('AQUACROP_SOIL_WP', 0.239)),
        'SOIL_SATURATION': float(os.getenv('AQUACROP_SOIL_SAT', 0.4058)),
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
        'LATITUDE': float(os.getenv('AQUACROP_LATITUDE', 35.0)),  # 纬度，用于FAO-56计算
        'ELEVATION': float(os.getenv('AQUACROP_ELEVATION', 100.0)),  # 海拔，用于FAO-56计算
        
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
        'wheat_season_start_month': int(os.getenv('WHEAT_START_MONTH', 10)),
        'wheat_season_start_day': int(os.getenv('WHEAT_START_DAY', 1)),
        'wheat_season_end_month': int(os.getenv('WHEAT_END_MONTH', 6)),
        'wheat_season_end_day': int(os.getenv('WHEAT_END_DAY', 1)),
        
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