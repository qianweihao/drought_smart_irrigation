"""
### 1. IRRIGATION_CONFIG 配置项
- HUMIDITY_MIN_RANGE 和 HUMIDITY_MAX_RANGE ：用于验证湿度输入参数的有效范围
- SOIL_DEPTH_CM ：土壤深度（厘米），用于土壤湿度计算的转换因子
- ROOT_DEPTH_THRESHOLD :根系深度阈值,用于判断根系深度系数(0.3米)
- DEFAULT_DEVICE_ID 和 DEFAULT_FIELD_ID :默认设备ID和地块ID,用于获取传感器数据
- IRRIGATION_THRESHOLD ：基础灌溉阈值，与生育阶段系数相乘得到实际阈值
- MIN_EFFECTIVE_IRRIGATION :最小有效灌溉量(5.0mm)
- MAX_SINGLE_IRRIGATION :单次最大灌溉量(30.0mm)
- RAIN_FORECAST_DAYS :降雨预报考虑天数(3天)
- MIN_RAIN_AMOUNT :最小有效降雨量(5.0mm)
- IRRIGATION_LEVELS ：灌溉量分档列表 [0, 5, 10, 15, 20, 25, 30, 40, 50]
- MAX_FORECAST_DAYS :最大预报天数(7天)
- MIN_FORECAST_DATA_DAYS :最小预报数据天数(3天)
### 2. DEFAULT_SOIL_PARAMS 配置项
- fc ：田间持水量百分比，作为传感器数据的默认值
- sat ：饱和含水量百分比，作为传感器数据的默认值
- pwp ：萎蔫点含水量百分比，作为传感器数据的默认值
- depth_cm ：默认土壤深度（厘米）
### 3. DEFAULT_COEFFICIENTS 配置项
- root_depth ：默认根系深度系数，当无法从模型文件获取时使用
- growth_stage ：默认生育阶段系数，当无法确定当前生育阶段时使用
- irrigation_threshold ：默认灌溉阈值系数
### 4. FILE_PATHS 配置项
- model_output ：模型输出文件路径，用于读取根系深度和蒸散量数据
- growth_stages ：生育阶段文件路径，用于确定当前生育阶段
### 5. GROWTH_STAGE_COEFFICIENTS 配置项
- 生育阶段系数字典，根据当前生育阶段获取对应的系数值
"""
import os
import pandas as pd
from datetime import datetime
import sys
from functools import lru_cache

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(project_root)

from src.utils.logger import logger
from src.models.fao_model import FAOModel
from config import Config

