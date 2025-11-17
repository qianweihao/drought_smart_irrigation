#传感器模块
"""
### 1. SOIL_SENSOR_DEFAULTS 配置组
默认数据配置：
- DEFAULT_MAX_HUMIDITY : 默认最大湿度值 (35.5)
- DEFAULT_MIN_HUMIDITY : 默认最小湿度值 (15.2)
- DEFAULT_REAL_HUMIDITY : 默认实时湿度值 (25.0)
- DEFAULT_SAT : 默认饱和含水量 (35.5)
- DEFAULT_FC : 默认田间持水量 (25.0)
- DEFAULT_PWP : 默认凋萎点 (15.2)
- DEFAULT_SOIL_DEPTH : 默认土壤深度 (30.0)
- HUMIDITY_10CM_DEFAULT : 10cm深度默认湿度 (15.0)
- HUMIDITY_20CM_DEFAULT : 20cm深度默认湿度 (20.0)
- HUMIDITY_30CM_DEFAULT : 30cm深度默认湿度 (25.0)
API配置:
- API_TIMEOUT : API超时时间 (15秒)
- API_MAX_RETRIES : API最大重试次数 (3次)
- API_MAX_WAIT_TIME : API最大等待时间 (10秒)
- HEALTH_CHECK_TIMEOUT : 健康检查超时时间 (5秒)
熔断器配置：
- CIRCUIT_BREAKER_FAILURE_THRESHOLD : 熔断器失败阈值 (5次)
- CIRCUIT_BREAKER_RECOVERY_TIMEOUT : 熔断器恢复超时时间 (60秒)
重试策略配置：
- RETRY_TOTAL : 重试总次数 (2次)
- RETRY_BACKOFF_FACTOR : 重试退避因子 (1.0)

### 2. DATA_QUERY_RANGES 配置组
用于设置数据查询的日期范围：
传感器极值/SAT/PWP数据查询日期:
- MOISTURE_DATA_START_YEAR : 2024
- MOISTURE_DATA_START_MONTH : 7
- MOISTURE_DATA_START_DAY : 1
传感器FC数据查询日期:
- FC_DATA_START_YEAR : 2024
- FC_DATA_START_MONTH : 10
- FC_DATA_START_DAY : 15
- FC_DATA_END_YEAR : 2024
- FC_DATA_END_MONTH : 10
- FC_DATA_END_DAY : 31
### 3. IRRIGATION_CONFIG 配置组
在获取实时湿度数据时使用：
- SOIL_DEPTH_CM : 土壤深度配置 (30cm)，用于选择对应深度的湿度字段
"""
import os
import sys
import json
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from loguru import logger
import warnings
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

# ==================== 1. SoilSensorConfig（配置） ====================

class SoilSensorConfig:
    """土壤传感器配置类"""
    # API端点常量
    DAILY_AVG_ENDPOINT = "/zlapi/soilTestingApi/v1/getDailyAvg"
    LAST_SOIL_ENDPOINT = "/zlapi/irrigationApi/v2/getSoilLast"
    # 默认配置
    DEFAULT_BASE_URL = "https://iland.zoomlion.com/open-sharing-platform"
    DEFAULT_API_KEY = "dWCkcdbdSeMqHyMQmZruWzwHR30cspVH"
    
    def __init__(self):
        self.base_url = self.DEFAULT_BASE_URL
        self.api_key = self.DEFAULT_API_KEY
        try:
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
            from config import Config
            self.soil_defaults = Config.SOIL_SENSOR_DEFAULTS
            self.DATA_QUERY_RANGES = Config.DATA_QUERY_RANGES
            logger.info("成功从配置文件加载土壤传感器默认值")
        except ImportError as e:
            logger.error(f"无法导入配置文件: {e}，配置文件是必需的")
            raise ImportError(f"配置文件导入失败,请检查config.py文件: {e}")
        logger.info("成功加载土壤传感器配置")