class IrrigationService:
    """智能灌溉服务类
    提供旱作灌溉决策功能,包括土壤湿度计算、
    根系深度系数获取、生育阶段系数计算等核心功能。
    """
    
    def __init__(self, config):
        self.config = config
        self.fao_model = FAOModel(config)
        self._last_model_run = None
        self._cache_timestamp = None
        
        # 验证配置
        self._validate_config()
        
    def _validate_config(self):
        """验证配置的有效性"""
        required_configs = ['IRRIGATION_CONFIG', 'GROWTH_STAGE_COEFFICIENTS']
        for config_name in required_configs:
            if not hasattr(self.config, config_name):
                logger.warning(f"配置项 {config_name} 不存在，将使用默认值")
                
    # 注意：_validate_humidity_inputs 函数已废弃
    # 新的函数签名不再需要 max_humidity 和 min_humidity 参数
    # 验证逻辑已直接集成到 calculate_soil_humidity_differences 中
        
    def _safe_get_coefficient(self, func_name, *args, default_value=1.0):
        """安全获取系数的统一方法
        
        Args:
            func_name (str): 函数名称
            *args: 函数参数
            default_value (float): 默认值
            
        Returns:
            float: 系数值
        """
        try:
            func = getattr(self, func_name)
            return func(*args)
        except Exception as e:
            logger.warning(f"{func_name}获取失败，使用默认值{default_value}: {str(e)}")
            return default_value
            
    def _get_file_path(self, file_key):
        """获取文件路径
        
        Args:
            file_key (str): 文件键名
            
        Returns:
            str: 完整文件路径
        """
        relative_path = Config.FILE_PATHS.get(file_key)
        if not relative_path:
            raise ValueError(f"未知的文件键: {file_key}")
        return os.path.join(project_root, relative_path)
        

        
    @lru_cache(maxsize=32)
    def _get_cached_sensor_data(self, device_id, field_id, hour_timestamp):
        """带缓存的传感器数据获取（按小时粒度缓存）
        
        Args:
            device_id (str): 设备ID
            field_id (str): 地块ID
            hour_timestamp (str): 小时粒度时间戳，用于缓存过期控制
            
        Returns:
            dict: 传感器数据
        """
        try:
            from src.devices.soil_sensor import SoilSensor
            soil_sensor = SoilSensor(device_id=device_id, field_id=field_id)
            return soil_sensor.get_current_data()
        except Exception as e:
            logger.warning(f"获取传感器数据失败，使用默认值: {str(e)}")
            return {
                'fc': Config.DEFAULT_SOIL_PARAMS['fc'],
                'sat': Config.DEFAULT_SOIL_PARAMS['sat'], 
                'pwp': Config.DEFAULT_SOIL_PARAMS['pwp']
            }
        
    def get_root_depth_coefficient(self, out_file=None):
        """从模型输出文件中读取根系深度系数
        
        Args:
            out_file (str, optional): 输出文件路径,如果为None则使用默认路径
            
        Returns:
            float: 根系深度系数 (0.5 或 1.0)
        """
        try:
            # 使用默认文件路径或传入的路径
            if out_file is None:
                file_path = self._get_file_path('model_output')
            else:
                file_path = out_file if os.path.isabs(out_file) else os.path.join(project_root, out_file)
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                logger.warning(f"模型输出文件不存在: {file_path}")
                return Config.DEFAULT_COEFFICIENTS['root_depth']
            
            # 读取CSV文件
            df = pd.read_csv(file_path, delim_whitespace=True, skiprows=10)
            
            # 检查是否有数据和必要的列
            if df.empty:
                logger.warning(f"模型输出文件为空: {file_path}")
                return Config.DEFAULT_COEFFICIENTS['root_depth']
                
            required_columns = ['Date', 'Zr']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                logger.warning(f"模型输出文件缺少必要列: {missing_columns}")
                return Config.DEFAULT_COEFFICIENTS['root_depth']
            
            # 获取当前日期
            current_date = datetime.now()
            
            # 将日期列转换为datetime类型
            df['Date'] = pd.to_datetime(df['Date'], format='%m/%d/%y', errors='coerce')
            
            # 过滤掉无效日期
            df = df.dropna(subset=['Date'])
            if df.empty:
                logger.warning("模型输出文件中没有有效的日期数据")
                return Config.DEFAULT_COEFFICIENTS['root_depth']
            
            now = pd.to_datetime(current_date.date())
            today_data = df[df['Date'] == now]
            
            if today_data.empty:
                logger.warning(f"无法找到当前日期({now.strftime('%Y-%m-%d')})的数据，使用最接近的日期")
                df['date_diff'] = abs((df['Date'] - now).dt.days)
                closest_row = df.loc[df['date_diff'].idxmin()]
            else:
                closest_row = today_data.iloc[0]
                
            # 获取根系深度
            root_depth = closest_row['Zr'] if 'Zr' in closest_row else 0.2
            
            # 验证根系深度值
            if pd.isna(root_depth) or not isinstance(root_depth, (int, float)):
                logger.warning(f"根系深度值无效: {root_depth}")
                return Config.DEFAULT_COEFFICIENTS['root_depth']
            
            # 根据根系深度计算系数
            irrigation_config = getattr(self.config, 'IRRIGATION_CONFIG', {})
            threshold = irrigation_config.get('ROOT_DEPTH_THRESHOLD', 0.3)
            coefficient = 0.5 if root_depth < threshold else 1.0
            
            logger.info(f"当前根系深度为{root_depth}m,系数为{coefficient}")
            return coefficient
                
        except Exception as e:
            logger.error(f"获取根系深度系数时出错: {str(e)}")
            return Config.DEFAULT_COEFFICIENTS['root_depth']  
    
    def get_growth_stage_coefficient(self):
        """获取生育阶段系数
        Returns:
            float: 生育阶段系数
        """
        try:
            # 使用统一的文件路径获取方法
            growth_stages_file = self._get_file_path('growth_stages')
            
            if not os.path.exists(growth_stages_file):
                logger.warning(f"生育阶段文件不存在: {growth_stages_file},使用默认系数")
                return Config.DEFAULT_COEFFICIENTS['growth_stage']
                
            growth_stages_df = pd.read_csv(growth_stages_file)
            if growth_stages_df.empty:
                logger.warning("生育阶段文件为空,使用默认系数")
                return Config.DEFAULT_COEFFICIENTS['growth_stage']
                
            # 检查必要的列是否存在
            required_columns = ['开始日期', '结束日期', '阶段']
            missing_columns = [col for col in required_columns if col not in growth_stages_df.columns]
            if missing_columns:
                logger.warning(f"生育阶段文件缺少必要列: {missing_columns}")
                return Config.DEFAULT_COEFFICIENTS['growth_stage']
                
            growth_stages_df['开始日期'] = pd.to_datetime(growth_stages_df['开始日期'], errors='coerce')
            growth_stages_df['结束日期'] = pd.to_datetime(growth_stages_df['结束日期'], errors='coerce')
            
            # 过滤掉无效日期
            growth_stages_df = growth_stages_df.dropna(subset=['开始日期', '结束日期'])
            if growth_stages_df.empty:
                logger.warning("生育阶段文件中没有有效的日期数据")
                return Config.DEFAULT_COEFFICIENTS['growth_stage']
                
            now = datetime.now().date()
            current_stage = None
            for _, stage in growth_stages_df.iterrows():
                start_date = stage['开始日期'].date()
                end_date = stage['结束日期'].date()
                
                if start_date <= now <= end_date:
                    current_stage = stage['阶段']
                    break
                    
            # 安全获取生育阶段系数
            if hasattr(self.config, 'GROWTH_STAGE_COEFFICIENTS'):
                stage_coefficients = self.config.GROWTH_STAGE_COEFFICIENTS
            else:
                logger.warning("配置中缺少GROWTH_STAGE_COEFFICIENTS，使用默认值")
                return Config.DEFAULT_COEFFICIENTS['growth_stage']
                
            if current_stage and current_stage in stage_coefficients:
                coefficient = stage_coefficients[current_stage]
                logger.info(f"当前生育阶段为：{current_stage}，应用系数{coefficient}")
                return coefficient
            else:
                logger.warning(f"无法确定当前生育阶段或找不到对应系数,使用默认系数")
                return Config.DEFAULT_COEFFICIENTS['growth_stage']
                
        except Exception as e:
            logger.error(f"获取生育阶段系数时出错: {str(e)}")
            return Config.DEFAULT_COEFFICIENTS['growth_stage']  
        
    def calculate_soil_humidity_differences(self, field_id, device_id, real_humidity):
        """计算土壤湿度指标（从传感器获取SAT/FC/PWP数据）
        
        Args:
            field_id (str): 田块ID，用于获取田块特定的传感器数据
            device_id (str): 设备ID，用于获取设备数据
            real_humidity (float): 实际土壤湿度 (%)
            
        Returns:
            tuple: (SAT(mm), FC(mm), PWP(mm), diff_max_real_mm, diff_min_real_mm, diff_com_real_mm)
            - SAT: 饱和含水量(mm)
            - FC: 田间持水量(mm) 
            - PWP: 萎蔫点含水量(mm)
            - diff_max_real_mm: 饱和含水量与实际湿度差值(mm)
            - diff_min_real_mm: 实际湿度与萎蔫点差值(mm)
            - diff_com_real_mm: 田间持水量与实际湿度差值(mm)
        
        Note:
            SAT、FC、PWP 值直接从传感器获取（根据field_id的历史数据统计）
            不再接受 max_humidity 和 min_humidity 参数，避免参数混淆
        """
        try:
            # 验证实际湿度参数 - 首先检查是否为 None
            if real_humidity is None:
                raise ValueError(f"[田块 {field_id}] real_humidity 不能为 None")
            
            # 检查参数类型
            if not isinstance(real_humidity, (int, float)):
                raise ValueError(f"[田块 {field_id}] real_humidity 必须是数值类型，当前值: {real_humidity} (类型: {type(real_humidity).__name__})")
            
            # 验证数值范围
            irrigation_config = getattr(self.config, 'IRRIGATION_CONFIG', {})
            min_range = irrigation_config.get('HUMIDITY_MIN_RANGE', 0.0)
            max_range = irrigation_config.get('HUMIDITY_MAX_RANGE', 100.0)
            
            if not (min_range <= real_humidity <= max_range):
                logger.warning(f"[田块 {field_id}] 实际湿度 {real_humidity}% 超出有效范围 [{min_range}, {max_range}]")
                real_humidity = max(min_range, min(real_humidity, max_range))
            
            logger.info(f"[田块 {field_id}] 计算土壤湿度差异: real_humidity={real_humidity}%")
            
            # 获取配置参数
            soil_depth = irrigation_config.get('SOIL_DEPTH_CM', Config.DEFAULT_SOIL_PARAMS['depth_cm'])
            
            # 安全获取系数
            out_file = self._get_file_path('model_output')
            root_depth_coefficient = self._safe_get_coefficient(
                'get_root_depth_coefficient', out_file,
                default_value=Config.DEFAULT_COEFFICIENTS['root_depth']
            )
            
            growth_stage_coefficient = self._safe_get_coefficient(
                'get_growth_stage_coefficient',
                default_value=Config.DEFAULT_COEFFICIENTS['growth_stage']
            )
            
            # 从传感器获取田块特定的SAT/FC/PWP数据（根据田块的历史数据统计得出）
            hour_timestamp = datetime.now().strftime('%Y-%m-%d-%H')
            sensor_data = self._get_cached_sensor_data(device_id, field_id, hour_timestamp)
            
            # 获取传感器统计的土壤参数（百分比）- 确保不为 None
            sat_percent = sensor_data.get('sat') or Config.DEFAULT_SOIL_PARAMS['sat']
            fc_percent = sensor_data.get('fc') or Config.DEFAULT_SOIL_PARAMS['fc']
            pwp_percent = sensor_data.get('pwp') or Config.DEFAULT_SOIL_PARAMS['pwp']
            
            # 确保是数值类型
            try:
                sat_percent = float(sat_percent) if sat_percent is not None else Config.DEFAULT_SOIL_PARAMS['sat']
                fc_percent = float(fc_percent) if fc_percent is not None else Config.DEFAULT_SOIL_PARAMS['fc']
                pwp_percent = float(pwp_percent) if pwp_percent is not None else Config.DEFAULT_SOIL_PARAMS['pwp']
            except (ValueError, TypeError) as e:
                logger.warning(f"[田块 {field_id}] 传感器参数类型转换失败: {e}，使用默认值")
                sat_percent = Config.DEFAULT_SOIL_PARAMS['sat']
                fc_percent = Config.DEFAULT_SOIL_PARAMS['fc']
                pwp_percent = Config.DEFAULT_SOIL_PARAMS['pwp']
            
            logger.info(f"[田块 {field_id}] 传感器土壤参数: SAT={sat_percent}%, FC={fc_percent}%, PWP={pwp_percent}%")
            
            # 计算转换因子
            conversion_factor = soil_depth / 10 * root_depth_coefficient * growth_stage_coefficient
            
            # 计算土壤参数 (mm)
            SAT = sat_percent * conversion_factor
            FC = fc_percent * conversion_factor  
            PWP = pwp_percent * conversion_factor
            
            # 计算湿度差异 (mm)
            diff_max_real_mm = (sat_percent - real_humidity) * conversion_factor  # 蓄水潜力
            diff_min_real_mm = (real_humidity - pwp_percent) * conversion_factor  # 有效储水量
            diff_com_real_mm = (fc_percent - real_humidity) * conversion_factor    # 相对田间持水量的差异
            
            logger.info(f"[田块 {field_id}] 土壤湿度计算结果: SAT={SAT:.2f}mm, FC={FC:.2f}mm, PWP={PWP:.2f}mm")
            logger.info(f"[田块 {field_id}] 湿度差异: diff_min_real={diff_min_real_mm:.2f}mm, diff_com_real={diff_com_real_mm:.2f}mm")
            logger.info(f"[田块 {field_id}] 应用系数: 根系深度={root_depth_coefficient}, 生育阶段={growth_stage_coefficient}")
            
            return SAT, FC, PWP, diff_max_real_mm, diff_min_real_mm, diff_com_real_mm
            
        except Exception as e:
            logger.error(f"[田块 {field_id}] 计算土壤湿度差异时出错: {str(e)}")
            raise
            
    def _load_and_validate_forecast_data(self, out_file):
        """加载并验证预测数据
        
        Args:
            out_file (str): 模型输出文件路径
            
        Returns:
            tuple: (future_data, current_date)
        """
        if not os.path.exists(out_file):
            raise FileNotFoundError(f"模型输出文件不存在: {out_file}")
            
        df = pd.read_csv(out_file, delim_whitespace=True, skiprows=10)
        if df.empty:
            raise ValueError("模型输出文件为空")
            
        # 验证必要的列
        required_columns = ['Date', 'ETc', 'Rain']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"模型输出文件缺少必要列: {missing_columns}")
            
        df['Date'] = pd.to_datetime(df['Date'], format='%m/%d/%y', errors='coerce')
        df = df.dropna(subset=['Date'])
        
        if df.empty:
            raise ValueError("模型输出文件中没有有效的日期数据")
            
        now = pd.to_datetime(datetime.now().date())
        
        # 获取预测天数和数据
        max_forecast_days = getattr(self.config, 'IRRIGATION_CONFIG', {}).get('MAX_FORECAST_DAYS', 7)
        future_data = df[
            (df['Date'] >= now) & 
            (df['Date'] <= (now + pd.to_timedelta(f'{max_forecast_days} days')))
        ].copy()
        
        # 确保数据按日期排序并处理NaN值
        future_data = future_data.sort_values('Date').copy()
        future_data['ETc'] = future_data['ETc'].fillna(0)
        future_data['Rain'] = pd.to_numeric(future_data['Rain'], errors='coerce').fillna(0)
        
        # 检查数据量是否足够
        irrigation_config = getattr(self.config, 'IRRIGATION_CONFIG', {})
        min_days = irrigation_config.get('MIN_FORECAST_DATA_DAYS', 3)
        if len(future_data) < min_days:
            raise ValueError(f"没有足够的未来数据用于决策，当前仅有{len(future_data)}天，至少需要{min_days}天")
            
        # 计算累积蒸散量
        future_data['Cumulative_ETcadj'] = future_data['ETc'].cumsum()
        
        return future_data, now
        
    def _analyze_rainfall(self, future_data):
        """分析降雨情况
        
        Args:
            future_data (DataFrame): 未来天气数据
            
        Returns:
            tuple: (has_rain, first_rain_day, first_rain_amount)
        """
        has_rain = (future_data["Rain"] > 0).any()
        first_rain_day = None
        first_rain_amount = 0
        
        if has_rain:
            rain_days = future_data[future_data['Rain'] > 0]
            if not rain_days.empty:
                first_rain_day = rain_days.iloc[0]['Date']
                first_rain_amount = rain_days.iloc[0]['Rain']
                
        return has_rain, first_rain_day, first_rain_amount
        

    def get_irrigation_decision(self, out_file, diff_min_real_mm, diff_com_real_mm):
        """获取灌溉决策
        
        Args:
            out_file (str): 模型输出文件路径
            diff_min_real_mm (float): 实际与最小湿度差值(mm)
            diff_com_real_mm (float): 田间持水量与实际湿度差值(mm)
            
        Returns:
            tuple: (date, irrigation_value, message)
        """
        try:
            # 加载和验证预测数据
            future_data, now = self._load_and_validate_forecast_data(out_file)
            
            # 获取配置
            irrigation_config = getattr(self.config, 'IRRIGATION_CONFIG', {})
            
            # 获取生育阶段系数和灌溉阈值
            growth_stage_coeff = self._safe_get_coefficient(
                'get_growth_stage_coefficient',
                default_value=Config.DEFAULT_COEFFICIENTS['growth_stage']
            )
            
            base_threshold = irrigation_config.get('IRRIGATION_THRESHOLD', Config.DEFAULT_COEFFICIENTS['irrigation_threshold'])
            irrigation_threshold = base_threshold * growth_stage_coeff
            
            # 获取第三天的累积蒸散量 - 使用更稳健的方法
            third_idx = min(2, len(future_data) - 1)  # 第三天或最后一天数据
            third_day_etcadj = future_data.iloc[third_idx]['Cumulative_ETcadj']
            
            # 获取最小有效灌溉量
            min_effective_irrigation = irrigation_config.get('MIN_EFFECTIVE_IRRIGATION', 5.0)
            
            # 检查临界情况（土壤水分低于萎蔫点）
            if diff_min_real_mm <= 0:
                # 土壤水分低于萎蔫点，需要立即灌溉
                max_irrigation = irrigation_config.get('MAX_SINGLE_IRRIGATION', 30.0)
                irrigation_value = min(diff_com_real_mm, max_irrigation) 
                irrigation_value = self._quantize_irrigation(irrigation_value)
                return now, irrigation_value, "土壤水分已达临界水平，立即灌溉"
                
            # 检查水分是否充足
            if third_day_etcadj <= diff_min_real_mm * irrigation_threshold:
                logger.info(f"[NO_IRRIGATION] 水分充足 - third_day_etcadj={third_day_etcadj:.2f}, "
                           f"available_to_pwp={diff_min_real_mm:.2f}, thresh={irrigation_threshold:.3f}")
                return now, 0, "水分充足，今日不灌溉"
            
            # 分析降雨情况
            has_rain, first_rain_day, first_rain_amount = self._analyze_rainfall(future_data)
            
            # 计算距离降雨的天数
            days_to_rain = None
            if first_rain_day:
                days_to_rain = (first_rain_day - now).days
            
            # 基于降雨的决策
            # 分析降雨情况
            rain_forecast_days = irrigation_config.get('RAIN_FORECAST_DAYS', 3)
            min_rain_amount = irrigation_config.get('MIN_RAIN_AMOUNT', 5.0)
            
            if has_rain:
                # 分析降雨时间和雨量
                days_to_rain = (first_rain_day - now).days if first_rain_day else 7
                
                # 降雨在配置天数以内且雨量充足
                if days_to_rain <= rain_forecast_days and first_rain_amount >= min_rain_amount:
                    return now, 0, f"未来{days_to_rain}天内有{first_rain_amount:.1f}mm降雨,延迟灌溉"
                    
                # 降雨在三天后，需要判断是否需要部分灌溉
                three_days_from_now = now + pd.to_timedelta('2 days')
                if first_rain_day and first_rain_day > three_days_from_now:
                    irrigation_value = third_day_etcadj - diff_min_real_mm * irrigation_threshold
                    if irrigation_value > min_effective_irrigation:
                        irrigation_value = min(irrigation_value, irrigation_config.get('MAX_SINGLE_IRRIGATION', 30.0))
                        irrigation_value = self._quantize_irrigation(irrigation_value)
                        return now, irrigation_value, f"今日需灌溉{irrigation_value:.1f}mm,降雨在三天后"
                
                # 近日有降雨但不足以满足需求（包括当天小雨）
                if first_rain_day and first_rain_day >= now:
                    first_rain_data = future_data[future_data["Date"] == first_rain_day]
                    if not first_rain_data.empty:
                        irrigation_value = first_rain_data['Cumulative_ETcadj'].values[0] - diff_min_real_mm * irrigation_threshold
                        if irrigation_value > min_effective_irrigation:
                            irrigation_value = min(irrigation_value, irrigation_config.get('MAX_SINGLE_IRRIGATION', 30.0))
                            irrigation_value = self._quantize_irrigation(irrigation_value)
                            return now, irrigation_value, f"今日需灌溉{irrigation_value:.1f}mm,近日有降雨但不足以满足需求"
                        
                logger.info(f"[NO_IRRIGATION] 今日有降雨预报 - third_day_etcadj={third_day_etcadj:.2f}, "
                           f"available_to_pwp={diff_min_real_mm:.2f}, thresh={irrigation_threshold:.3f}, "
                           f"first_rain_day={first_rain_day}, first_rain_amount={first_rain_amount:.2f}mm, "
                           f"days_to_rain={days_to_rain}")
                return now, 0, "今日有降雨预报，不灌溉"
                
            # 基于无降雨的决策
            irrigation_value = min(
                diff_com_real_mm, 
                third_day_etcadj - diff_min_real_mm * irrigation_threshold  
            )
            
            # 应用单次最大灌溉量限制
            max_single_irrigation = irrigation_config.get('MAX_SINGLE_IRRIGATION', 30.0)
            irrigation_value = min(irrigation_value, max_single_irrigation)
            
            # 确保灌溉量大于最小有效值
            if irrigation_value <= 0:
                logger.info(f"[NO_IRRIGATION] 土壤水分可支撑至第三天 - third_day_etcadj={third_day_etcadj:.2f}, "
                           f"available_to_pwp={diff_min_real_mm:.2f}, thresh={irrigation_threshold:.3f}, "
                           f"first_rain_day={first_rain_day}, first_rain_amount={first_rain_amount:.2f}mm, "
                           f"days_to_rain={days_to_rain}")
                return now, 0, "土壤水分可支撑至第三天，今日不灌溉"
            if irrigation_value <= min_effective_irrigation:
                logger.info(f"[NO_IRRIGATION] 计算灌溉量小于最小有效灌溉量 - third_day_etcadj={third_day_etcadj:.2f}, "
                           f"available_to_pwp={diff_min_real_mm:.2f}, thresh={irrigation_threshold:.3f}, "
                           f"first_rain_day={first_rain_day}, first_rain_amount={first_rain_amount:.2f}mm, "
                           f"days_to_rain={days_to_rain}, min_effective={min_effective_irrigation:.1f}mm")
                return now, 0, f"计算灌溉量小于最小有效灌溉量({min_effective_irrigation:.1f}mm)，今日不灌溉"
            
            # 量化灌溉量
            irrigation_value = self._quantize_irrigation(irrigation_value)
            return now, irrigation_value, f"今日需灌溉{irrigation_value:.1f}mm,近期无降雨预报"
            
        except Exception as e:
            logger.error(f"获取灌溉决策时出错: {str(e)}")
            raise

    def _quantize_irrigation(self, irrigation_value):
        """量化灌溉量（分档）
        
        Args:
            irrigation_value (float): 计算的灌溉量
            
        Returns:
            float: 量化后的灌溉量
        """
        if irrigation_value <= 0:
            return 0
            
        # 使用配置中定义的灌溉档位
        irrigation_config = getattr(self.config, 'IRRIGATION_CONFIG', {})
        irrigation_levels = irrigation_config.get('IRRIGATION_LEVELS', [0, 5, 10, 15, 20, 25, 30, 40, 50])
        for level in irrigation_levels:
            if irrigation_value <= level:
                return level
                
        return irrigation_levels[-1]  # 返回最大档位
            
    def make_irrigation_decision(self, field_id, device_id, real_humidity):
        """生成灌溉决策
        
        Args:
            field_id (str): 地块ID
            device_id (str): 设备ID（用于获取田块的传感器数据）
            real_humidity (float): 实际土壤湿度 (%)
            
        Returns:
            dict: 包含灌溉决策信息的字典
            
        Note:
            SAT、FC、PWP 从传感器自动获取（根据田块历史数据统计），无需传入
        """
        try:
            logger.info(f"[田块 {field_id}] 开始生成灌溉决策: device_id={device_id}, real_humidity={real_humidity}%")
            
            # 计算土壤湿度差异（自动从传感器获取 SAT/FC/PWP）
            SAT, FC, PWP, _, diff_min_real_mm, diff_com_real_mm = self.calculate_soil_humidity_differences(
                field_id, device_id, real_humidity
            )
            
            # 获取传感器数据用于日志
            irrigation_config = getattr(self.config, 'IRRIGATION_CONFIG', {})
            hour_timestamp = datetime.now().strftime('%Y-%m-%d-%H')
            sensor_data = self._get_cached_sensor_data(device_id, field_id, hour_timestamp)
            
            # 确保传感器参数不为 None
            sat_percent = sensor_data.get('sat') or Config.DEFAULT_SOIL_PARAMS['sat']
            fc_percent = sensor_data.get('fc') or Config.DEFAULT_SOIL_PARAMS['fc']
            pwp_percent = sensor_data.get('pwp') or Config.DEFAULT_SOIL_PARAMS['pwp']
            
            # 确保是数值类型
            try:
                sat_percent = float(sat_percent) if sat_percent is not None else Config.DEFAULT_SOIL_PARAMS['sat']
                fc_percent = float(fc_percent) if fc_percent is not None else Config.DEFAULT_SOIL_PARAMS['fc']
                pwp_percent = float(pwp_percent) if pwp_percent is not None else Config.DEFAULT_SOIL_PARAMS['pwp']
            except (ValueError, TypeError) as e:
                logger.warning(f"[田块 {field_id}] 传感器参数类型转换失败: {e}，使用默认值")
                sat_percent = Config.DEFAULT_SOIL_PARAMS['sat']
                fc_percent = Config.DEFAULT_SOIL_PARAMS['fc']
                pwp_percent = Config.DEFAULT_SOIL_PARAMS['pwp']
            
            logger.info(f"[田块 {field_id}] 传感器百分比: SAT={sat_percent}%, FC={fc_percent}%, PWP={pwp_percent}%, Real={real_humidity}%")
            
            # 运行模型（如果需要）
            self._ensure_model_run()
            
            # 获取灌溉决策
            out_file = self._get_file_path('model_output')
            date, irrigation_value, message = self.get_irrigation_decision(
                out_file, diff_min_real_mm, diff_com_real_mm
            )
            
            # 获取系数（用于日志记录）
            root_depth_coefficient = self._safe_get_coefficient('get_root_depth_coefficient', out_file)
            growth_stage_coefficient = self._safe_get_coefficient('get_growth_stage_coefficient')
            
            # 获取关键阈值信息用于meta字段
            base_threshold = irrigation_config.get('IRRIGATION_THRESHOLD', Config.DEFAULT_COEFFICIENTS['irrigation_threshold'])
            irrigation_threshold = base_threshold * growth_stage_coefficient
            min_effective_irrigation = irrigation_config.get('MIN_EFFECTIVE_IRRIGATION', 5.0)
            rain_forecast_days = irrigation_config.get('RAIN_FORECAST_DAYS', 3)
            min_rain_amount = irrigation_config.get('MIN_RAIN_AMOUNT', 5.0)
            
            # 计算土壤深度
            soil_depth = irrigation_config.get('SOIL_DEPTH_CM', Config.DEFAULT_SOIL_PARAMS['depth_cm'])
            
            logger.info(f"[田块 {field_id}] 储水指标计算详情: 土壤深度={soil_depth}cm, 根系系数={root_depth_coefficient}, 生育阶段系数={growth_stage_coefficient}")
            logger.info(f"[田块 {field_id}] 百分比数据: SAT={sat_percent}%, FC={fc_percent}%, PWP={pwp_percent}%, Real={real_humidity}%")
            logger.info(f"[田块 {field_id}] 毫米数据: SAT={SAT:.2f}mm, FC={FC:.2f}mm, PWP={PWP:.2f}mm")
            logger.info(f"[田块 {field_id}] 灌溉决策: date={date.strftime('%Y-%m-%d')}, irrigation_value={irrigation_value:.2f}mm")
            
            return {
                "date": date.strftime('%Y-%m-%d'),
                "field_id": field_id,
                "device_id": device_id,
                "message": f"当前土壤体积含水量为：{real_humidity:.2f} %, {message}",
                "irrigation_value": round(irrigation_value, 2) if irrigation_value else 0,
                "soil_data": {
                    "current_humidity": round(real_humidity, 2),
                    "root_depth_coefficient": root_depth_coefficient,
                    "growth_stage_coefficient": growth_stage_coefficient,
                    "soil_depth": soil_depth,
                    "storage_potential": round(SAT - PWP, 2),  # 蓄水潜力 = 饱和含水量 - 凋萎点
                    "effective_storage": round(FC - PWP, 2),   # 有效储水量 = 田间持水量 - 凋萎点
                    "available_storage": round(max(0, min(diff_com_real_mm, FC - PWP)), 2),  # 可利用储水量
                    "sat": round(SAT, 2),
                    "fc": round(FC, 2),
                    "pwp": round(PWP, 2),
                    "sat_percent": round(sat_percent, 2),
                    "fc_percent": round(fc_percent, 2),
                    "pwp_percent": round(pwp_percent, 2),
                    "is_real_data": True
                },
                "meta": {
                    "irrigation_threshold": round(irrigation_threshold, 3),
                    "min_effective_irrigation": round(min_effective_irrigation, 2),
                    "rain_forecast_days": rain_forecast_days,
                    "min_rain_amount": round(min_rain_amount, 2)
                }
            }
            
        except Exception as e:
            logger.error(f"生成灌溉决策时出错: {str(e)}")
            raise
    
    def _ensure_model_run(self):
        """确保模型在当天已运行"""
        now = datetime.now()
        if (self._last_model_run is None or 
            self._last_model_run.date() != now.date()):
            self.fao_model.run_model()
            self._last_model_run = now


"""
if __name__ == "__main__":
    try:
        # 导入配置
        from src.config.config import get_config
        
        # 获取配置
        config = get_config()
        
        # 创建灌溉服务实例
        irrigation_service = IrrigationService(config)
        
        # 示例数据 - 可以根据实际情况修改
        field_id = Config.IRRIGATION_CONFIG['DEFAULT_FIELD_ID']
        device_id = Config.IRRIGATION_CONFIG['DEFAULT_DEVICE_ID']
        real_humidity = 25.8  # 实际土壤湿度（百分比）
        
        # 生成灌溉决策（SAT/FC/PWP 自动从传感器获取）
        result = irrigation_service.make_irrigation_decision(
            field_id, device_id, real_humidity
        )
        
        # 打印结果
        print("\n=== 灌溉决策结果 ===")
        print(f"日期: {result['date']}")
        print(f"地块ID: {result['field_id']}")
        print(f"消息: {result['message']}")
        print(f"灌溉量(mm): {result['irrigation_value']}")
        print("\n土壤数据:")
        print(f"田间持水量(FC, mm): {result['soil_data']['fc']}")
        print(f"凋萎点(PWP, mm): {result['soil_data']['pwp']}")
        print(f"当前湿度: {result['soil_data']['current_humidity']}")
        print(f"根系深度系数: {result['soil_data']['root_depth_coefficient']}")
        print(f"生育阶段系数: {result['soil_data']['growth_stage_coefficient']}")
        
    except Exception as e:
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()
"""