config = SoilSensorConfig()
# ==================== 2. APIClient（请求 + 重试） ====================
class APIClient:
    """API客户端,负责处理所有外部API调用"""
    def __init__(self, base_url=None, api_key=None):
        self.base_url = (base_url or config.DEFAULT_BASE_URL).rstrip('/')
        self.session = requests.Session()
        defaults = config.soil_defaults
        self.circuit_breaker = {
            'failure_count': 0,
            'last_failure_time': None,
            'state': 'closed',  
            'failure_threshold': defaults['CIRCUIT_BREAKER_FAILURE_THRESHOLD'],
            'recovery_timeout': defaults['CIRCUIT_BREAKER_RECOVERY_TIMEOUT']  # 秒
        }
        retry_strategy = Retry(
            total=defaults['RETRY_TOTAL'],  # 减少重试次数
            backoff_factor=defaults['RETRY_BACKOFF_FACTOR'],  # 增加退避时间
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("POST",)
        )
        # 挂载适配器
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': api_key or config.DEFAULT_API_KEY
        }
    
    def _check_circuit_breaker(self):
        """检查熔断器状态"""
        cb = self.circuit_breaker
        
        if cb['state'] == 'open':
            # 检查是否可以尝试恢复
            if cb['last_failure_time'] and \
               time.time() - cb['last_failure_time'] > cb['recovery_timeout']:
                cb['state'] = 'half_open'
                logger.info("熔断器进入半开状态，尝试恢复")
                return True
            else:
                logger.warning("熔断器处于开启状态，跳过API调用")
                return False
        
        return True
    
    def _record_success(self):
        """记录成功调用"""
        cb = self.circuit_breaker
        if cb['state'] == 'half_open':
            cb['state'] = 'closed'
            cb['failure_count'] = 0
            logger.info("熔断器恢复到关闭状态")
        elif cb['state'] == 'closed':
            cb['failure_count'] = max(0, cb['failure_count'] - 1)
    
    def _record_failure(self):
        """记录失败调用"""
        cb = self.circuit_breaker
        cb['failure_count'] += 1
        cb['last_failure_time'] = time.time()
        
        if cb['failure_count'] >= cb['failure_threshold']:
            cb['state'] = 'open'
            logger.error(f"熔断器开启，连续失败{cb['failure_count']}次")
    
    def make_request(self, endpoint, data, timeout=None, max_retries=None):
        """统一的API请求方法，带有熔断器和智能重试"""
        
        # 从配置获取默认值
        defaults = config.soil_defaults
        if timeout is None:
            timeout = defaults['API_TIMEOUT']
        if max_retries is None:
            max_retries = defaults['API_MAX_RETRIES']
        
        # 检查熔断器
        if not self._check_circuit_breaker():
            return None
        
        # 确保data是字典类型，并自动添加token参数
        if data is None:
            data = {}
        elif not isinstance(data, dict):
            data = dict(data) if hasattr(data, 'items') else {}
        
        # 自动添加token参数到POST数据中
        if 'token' not in data:
            # 从Authorization header中提取token，或使用默认API key
            auth_header = self.headers.get('Authorization', config.DEFAULT_API_KEY)
            data['token'] = auth_header
            logger.debug(f"自动添加token参数到POST数据中")
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        for attempt in range(max_retries):
            try:
                logger.info(f"调用API (尝试 {attempt + 1}/{max_retries}): url={url}")
                
                # 指数退避
                if attempt > 0:
                    max_wait = defaults['API_MAX_WAIT_TIME']
                    wait_time = min(2 ** attempt, max_wait)  # 最大等待时间从配置获取
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                
                response = self.session.post(url, headers=self.headers, data=data, timeout=timeout)
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        self._record_success()
                        logger.info(f"API调用成功: {endpoint}")
                        return result
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON解析失败: {str(e)}")
                        self._record_failure()
                        if attempt == max_retries - 1:
                            return None
                        continue
                
                elif response.status_code in (429, 500, 502, 503, 504):
                    logger.warning(f"API返回可重试错误: HTTP {response.status_code}")
                    self._record_failure()
                    if attempt == max_retries - 1:
                        logger.error(f"API请求最终失败: HTTP {response.status_code}")
                        return None
                    continue
                
                else:
                    logger.error(f"API请求失败: HTTP {response.status_code}")
                    self._record_failure()
                    return None
                    
            except requests.exceptions.Timeout:
                logger.warning(f"API请求超时 (尝试 {attempt + 1}/{max_retries})")
                self._record_failure()
                if attempt == max_retries - 1:
                    logger.error("API请求最终超时")
                    return None
                continue
                
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"连接错误 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                self._record_failure()
                if attempt == max_retries - 1:
                    logger.error(f"API连接最终失败: {str(e)}")
                    return None
                continue
                
            except requests.exceptions.RequestException as e:
                logger.error(f"API请求异常: {str(e)}")
                self._record_failure()
                return None
        
        return None
    
    def health_check(self):
        """API健康检查"""
        try:
            # 使用一个轻量级的端点进行健康检查
            # 这里可以根据实际API调整
            defaults = config.soil_defaults
            health_timeout = defaults['HEALTH_CHECK_TIMEOUT']
            response = self.session.get(f"{self.base_url}/health", timeout=health_timeout)
            if response.status_code == 200:
                logger.info("API健康检查通过")
                return True
        except:
            pass
        
        logger.warning("API健康检查失败")
        return False
    
    def get_circuit_breaker_status(self):
        """获取熔断器状态"""
        cb = self.circuit_breaker
        return {
            'state': cb['state'],
            'failure_count': cb['failure_count'],
            'last_failure_time': cb['last_failure_time']
        }

# 全局API客户端实例
api_client = APIClient()
# ==================== 3. DataProcessor（日期与数据清洗） ====================

class DataProcessor:
    """数据处理器类"""
    @staticmethod
    def get_date_range(days=None):
        if days is not None:
            end_day = datetime.now().strftime('%Y-%m-%d')
            start_day = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        else:
            # 使用DATA_QUERY_RANGES中的默认日期配置
            ranges = config.DATA_QUERY_RANGES
            start_date = datetime(
                ranges['MOISTURE_DATA_START_YEAR'],
                ranges['MOISTURE_DATA_START_MONTH'],
                ranges['MOISTURE_DATA_START_DAY']
            )
            start_day = start_date.strftime('%Y-%m-%d')
            end_day = datetime.now().strftime('%Y-%m-%d')
        logger.info(f"使用配置的日期范围: {start_day} 到 {end_day}")
        return start_day, end_day

    @staticmethod
    def validate_and_process_data(data):
        if not data:
            logger.error("API返回无效数据或错误")
            return None, False
        if not isinstance(data, list) or len(data) == 0:
            logger.warning("API返回的数据列表为空")
            return None, False
        try:
            df = pd.DataFrame(data)
            
            # 如果DataFrame为空，直接返回
            if df.empty:
                logger.warning("DataFrame为空")
                return None, False
            
            # 尝试清理时间字段（如果存在）
            if 'msgTimeStr' in df.columns:
                valid_mask = df['msgTimeStr'].notna() & (df['msgTimeStr'] != '')
                df_filtered = df[valid_mask]
                # 如果过滤后还有数据，使用过滤后的数据；否则使用原始数据
                if not df_filtered.empty:
                    df = df_filtered
                    logger.debug(f"通过msgTimeStr过滤后剩余{len(df)}条记录")
                else:
                    logger.warning("msgTimeStr过滤后数据为空，使用原始数据")
            
            # 再次检查是否为空
            if df.empty:
                logger.warning("数据清洗后为空")
                return None, False
            
            logger.info(f"数据处理成功，共{len(df)}条记录")
            return df, True
        except Exception as e:
            logger.error(f"数据处理失败: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return None, False

# ==================== 4. fetch_daily_avg_df（统一拉取入口） ====================

def fetch_daily_avg_df(device_id, start_day, end_day):
    """统一的每日平均数据拉取入口"""
    data = {
        'deviceCode': device_id,
        'startDay': start_day,
        'endDay': end_day
    }
    response = api_client.make_request(config.DAILY_AVG_ENDPOINT, data)
    if response and response.get('success'):
        df, success = DataProcessor.validate_and_process_data(response.get('data', []))
        return df if success else pd.DataFrame()
    logger.warning("获取每日平均数据失败")
    return pd.DataFrame()

# ==================== 5. save_real_humidity_data（实时湿度） ====================
def save_real_humidity_data(field_id):
    """获取实时土壤湿度数据"""
    data = {'sectionID': field_id}
    default_humidity = config.soil_defaults['DEFAULT_REAL_HUMIDITY']
    try:
        response = api_client.make_request(config.LAST_SOIL_ENDPOINT, data)
        if not response or not response.get('success'):
            logger.error("获取实时湿度数据失败")
            return default_humidity, False
        df, success = DataProcessor.validate_and_process_data(response.get('data', []))
        if not success or df.empty:
            logger.warning("实时湿度数据为空，使用默认值")
            return default_humidity, False
        # 根据土壤深度选择合适的湿度字段
        from config import Config
        irrigation_config = Config.IRRIGATION_CONFIG
        soil_depth = irrigation_config.get('SOIL_DEPTH_CM', 30)
        humidity_field = f'soilHumidity{soil_depth}Value'
        
        if humidity_field in df.columns:
            real_humidity = float(df[humidity_field].iloc[-1])
            logger.info(f"获取实时土壤湿度数据 (深度{soil_depth}cm): {real_humidity}")
            return real_humidity, True
        else:
            # 如果指定深度的字段不存在，尝试使用其他可用的湿度字段
            humidity_columns = [col for col in df.columns if 'soilHumidity' in col and 'Value' in col]
            if humidity_columns:
                # 使用第一个可用的湿度字段
                humidity_field = humidity_columns[0]
                real_humidity = float(df[humidity_field].iloc[-1])
                logger.info(f"使用替代湿度字段 {humidity_field}: {real_humidity}")
                return real_humidity, True
            else:
                logger.warning("未找到任何湿度字段，使用默认值")
                return default_humidity, False
    except Exception as e:
        logger.error(f"获取实时土壤湿度数据失败: {str(e)}")
        return default_humidity, False

# ==================== 6. SAT/PWP和FC数据获取函数 ====================

def get_sat_pwp_data(device_id, field_id=None):
    """获取饱和含水量(SAT)和凋萎点(PWP)数据
    
    Args:
        device_id: 设备ID
        field_id: 田块ID（可选，用于获取田块特定的历史数据时间段）
    """
    try:
        # 获取田块特定的历史数据时间段配置
        from config import Config
        periods = Config.get_field_data_periods(field_id) if field_id else None
        
        if periods and periods['sat_pwp']['start_date']:
            # 使用田块特定的时间段
            start_day = periods['sat_pwp']['start_date']
            end_day = periods['sat_pwp']['end_date'] or datetime.now().strftime('%Y-%m-%d')
            logger.info(f"[田块 {field_id}] 获取SAT/PWP数据: 使用自定义日期范围 {start_day} 到 {end_day}")
        else:
            # 使用全局默认配置
            query_ranges = config.DATA_QUERY_RANGES
            start_date = datetime(
                query_ranges['MOISTURE_DATA_START_YEAR'],
                query_ranges['MOISTURE_DATA_START_MONTH'], 
                query_ranges['MOISTURE_DATA_START_DAY']
            )
            end_date = datetime.now()
            start_day = start_date.strftime('%Y-%m-%d')
            end_day = end_date.strftime('%Y-%m-%d')
            logger.info(f"获取饱和含水量(SAT)和凋萎点(PWP)数据: 使用默认日期范围 {start_day} 到 {end_day}")
        df = fetch_daily_avg_df(device_id, start_day, end_day)
        if df.empty:
            logger.warning("无法获取SAT/PWP历史数据,使用默认值")
            defaults = config.soil_defaults
            return defaults['DEFAULT_SAT'], defaults['DEFAULT_PWP']
        humidity_cols = [col for col in df.columns if 'humidity' in col.lower()]
        if humidity_cols:
            col = humidity_cols[0]
            sat = float(df[col].max())  #
            pwp = float(df[col].min())  
            logger.info(f"计算得到 SAT: {sat}, PWP: {pwp}")
            return sat, pwp
        else:
            logger.warning("无湿度数据,使用默认SAT/PWP值")
            defaults = config.soil_defaults
            return defaults['DEFAULT_SAT'], defaults['DEFAULT_PWP']
            
    except Exception as e:
        logger.error(f"获取SAT/PWP数据失败: {str(e)}")
        defaults = config.soil_defaults
        return defaults['DEFAULT_SAT'], defaults['DEFAULT_PWP']

def get_field_capacity_data(device_id, field_id=None):
    """获取田间持水量(FC)数据
    
    Args:
        device_id: 设备ID
        field_id: 田块ID（可选，用于获取田块特定的历史数据时间段）
    """
    try:
        # 获取田块特定的历史数据时间段配置
        from config import Config
        periods = Config.get_field_data_periods(field_id) if field_id else None
        
        if periods and periods['fc']['start_date']:
            # 使用田块特定的时间段
            start_day = periods['fc']['start_date']
            end_day = periods['fc']['end_date']
            logger.info(f"[田块 {field_id}] 获取FC数据: 使用自定义日期范围 {start_day} 到 {end_day}")
        else:
            # 使用全局默认配置
            query_ranges = config.DATA_QUERY_RANGES
            start_date = datetime(
                query_ranges['FC_DATA_START_YEAR'],
                query_ranges['FC_DATA_START_MONTH'],
                query_ranges['FC_DATA_START_DAY']
            )
            end_date = datetime(
                query_ranges['FC_DATA_END_YEAR'],
                query_ranges['FC_DATA_END_MONTH'],
                query_ranges['FC_DATA_END_DAY']
            )
            
            start_day = start_date.strftime('%Y-%m-%d')
            end_day = end_date.strftime('%Y-%m-%d')
            
            logger.info(f"获取田间持水量(FC)数据: 使用默认日期范围 {start_day} 到 {end_day}")
        
        df = fetch_daily_avg_df(device_id, start_day, end_day)
        if df.empty:
            logger.warning("无法获取FC历史数据,使用默认值")
            defaults = config.soil_defaults
            return defaults['DEFAULT_FC']
        humidity_cols = [col for col in df.columns if 'humidity' in col.lower()]
        if humidity_cols:
            col = humidity_cols[0]
            fc = float(df[col].mean()) 
            logger.info(f"计算得到 FC: {fc}")
            return fc
        else:
            logger.warning("无湿度数据,使用默认FC值")
            defaults = config.soil_defaults
            return defaults['DEFAULT_FC']
            
    except Exception as e:
        logger.error(f"获取FC数据失败: {str(e)}")
        defaults = config.soil_defaults
        return defaults['DEFAULT_FC']

# ==================== 7. get_soil_parameters（聚合指标：max/min、SAT/PWP、FC、real） ====================

def get_soil_parameters(device_id, field_id):
    """获取所有土壤参数的聚合函数"""
    logger.info(f"获取土壤参数: device_id={device_id}, field_id={field_id}")
    def _create_default_params(use_calculated=False, max_humidity=None, min_humidity=None, sat=None, fc=None, pwp=None, real_humidity=None, is_real_data=False):
        defaults = config.soil_defaults
        return {
            'max_humidity': max_humidity if use_calculated else defaults['DEFAULT_MAX_HUMIDITY'],
            'min_humidity': min_humidity if use_calculated else defaults['DEFAULT_MIN_HUMIDITY'],
            'real_humidity': real_humidity if use_calculated else defaults['DEFAULT_REAL_HUMIDITY'],
            'sat': sat if use_calculated else defaults['DEFAULT_SAT'],
            'fc': fc if use_calculated else defaults['DEFAULT_FC'],
            'pwp': pwp if use_calculated else defaults['DEFAULT_PWP'],
            'soil_depth': defaults['DEFAULT_SOIL_DEPTH'],
            'humidity_10cm': defaults['HUMIDITY_10CM_DEFAULT'],
            'humidity_20cm': defaults['HUMIDITY_20CM_DEFAULT'],
            'humidity_30cm': defaults['HUMIDITY_30CM_DEFAULT'],
            'is_real_data': is_real_data
        }
    
    try:
        # 优先检查是否有手动配置的土壤参数
        from config import Config
        manual_params = Config.get_field_soil_params(field_id)
        
        if manual_params:
            # 使用手动配置的参数
            logger.info(f"[田块 {field_id}] 使用手动配置的土壤参数: SAT={manual_params['sat']}%, FC={manual_params['fc']}%, PWP={manual_params['pwp']}%")
            sat = manual_params['sat']
            fc = manual_params['fc']
            pwp = manual_params['pwp']
        else:
            # 使用统计方法获取SAT/PWP和FC
            sat, pwp = get_sat_pwp_data(device_id, field_id)
            fc = get_field_capacity_data(device_id, field_id)
            logger.info(f"[田块 {field_id}] 使用统计方法获取的土壤参数: SAT={sat}%, FC={fc}%, PWP={pwp}%")
        
        real_humidity, real_humidity_is_real = save_real_humidity_data(field_id)
        start_day, end_day = DataProcessor.get_date_range()
        df = fetch_daily_avg_df(device_id, start_day, end_day)
        
        # 判断数据是否真实：如果SAT、FC、PWP或实时湿度中至少有一个是真实获取的，就认为数据可用
        # 检查SAT、FC、PWP是否为默认值（如果是默认值，说明获取失败）
        defaults = config.soil_defaults
        sat_is_real = sat != defaults['DEFAULT_SAT']
        fc_is_real = fc != defaults['DEFAULT_FC']
        pwp_is_real = pwp != defaults['DEFAULT_PWP']
        
        # 如果至少有一个参数是真实获取的，就认为数据可用
        is_real_data = real_humidity_is_real or sat_is_real or fc_is_real or pwp_is_real or not df.empty
        
        if df.empty:
            logger.warning("无法获取常规湿度数据,但已获取SAT/PWP/FC数据")
            params = _create_default_params(
                use_calculated=True,
                max_humidity=sat,  
                min_humidity=pwp, 
                sat=sat,
                fc=fc,
                pwp=pwp,
                real_humidity=real_humidity,
                is_real_data=is_real_data
            )
            logger.info(f"使用专门函数获取的土壤参数: {params}")
            return params
            
        humidity_cols = [col for col in df.columns if 'humidity' in col.lower()]
        if humidity_cols:
            col = humidity_cols[0] 
            max_humidity = float(df[col].max())
            min_humidity = float(df[col].min())
            
            params = _create_default_params(
                use_calculated=True,
                max_humidity=max_humidity,
                min_humidity=min_humidity,
                sat=sat,
                fc=fc,
                pwp=pwp,
                real_humidity=real_humidity,
                is_real_data=is_real_data
            )
            logger.info(f"计算得到完整土壤参数: {params}")
            return params
        else:
            params = _create_default_params(
                use_calculated=True,
                max_humidity=sat,  
                min_humidity=pwp, 
                sat=sat,
                fc=fc,
                pwp=pwp,
                real_humidity=real_humidity,
                is_real_data=is_real_data
            )
            logger.info(f"无常规湿度数据，使用专门函数获取的土壤参数: {params}")
            return params
    except Exception as e:
        logger.error(f"获取土壤参数失败: {str(e)}")
        return _create_default_params()

# ==================== 7. get_history_humidity_data（历史与平滑） ====================
def get_history_humidity_data(device_id, days=None):
    """ 获取历史湿度数据并进行平滑处理"""
    if days is None:
        defaults = config.soil_defaults
        days = defaults['DEFAULT_HISTORY_DAYS']
    logger.info(f"获取历史湿度数据: device_id={device_id}, days={days}")
    
    try:
        start_day, end_day = DataProcessor.get_date_range(days)
        df = fetch_daily_avg_df(device_id, start_day, end_day)
        if df.empty:
            logger.warning("无法获取历史数据")
            return pd.DataFrame()
        # 处理日期列，支持 msgTimeStr 或 dt 列
        if 'msgTimeStr' in df.columns:
            df['date'] = pd.to_datetime(df['msgTimeStr'], errors='coerce')
            df = df.dropna(subset=['date'])
            df = df.sort_values('date')
        elif 'dt' in df.columns:
            df['date'] = pd.to_datetime(df['dt'], errors='coerce')
            df = df.dropna(subset=['date'])
            df = df.sort_values('date')
        defaults = config.soil_defaults
        smooth_window = defaults['SMOOTH_WINDOW']
        humidity_cols = [col for col in df.columns if 'humidity' in col.lower()]
        for col in humidity_cols:
            if col in df.columns:
                df[f'{col}_smooth'] = df[col].rolling(window=smooth_window, center=True).mean()
        
        logger.info(f"获取历史湿度数据成功，共{len(df)}条记录")
        return df    
    except Exception as e:
        logger.error(f"获取历史湿度数据失败: {str(e)}")
        return pd.DataFrame()

# ==================== 8. SoilSensor（OO 封装） ====================

class SoilSensor:
    """土壤传感器类"""
    def __init__(self, device_id, field_id):
        """初始化土壤传感器"""
        self.device_id = device_id
        self.field_id = field_id
        try:
            self.use_mock = False
            logger.info("SoilSensor初始化: 使用配置文件设置")
        except ImportError as e:
            self.use_mock = False
            logger.info(f"SoilSensor初始化: 配置获取失败({str(e)}),默认使用真实API")
    
    def get_current_data(self):
        """获取当前土壤数据"""
        return get_soil_parameters(self.device_id, self.field_id)
    
    def get_history_humidity_data(self, days=None):
        """获取历史湿度数据 """
        return get_history_humidity_data(self.device_id, days)

# ==================== 兼容性函数（已弃用） ====================
def save_extremum_humidity_data(device_id):
    """已弃用函数，保持向后兼容"""
    warnings.warn("save_extremum_humidity_data已弃用,请使用get_soil_parameters", DeprecationWarning, stacklevel=2)
    params = get_soil_parameters(device_id, "default_field")
    return params['max_humidity'], params['min_humidity'], params['sat'], params['pwp']

def get_current_data():
    """已弃用函数，保持向后兼容"""
    warnings.warn("get_current_data已弃用,建议使用SoilSensor类或get_soil_parameters()函数", DeprecationWarning, stacklevel=2)
    return get_soil_parameters("default_device", "default_field")

# ==================== 模块测试代码 ====================
if __name__ == "__main__":
    logger.info("开始测试土壤传感器模块")
    sensor = SoilSensor('test_device', 'test_field')
    current_data = sensor.get_current_data()
    logger.info(f"当前数据: {current_data}")
    history_data = sensor.get_history_humidity_data()
    logger.info(f"历史数据条数: {len(history_data)}")
    logger.info("土壤传感器模块测试完成")