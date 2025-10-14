import pandas as pd
import os
import datetime
import math
import numpy as np
from aquacrop import AquaCropModel, Soil, Crop, InitialWaterContent, IrrigationManagement
from aquacrop.utils import prepare_weather, get_filepath
import matplotlib.pyplot as plt
import json
import logging
import sys
from typing import Dict, List, Optional, Union
from dataclasses import dataclass, field


def normalize_irr_frequency(freq_val):
    """
    规范化灌溉频率参数，支持整数天数和pandas频率字符串
    
    参数:
    freq_val: 灌溉频率值，可以是整数天数或pandas频率字符串(如 "7D")
    
    返回:
    str: 规范化的pandas频率字符串
    
    抛出:
    ValueError: 当频率值无效时
    """
    from pandas.tseries.frequencies import to_offset
    try:
        if isinstance(freq_val, (int, float)):
            # 整数天数，转换为pandas频率字符串
            return f"{int(freq_val)}D"
        # 字符串等，验证能否被pandas识别
        to_offset(freq_val)
        return freq_val
    except Exception:
        raise ValueError('IRR_FREQUENCY 应为整数天或 pandas 频率字符串(如 "7D")')


def validate_config(config):
    """
    校验配置参数的有效性和完整性
    
    参数:
    config: 配置字典
    
    抛出:
    ValueError: 当配置无效时
    """
    logger.info("开始配置校验...")
    
    # 必需的配置项（移除WEATHER_INPUT_CSV，因为可能使用WTH文件）
    required_keys = [
        'CROP_NAME', 'PLANTING_DATE', 'SIM_START_TIME', 'SIM_END_TIME',
        'SOIL_TEXTURE', 'SOIL_SATURATION', 'SOIL_FIELD_CAPACITY', 'SOIL_WILTING_POINT',
        'IRR_FREQUENCY', 'IRR_DEPTH', 'OUTPUT_DIR'
    ]
    
    # 检查必需配置项
    missing_keys = [key for key in required_keys if key not in config]
    if missing_keys:
        raise ValueError(f"缺少必需的配置项: {missing_keys}")
    
    # 日期格式校验 (PLANTING_DATE由AquaCrop库处理，格式为MM/DD)
    date_keys = ['SIM_START_TIME', 'SIM_END_TIME']
    for key in date_keys:
        if key in config:
            try:
                pd.to_datetime(config[key])
            except Exception as e:
                raise ValueError(f"配置项 {key} 的日期格式无效: {config[key]}, 错误: {e}")
    
    # PLANTING_DATE格式校验 (应为MM/DD格式)
    if 'PLANTING_DATE' in config:
        planting_date = config['PLANTING_DATE']
        if not isinstance(planting_date, str) or '/' not in planting_date:
            raise ValueError(f"PLANTING_DATE应为MM/DD格式，当前值: {planting_date}")
        try:
            month, day = planting_date.split('/')
            month, day = int(month), int(day)
            if not (1 <= month <= 12) or not (1 <= day <= 31):
                raise ValueError(f"PLANTING_DATE月份应在1-12之间，日期应在1-31之间: {planting_date}")
        except (ValueError, IndexError) as e:
            raise ValueError(f"PLANTING_DATE格式无效，应为MM/DD格式: {planting_date}, 错误: {e}")
    
    # 数值范围校验
    numeric_validations = {
        'SOIL_SATURATION': (0.3, 0.7, "土壤饱和含水量应在0.3-0.7之间"),
        'SOIL_FIELD_CAPACITY': (0.1, 0.5, "土壤田间持水量应在0.1-0.5之间"),
        'SOIL_WILTING_POINT': (0.05, 0.3, "土壤凋萎点应在0.05-0.3之间"),
        'IRR_DEPTH': (5, 100, "灌溉深度应在5-100mm之间"),
        'LATITUDE': (-90, 90, "纬度应在-90到90度之间"),
        'ELEVATION': (-500, 5000, "海拔应在-500到5000米之间")
    }
    
    for key, (min_val, max_val, message) in numeric_validations.items():
        if key in config:
            try:
                value = float(config[key])
                if not (min_val <= value <= max_val):
                    raise ValueError(f"{message}, 当前值: {value}")
            except (ValueError, TypeError) as e:
                if "invalid literal" not in str(e):
                    raise ValueError(f"配置项 {key} 必须是数值类型, 当前值: {config[key]}")
    
    # 特殊处理IRR_FREQUENCY校验（支持整数天数和pandas频率字符串）
    if 'IRR_FREQUENCY' in config:
        try:
            normalize_irr_frequency(config['IRR_FREQUENCY'])
        except ValueError as e:
            raise ValueError(f"IRR_FREQUENCY 配置无效: {e}")
    
    # 土壤参数逻辑校验
    if all(key in config for key in ['SOIL_SATURATION', 'SOIL_FIELD_CAPACITY', 'SOIL_WILTING_POINT']):
        sat = float(config['SOIL_SATURATION'])
        fc = float(config['SOIL_FIELD_CAPACITY'])
        wp = float(config['SOIL_WILTING_POINT'])
        
        if not (wp < fc < sat):
            raise ValueError(f"土壤参数逻辑错误: 凋萎点({wp}) < 田间持水量({fc}) < 饱和含水量({sat})")
    
    # 日期逻辑校验
    if all(key in config for key in ['SIM_START_TIME', 'SIM_END_TIME']):
        start_date = pd.to_datetime(config['SIM_START_TIME'])
        end_date = pd.to_datetime(config['SIM_END_TIME'])
        
        if start_date >= end_date:
            raise ValueError(f"模拟开始时间({start_date})必须早于结束时间({end_date})")
        
        # 注意：PLANTING_DATE格式为MM/DD，由AquaCrop库处理，不在此处验证日期范围
    
    # 文件路径校验
    path_keys = ['OUTPUT_DIR']  # 去掉WEATHER_INPUT_CSV的硬校验
    for key in path_keys:
        if key in config:
            path = config[key]
            if key == 'OUTPUT_DIR':
                # 输出目录可以不存在，会自动创建
                parent_dir = os.path.dirname(path) if os.path.dirname(path) else '.'
                if not os.path.exists(parent_dir):
                    logger.warning(f"输出目录的父目录不存在: {parent_dir}")
    
    # 可选的CSV文件校验（如果配置了但不存在则警告）
    csv_path = config.get('WEATHER_INPUT_CSV')
    if csv_path and not os.path.exists(csv_path):
        logger.warning(f"配置的 WEATHER_INPUT_CSV 不存在: {csv_path}，将尝试使用 WTH 文件")
    
    # ETo方法校验
    if 'ETO_METHOD' in config:
        valid_methods = ['observed', 'hargreaves_simplified', 'hargreaves_fao56']
        if config['ETO_METHOD'] not in valid_methods:
            raise ValueError(f"ETo估算方法无效: {config['ETO_METHOD']}, 有效选项: {valid_methods}")
    
    logger.info("配置校验通过")
    return True


def calculate_eto_hargreaves_fao56(weather_data, latitude, elevation):
    """
    使用FAO-56 Hargreaves方法计算参考蒸散量ETo
    
    参数:
    weather_data: DataFrame，包含Date, Tmax, Tmin列
    latitude: 纬度（度）
    elevation: 海拔（米）- 用于大气压力修正
    
    返回:
    Series，计算得到的ETo值
    """
    # 确保Date列是datetime类型
    if 'Date' in weather_data.columns:
        dates = pd.to_datetime(weather_data['Date'])
    else:
        # 如果没有Date列，使用索引
        dates = weather_data.index
        if not isinstance(dates, pd.DatetimeIndex):
            raise ValueError("需要Date列或DatetimeIndex来计算外辐射Ra")
    
    # 计算外辐射Ra
    ra_values = []
    for date in dates:
        day_of_year = date.timetuple().tm_yday
        ra = calculate_extraterrestrial_radiation(latitude, day_of_year)
        ra_values.append(ra)
    
    ra_series = pd.Series(ra_values, index=weather_data.index)
    
    # 计算平均温度
    tmean = (weather_data['Tmax'] + weather_data['Tmin']) / 2
    
    # 计算温度差
    temp_range = weather_data['Tmax'] - weather_data['Tmin']
    
    # 根据海拔高度计算大气压力修正系数（FAO-56方法）
    # P = 101.3 * ((293 - 0.0065 * z) / 293)^5.26
    # 其中z是海拔高度（米）
    if elevation is not None and elevation > 0:
        atmospheric_pressure = 101.3 * ((293 - 0.0065 * elevation) / 293) ** 5.26
        pressure_correction = atmospheric_pressure / 101.3  # 相对于海平面的修正系数
        logger.debug(f"海拔 {elevation}m 的大气压力修正系数: {pressure_correction:.4f}")
    else:
        pressure_correction = 1.0  # 海平面或未提供海拔时不修正
        if elevation is None:
            logger.debug("未提供海拔高度，使用海平面大气压力")
    
    # FAO-56 Hargreaves公式，加入大气压力修正
    # ETo = 0.0023 * (Tmean + 17.8) * sqrt(TD) * Ra * pressure_correction
    # 其中Ra需要转换单位从MJ/m²/day到mm/day（除以2.45）
    eto = 0.0023 * (tmean + 17.8) * np.sqrt(temp_range) * (ra_series / 2.45) * pressure_correction
    
    return eto


def calculate_extraterrestrial_radiation(latitude, day_of_year):
    """
    计算外辐射Ra (MJ/m²/day)
    
    参数:
    latitude: 纬度（度）
    day_of_year: 年积日（1-365/366）
    
    返回:
    外辐射Ra值 (MJ/m²/day)
    """
    # 转换纬度为弧度
    lat_rad = math.radians(latitude)
    
    # 太阳赤纬角
    delta = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)
    
    # 相对日地距离的倒数
    dr = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
    
    # 日落时角
    ws = math.acos(-math.tan(lat_rad) * math.tan(delta))
    
    # 外辐射Ra
    ra = (24 * 60 / math.pi) * 0.082 * dr * (
        ws * math.sin(lat_rad) * math.sin(delta) + 
        math.cos(lat_rad) * math.cos(delta) * math.sin(ws)
    )
    
    return ra

def setup_logger(name: str = __name__, level: int = logging.INFO, log_file: Optional[str] = None) -> logging.Logger:
    """
    设置日志器配置
    
    参数:
    name: 日志器名称
    level: 日志级别
    log_file: 日志文件路径（可选）
    
    返回:
    logging.Logger: 配置好的日志器
    """
    logger = logging.getLogger(name)
    
    # 避免重复添加处理器
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # 创建格式器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器（如果指定了日志文件）
    if log_file:
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"无法创建日志文件处理器: {e}")
    
    # 防止日志传播到根日志器
    logger.propagate = False
    
    return logger

# 获取日志器
logger = setup_logger(__name__)

@dataclass
class ModelConfig:
    """模型配置数据类"""
    SOIL_LAYERS: int = 3
    CHART_FIGSIZE: tuple = (10, 6)
    DPI: int = 100
    CHART_COLORS: List[str] = field(default_factory=lambda: ['#87CEEB', '#FFD700', '#90EE90', '#FFA07A', '#9370DB', '#40E0D0'])
    CHART_FONTS: List[str] = field(default_factory=lambda: ['Microsoft YaHei', 'SimHei', 'DejaVu Sans', 'Arial Unicode MS'])
    
    def __post_init__(self):
        pass
    
    def get_matplotlib_rc_params(self) -> dict:
        """获取matplotlib配置参数,包含字体回退机制"""
        return {
            'font.sans-serif': self.CHART_FONTS,
            'axes.unicode_minus': False
        }


def _normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    归一化DataFrame的列名，处理不同版本的AquaCrop输出差异
    
    参数:
    df: 需要处理的DataFrame
    
    返回:
    pd.DataFrame: 列名归一化后的DataFrame副本
    """
    df = df.copy()
    
    # 冠层覆盖度列名映射
    cc_mapping = {
        'canopy_cover': '_cc',
        'CanopyCover': '_cc',
        'CC': '_cc',
        'cc': '_cc'
    }
    
    # DAP列名映射
    dap_mapping = {
        'dap': '_dap',
        'DAP': '_dap',
        'days_after_planting': '_dap',
        'DaysAfterPlanting': '_dap'
    }
    
    # 应用映射
    for old_name, new_name in cc_mapping.items():
        if old_name in df.columns and new_name not in df.columns:
            df[new_name] = df[old_name]
            logger.debug(f"归一化列名: {old_name} -> {new_name}")
    
    for old_name, new_name in dap_mapping.items():
        if old_name in df.columns and new_name not in df.columns:
            df[new_name] = df[old_name]
            logger.debug(f"归一化列名: {old_name} -> {new_name}")
    
    # 如果没有找到任何匹配的列，创建默认列
    if '_cc' not in df.columns:
        # 尝试从其他可能的列推断
        possible_cc_cols = [col for col in df.columns if 'cover' in col.lower() or 'canopy' in col.lower()]
        if possible_cc_cols:
            df['_cc'] = df[possible_cc_cols[0]]
            logger.info(f"使用列 {possible_cc_cols[0]} 作为冠层覆盖度")
        else:
            df['_cc'] = 0.0
            logger.warning("未找到冠层覆盖度列，使用默认值0.0")
    
    if '_dap' not in df.columns:
        # 尝试从日期计算DAP
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
            df['_dap'] = (df['Date'] - df['Date'].min()).dt.days
            logger.info("从Date列计算DAP")
        else:
            df['_dap'] = range(len(df))
            logger.warning("未找到DAP列，使用行索引作为DAP")
    
    return df


def _get_web_path(file_path: str, images_dir: str, static_url_prefix: str, static_root: str = None) -> str:
    """
    将物理文件路径转换为Web可访问的URL路径
    
    参数:
    file_path: 图片文件的物理路径
    images_dir: 图片目录的物理路径
    static_url_prefix: 静态文件URL前缀
    static_root: 静态文件根目录（可选）
    
    返回:
    str: Web可访问的URL路径
    """
    try:
        # 获取文件名
        filename = os.path.basename(file_path)
        
        # 如果提供了static_root，计算相对路径
        if static_root and os.path.exists(static_root):
            try:
                # 计算images_dir相对于static_root的路径
                rel_path = os.path.relpath(images_dir, static_root)
                # 标准化路径分隔符为Web格式
                rel_path = rel_path.replace(os.sep, '/')
                web_path = f"{static_url_prefix.rstrip('/')}/{rel_path}/{filename}"
                logger.debug(f"使用相对路径映射: {file_path} -> {web_path}")
                return web_path
            except ValueError:
                # 如果无法计算相对路径，回退到默认方式
                logger.warning(f"无法计算相对路径，使用默认映射: {images_dir} 不在 {static_root} 下")
        
        # 默认映射方式：假设images_dir对应static_url_prefix/images/
        web_path = f"{static_url_prefix.rstrip('/')}/images/{filename}"
        logger.debug(f"使用默认路径映射: {file_path} -> {web_path}")
        return web_path
        
    except Exception as e:
        logger.error(f"生成Web路径时出错: {str(e)}")
        # 回退到最简单的映射
        filename = os.path.basename(file_path)
        return f"{static_url_prefix.rstrip('/')}/images/{filename}"


def _ensure_date_col(df: pd.DataFrame, start: pd.Timestamp) -> pd.DataFrame:
    """
    安全地确保DataFrame包含正确的Date列
    
    参数:
    df: 需要处理的DataFrame
    start: 开始日期
    
    返回:
    pd.DataFrame: 包含正确Date列的DataFrame副本
    """
    df = df.copy()
    if 'Date' in df.columns:
        # 如果Date列已存在，尝试转换为datetime类型
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        # 如果所有日期都是NaT或无效，重新生成日期序列
        if df['Date'].isna().all():
            df['Date'] = pd.date_range(start=start, periods=len(df), freq='D')
    else:
        # 如果Date列不存在，在第一列插入
        df.insert(0, 'Date', pd.date_range(start=start, periods=len(df), freq='D'))
    return df

def validate_input_data(weather_df: pd.DataFrame) -> None:
    """验证输入数据的完整性和有效性
    Args:
        weather_df: 包含气象数据的DataFrame 
    Raises:
        ValueError: 当数据验证失败时
    """
    required_columns = ['Date', 'Tmin', 'Tmax', 'Precipitation', 'ETo']
    missing_columns = [col for col in required_columns if col not in weather_df.columns]
    if missing_columns:
        raise ValueError(f"输入数据缺少必要列: {', '.join(missing_columns)}")
        
    if (weather_df['Tmin'] > weather_df['Tmax']).any():
        raise ValueError("最低温度不能高于最高温度")
        
    null_counts = weather_df[required_columns].isnull().sum()
    if null_counts.any():
        raise ValueError(f"数据中存在缺失值:\n{null_counts[null_counts > 0]}")

def parse_wth_file(wth_file_path: str) -> pd.DataFrame:
    """解析.wth格式的气象数据文件
    
    Args:
        wth_file_path: .wth文件路径
    
    Returns:
        pd.DataFrame: 包含解析后数据的DataFrame
    
    Raises:
        FileNotFoundError: 当输入文件不存在时
        ValueError: 当数据格式不正确时
    """
    try:
        logger.info(f"开始解析.wth文件: {wth_file_path}")
        
        if not os.path.exists(wth_file_path):
            raise FileNotFoundError(f"输入文件不存在: {wth_file_path}")
        
        # 读取文件内容
        with open(wth_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 查找数据开始的行
        data_start_line = 0
        for i, line in enumerate(lines):
            if "Year-DOY" in line:
                data_start_line = i + 1
                header_line = line
                break
        
        if data_start_line == 0:
            raise ValueError("无法找到数据开始行，文件格式可能不正确")
        
        # 解析列名
        headers = header_line.strip().split()
        
        # 解析数据行
        data_rows = []
        for line in lines[data_start_line:]:
            if line.strip() and not line.startswith('*'):
                values = line.strip().split()
                if len(values) >= len(headers):
                    data_rows.append(values[:len(headers)])
        
        # 创建DataFrame
        df = pd.DataFrame(data_rows, columns=headers)
        
        # 转换日期格式
        def convert_year_doy_to_date(year_doy):
            try:
                parts = str(year_doy).split('-')
                if len(parts) != 2:
                    return pd.NaT
                
                year = int(parts[0])
                doy = int(parts[1])
                
                date = datetime.datetime(year, 1, 1) + datetime.timedelta(days=doy-1)
                return date
            except Exception as e:
                logger.error(f"转换日期格式出错: {year_doy}, 错误: {str(e)}")
                return pd.NaT
        
        # 转换日期列
        df['Date'] = df['Year-DOY'].apply(convert_year_doy_to_date)
        
        # 转换数值列
        numeric_columns = ['Tmax', 'Tmin', 'Rain', 'ETref']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 创建必要的列
        df['Precipitation'] = df['Rain']
        df['ETo'] = df['ETref']
        
        logger.info(f"成功解析.wth文件，共{len(df)}行数据")
        return df
    
    except Exception as e:
        logger.error(f"解析.wth文件过程中出错: {str(e)}", exc_info=True)
        raise

def convert_irrigation_weather_to_aquacrop_format(input_file_path: str, output_txt_path: str, config: dict) -> str:
    """转换气象数据格式为AquaCrop模型所需格式
    Args:
        input_file_path: 输入气象数据文件路径 (.csv 或 .wth)
        output_txt_path: 输出的aquacrop_weather.txt文件路径
        config: 配置字典，包含ETO_METHOD、LATITUDE、ELEVATION等参数
    
    Returns:
        str: 转换后的文件路径
        
    Raises:
        FileNotFoundError: 当输入文件不存在时
        ValueError: 当数据格式不正确时
    """
    try:
        logger.info(f"开始转换气象数据: {input_file_path}")
        
        if not os.path.exists(input_file_path):
            raise FileNotFoundError(f"输入文件不存在: {input_file_path}")
        
        # 根据文件扩展名选择不同的解析方法
        file_ext = os.path.splitext(input_file_path)[1].lower()
        
        if file_ext == '.wth':
            logger.info("检测到.wth格式文件，使用WTH文件解析器")
            weather_df = parse_wth_file(input_file_path)
        else:
            logger.info("使用CSV文件解析方法")
            weather_df = pd.read_csv(input_file_path)
            
            # 处理CSV格式特有的日期转换
            if 'Date' in weather_df.columns:
                date_sample = str(weather_df['Date'].iloc[0]) if not weather_df.empty else ""
                # 使用正则表达式严格匹配年份-DOY格式
                import re
                doy_pattern = re.compile(r'^\d{4}-\d{1,3}$')
                if doy_pattern.match(date_sample):
                    logger.info("检测到年份-日序号(DOY)日期格式，正在转换...")
                    
                    def convert_year_doy_to_date(year_doy):
                        try:
                            if not doy_pattern.match(str(year_doy)):
                                return pd.NaT
                                
                            parts = str(year_doy).split('-')
                            year = int(parts[0])
                            doy = int(parts[1])
                            
                            # 校验DOY范围
                            if not (1 <= doy <= 366):
                                logger.warning(f"DOY值超出范围 [1-366]: {doy}")
                                return pd.NaT
                            
                            date = datetime.datetime(year, 1, 1) + datetime.timedelta(days=doy-1)
                            return date
                        except Exception as e:
                            logger.error(f"转换日期格式出错: {year_doy}, 错误: {str(e)}")
                            return pd.NaT
                    
                    weather_df['Date'] = weather_df['Date'].apply(convert_year_doy_to_date)
                    
                    # 清理DOY转换失败的记录
                    invalid_dates = weather_df['Date'].isna()
                    if invalid_dates.any():
                        invalid_count = invalid_dates.sum()
                        logger.warning(f"发现 {invalid_count} 条DOY转换失败的记录，将被删除")
                        weather_df = weather_df.dropna(subset=['Date']).reset_index(drop=True)
                        logger.info(f"清理后剩余 {len(weather_df)} 条有效记录")
                else:
                    weather_df['Date'] = pd.to_datetime(weather_df['Date'], errors='coerce')
                    
                    # 清理日期转换失败的记录
                    invalid_dates = weather_df['Date'].isna()
                    if invalid_dates.any():
                        invalid_count = invalid_dates.sum()
                        logger.warning(f"发现 {invalid_count} 条日期转换失败的记录，将被删除")
                        weather_df = weather_df.dropna(subset=['Date']).reset_index(drop=True)
                        logger.info(f"清理后剩余 {len(weather_df)} 条有效记录")
            elif '日期' in weather_df.columns:
                weather_df['Date'] = pd.to_datetime(weather_df['日期'], errors='coerce')
                weather_df = weather_df.drop('日期', axis=1)
                
                # 清理日期转换失败的记录
                invalid_dates = weather_df['Date'].isna()
                if invalid_dates.any():
                    invalid_count = invalid_dates.sum()
                    logger.warning(f"发现 {invalid_count} 条中文日期转换失败的记录，将被删除")
                    weather_df = weather_df.dropna(subset=['Date']).reset_index(drop=True)
                    logger.info(f"清理后剩余 {len(weather_df)} 条有效记录")
            
            # 列名映射 - 智能转换，避免冗余操作
            column_mapping = {
                '最高温度': 'Tmax',
                '最低温度': 'Tmin',
                '降雨量': 'Precipitation',
                '参考蒸散量': 'ETo',
            }
            
            # 获取所有目标英文列名
            target_columns = set(column_mapping.values())
            current_columns = set(weather_df.columns)
            
            # 只处理需要转换的列，避免自映射
            for chinese_name, english_name in column_mapping.items():
                if chinese_name in current_columns and english_name not in current_columns:
                    # 只有当中文列存在且英文列不存在时才进行转换
                    weather_df[english_name] = weather_df[chinese_name]
                    weather_df = weather_df.drop(chinese_name, axis=1)
                    logger.info(f"已转换列名: {chinese_name} -> {english_name}")
                elif chinese_name in current_columns and english_name in current_columns:
                    # 如果中文列和英文列都存在，删除中文列，保留英文列
                    weather_df = weather_df.drop(chinese_name, axis=1)
                    logger.info(f"删除重复的中文列名: {chinese_name}，保留英文列: {english_name}")
                elif english_name in current_columns:
                    # 如果英文列已存在，无需操作
                    logger.debug(f"列 {english_name} 已存在，跳过映射")
            
            # 检查是否所有必需的列都存在
            required_columns = ['Tmax', 'Tmin', 'Precipitation']  # ETo可能通过计算得到
            missing_columns = [col for col in required_columns if col not in weather_df.columns]
            if missing_columns:
                logger.warning(f"缺少必需的列: {missing_columns}")
            
            # 数据清洗步骤
            logger.info("开始数据清洗...")
            initial_count = len(weather_df)
            
            # 1. 按日期排序
            weather_df = weather_df.sort_values(by='Date').reset_index(drop=True)
            
            # 2. 去除重复记录（基于日期）
            duplicate_mask = weather_df.duplicated(subset=['Date'], keep='first')
            if duplicate_mask.any():
                duplicate_count = duplicate_mask.sum()
                logger.warning(f"发现 {duplicate_count} 条重复日期记录，保留最早的记录")
                weather_df = weather_df[~duplicate_mask].reset_index(drop=True)
            
            # 3. 处理异常值
            numeric_columns = ['Tmin', 'Tmax', 'Precipitation', 'ETo']
            for col in numeric_columns:
                if col in weather_df.columns:
                    # 处理负降水量
                    if col == 'Precipitation':
                        negative_mask = weather_df[col] < 0
                        if negative_mask.any():
                            negative_count = negative_mask.sum()
                            logger.warning(f"发现 {negative_count} 条负降水量记录，将设为0")
                            weather_df.loc[negative_mask, col] = 0
                    
                    # 处理极端异常值（使用IQR方法）
                    Q1 = weather_df[col].quantile(0.25)
                    Q3 = weather_df[col].quantile(0.75)
                    IQR = Q3 - Q1
                    lower_bound = Q1 - 3 * IQR  # 使用3倍IQR作为极端异常值阈值
                    upper_bound = Q3 + 3 * IQR
                    
                    extreme_outliers = (weather_df[col] < lower_bound) | (weather_df[col] > upper_bound)
                    if extreme_outliers.any():
                        outlier_count = extreme_outliers.sum()
                        logger.warning(f"发现 {col} 列有 {outlier_count} 个极端异常值")
                        # 将极端异常值替换为边界值
                        weather_df.loc[weather_df[col] < lower_bound, col] = lower_bound
                        weather_df.loc[weather_df[col] > upper_bound, col] = upper_bound
            
            # 4. 温度逻辑检查
            if 'Tmin' in weather_df.columns and 'Tmax' in weather_df.columns:
                temp_error_mask = weather_df['Tmin'] > weather_df['Tmax']
                if temp_error_mask.any():
                    error_count = temp_error_mask.sum()
                    logger.warning(f"发现 {error_count} 条最低温度高于最高温度的记录，将交换数值")
                    # 交换Tmin和Tmax的值
                    weather_df.loc[temp_error_mask, ['Tmin', 'Tmax']] = weather_df.loc[temp_error_mask, ['Tmax', 'Tmin']].values
            
            final_count = len(weather_df)
            logger.info(f"数据清洗完成: 原始记录 {initial_count} 条，清洗后 {final_count} 条")
        
        # 确保必要的列存在
        if 'Rain' in weather_df.columns and 'Precipitation' not in weather_df.columns:
            weather_df['Precipitation'] = weather_df['Rain']
            logger.info("使用Rain列作为Precipitation")
        
        if 'Etref' in weather_df.columns and 'ETo' not in weather_df.columns:
            weather_df['ETo'] = weather_df['Etref']
            logger.info("使用Etref列作为ETo")
        
        # 处理缺失的ETo数据
        if 'ETo' not in weather_df.columns or weather_df['ETo'].isnull().any() or (weather_df['ETo'] == 0).any():
            # 获取ETo估算方法配置
            eto_method = config.get('ETO_METHOD', 'hargreaves_simplified')
            logger.info(f"检测到缺失的参考蒸散量(ETo)数据，使用{eto_method}方法估算...")
            
            # 确保我们有Tmax和Tmin数据
            if 'Tmax' in weather_df.columns and 'Tmin' in weather_df.columns:
                # 如果列不存在，创建它
                if 'ETo' not in weather_df.columns:
                    weather_df['ETo'] = 0.0
                
                # 计算缺失值的索引
                missing_mask = weather_df['ETo'].isnull() | (weather_df['ETo'] == 0)
                
                if eto_method == 'observed':
                    # 使用观测数据，不进行估算
                    logger.warning("ETo方法设置为'observed'，但数据缺失，将使用简化Hargreaves方法作为回退")
                    eto_method = 'hargreaves_simplified'
                
                if eto_method in ['hargreaves_fao56', 'hargreaves_simplified']:
                    # 统一使用基于外辐射Ra的Hargreaves方法
                    latitude = config.get('LATITUDE')
                    if latitude is None:
                        logger.warning("未提供 LATITUDE，ETo 将退化为经验近似，结果仅供参考")
                        # 若确实无纬度，使用经验近似公式，但加醒目warning
                        weather_df.loc[missing_mask, 'ETo'] = 0.0023 * (
                            (weather_df.loc[missing_mask, 'Tmax'] + weather_df.loc[missing_mask, 'Tmin']) / 2 + 17.8
                        ) * (weather_df.loc[missing_mask, 'Tmax'] - weather_df.loc[missing_mask, 'Tmin'])**0.5 * 0.408
                    else:
                        # 使用基于外辐射Ra的Hargreaves方法（FAO-56标准）
                        elevation = config.get('ELEVATION', 0.0)
                        logger.info(f"使用基于外辐射Ra的Hargreaves方法计算ETo (方法: {eto_method}, 纬度: {latitude}°, 海拔: {elevation}m)")
                        weather_df.loc[missing_mask, 'ETo'] = calculate_eto_hargreaves_fao56(
                            weather_df.loc[missing_mask], latitude, elevation
                        )
                
                logger.info(f"已估算{missing_mask.sum()}行缺失的ETo数据")
            else:
                raise ValueError("缺少最高温度(Tmax)或最低温度(Tmin)数据，无法估算ETo")
        
        # 最终数据清理检查
        initial_count = len(weather_df)
        weather_df = weather_df.dropna(subset=['Date', 'Tmin', 'Tmax', 'Precipitation', 'ETo']).reset_index(drop=True)
        final_count = len(weather_df)
        
        if final_count < initial_count:
            removed_count = initial_count - final_count
            logger.warning(f"最终清理阶段删除了 {removed_count} 条包含缺失值的记录")
            logger.info(f"最终有效记录数: {final_count}")
        
        if final_count == 0:
            raise ValueError("经过数据清理后，没有有效的气象数据记录")
        
        # 数据验证
        validate_input_data(weather_df)
        
        # 准备输出数据
        weather_df = weather_df.sort_values(by='Date')
        weather_df['Year'] = weather_df['Date'].dt.year
        weather_df['Month'] = weather_df['Date'].dt.month
        weather_df['Day'] = weather_df['Date'].dt.day
        
        weather_df = weather_df.rename(columns={
            'Tmin': 'MinTemp',
            'Tmax': 'MaxTemp',
            'Precipitation': 'Precipitation',
            'ETo': 'ReferenceET'
        })
        
        aquacrop_columns = ['Day', 'Month', 'Year', 'MinTemp', 'MaxTemp', 'Precipitation', 'ReferenceET']
        aquacrop_df = weather_df[aquacrop_columns]
        
        # 保存转换后的数据
        out_dir = os.path.dirname(output_txt_path) or '.'
        os.makedirs(out_dir, exist_ok=True)
        with open(output_txt_path, 'w', encoding='utf-8') as f:
            aquacrop_df.to_csv(f, index=False, header=True, sep='\t')
        
        logger.info(f"转换完成! 文件已保存到: {output_txt_path}")
        return output_txt_path
        
    except Exception as e:
        logger.error(f"转换过程中出错: {str(e)}", exc_info=True)
        raise

def get_current_growth_stage(stage_results: List[Dict]) -> Optional[Dict]:
    """根据当前日期确定小麦处于哪个生育阶段
    
    Args:
        stage_results: 生育阶段结果列表,每个元素包含开始日期、结束日期等信息
        
    Returns:
        Optional[Dict]: 当前生育阶段信息,如果无法确定则返回None
    """
    def _to_date(x):
        """统一转换为date对象"""
        if isinstance(x, datetime.datetime): 
            return x.date()
        if isinstance(x, datetime.date):     
            return x
        return pd.to_datetime(x).date()      # 字符串/时间戳
    
    try:
        today = datetime.datetime.now().date()
        logger.debug(f"当前日期: {today}")
        
        for stage in stage_results:
            start_date = _to_date(stage["开始日期"])
            end_date = _to_date(stage["结束日期"])
            
            if start_date <= today <= end_date:
                # 使用含端点的天数计算，避免单日阶段进度为0
                total_days = (end_date - start_date).days + 1
                days_passed = (today - start_date).days + 1
                # 边界保护
                days_passed = max(1, min(days_passed, total_days))
                progress = round(days_passed / total_days * 100, 2) if total_days > 0 else 0
                
                result = {
                    "阶段": stage["阶段"],
                    "开始日期": start_date.strftime('%Y-%m-%d'),
                    "结束日期": end_date.strftime('%Y-%m-%d'),
                    "进度": progress,
                    "持续天数": stage["持续天数"],
                    "已过天数": days_passed  # 已过天数（含当天）
                }
                logger.info(f"当前生育阶段: {result['阶段']}, 进度: {progress}%")
                return result
        
        if stage_results:
            first_stage_start = _to_date(stage_results[0]["开始日期"])
            last_stage_end = _to_date(stage_results[-1]["结束日期"])
            
            if today < first_stage_start:
                logger.info("当前处于播种前准备期")
                return {
                    "阶段": "播种前准备期",
                    "开始日期": None,
                    "结束日期": first_stage_start.strftime('%Y-%m-%d'),
                    "进度": 0,
                    "持续天数": 0,
                    "已过天数": 0
                }
            elif today > last_stage_end:
                logger.info("当前处于收获后期")
                return {
                    "阶段": "收获后期",
                    "开始日期": last_stage_end.strftime('%Y-%m-%d'),
                    "结束日期": None,
                    "进度": 100,
                    "持续天数": 0,
                    "已过天数": 0
                }
        
        logger.warning("无法确定当前生育阶段")
        return None
        
    except Exception as e:
        logger.error(f"获取当前生育阶段时出错: {str(e)}", exc_info=True)
        return None

def get_growth_stages_from_model(daily_crop_growth):
    """从模型数据中提取更准确的生育期划分"""

    model_irr_dir = os.path.dirname(__file__)
    project_root = os.path.abspath(os.path.join(model_irr_dir, '../../'))
    

    sys.path.append(project_root)
    from config import current_config
    
    logger.info("===== 分析小麦生育阶段 =====")
    

    config = current_config().AQUACROP_CONFIG
    standard_stages = config.get('GROWTH_STAGES_DAP', config.get('GROWTH_STAGES', []))
    
    # 归一化列名，确保使用统一的列名
    df = _normalize_column_names(daily_crop_growth)
    df = df.sort_values("_dap")
    
    stage_results = []
    
    min_available_dap = df["_dap"].min()
    max_available_dap = df["_dap"].max()
    logger.info(f"模型中可用的DAP范围: {min_available_dap} - {max_available_dap}")
    
    date_diffs = df["Date"].diff().dropna()
    if not all(diff == pd.Timedelta(days=1) for diff in date_diffs):
        logger.warning("模型日期不连续，将尝试修正")
    
    for i, stage in enumerate(standard_stages):
        stage_name = stage["阶段"]
        start_dap = max(stage["开始DAP"], min_available_dap)  
        end_dap = min(stage["结束DAP"], max_available_dap)    
        
        if start_dap > max_available_dap or end_dap < min_available_dap:
            logger.info(f"跳过 {stage_name}: DAP范围 {stage['开始DAP']}-{stage['结束DAP']} 超出模型可用范围")
            continue
        
        stage_data = df[(df["_dap"] >= start_dap) & (df["_dap"] <= end_dap)]
        
        if not stage_data.empty:
            start_date = stage_data["Date"].min()
            end_date = stage_data["Date"].max()
            
            if i > 0 and stage_results:
                previous_end_date = stage_results[-1]["结束日期"]
                expected_start_date = previous_end_date + pd.Timedelta(days=1)
                
                if start_date != expected_start_date:
                    logger.info(f"调整 {stage_name} 开始日期从 {start_date.strftime('%Y-%m-%d')} 到 {expected_start_date.strftime('%Y-%m-%d')} 以保持连续性")
                    start_date = expected_start_date
                    start_dap_row = df[df["Date"] >= start_date]
                    if not start_dap_row.empty:
                        start_dap = start_dap_row.iloc[0]["_dap"]
            
            # 检查拉齐后是否出现负持续期
            if start_date > end_date:
                logger.warning(f"{stage_name} 被压缩为负持续期（开始: {start_date.strftime('%Y-%m-%d')}, 结束: {end_date.strftime('%Y-%m-%d')}），跳过")
                continue
            
            duration = (end_date - start_date).days + 1
            
            stage_results.append({
                "阶段": stage_name,
                "开始日期": start_date,
                "结束日期": end_date,
                "开始DAP": start_dap,
                "结束DAP": end_dap,
                "持续天数": duration
            })
            
            logger.info(f"{stage_name}: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}，持续{duration}天 (DAP: {start_dap:.1f}-{end_dap:.1f})")
    
    if stage_results:
        total_start_date = stage_results[0]["开始日期"]
        total_end_date = stage_results[-1]["结束日期"]
        total_duration = (total_end_date - total_start_date).days + 1
        logger.info(f"总生育期: {total_start_date.strftime('%Y-%m-%d')} 至 {total_end_date.strftime('%Y-%m-%d')}，共{total_duration}天")
    
    return stage_results

def create_growth_stages_visualization(stage_results: List[Dict], current_stage: Optional[Dict], images_dir: str) -> str:
    """创建生育期可视化图表
    
    Args:
        stage_results: 生育阶段结果列表
        current_stage: 当前生育阶段信息
        images_dir: 图像文件目录路径
        
    Returns:
        str: 生成的图表文件路径
        
    Raises:
        ValueError: 当输入数据无效时
    """
    try:
        if not stage_results:
            raise ValueError("生育阶段数据为空")
            
        logger.info("开始创建生育期可视化图表")
        
        config = ModelConfig()
        
        # 使用配置化的matplotlib参数
        rc_params = config.get_matplotlib_rc_params()
        
        stage_results = sorted(stage_results, key=lambda x: x["开始日期"])
        stages = [stage["阶段"] for stage in stage_results]
        durations = [stage["持续天数"] for stage in stage_results]
        
        start_dates = []
        end_dates = []
        for stage in stage_results:
            start_date = pd.to_datetime(stage["开始日期"]).strftime('%m/%d')
            end_date = pd.to_datetime(stage["结束日期"]).strftime('%m/%d')
            start_dates.append(start_date)
            end_dates.append(end_date)
        
        stage_labels = [f"{stage}\n({start}-{end})" 
                       for stage, start, end in zip(stages, start_dates, end_dates)]
        
        # 设置默认颜色，避免None错误
        default_colors = ['#87CEEB', '#FFD700', '#90EE90', '#FFA07A', '#9370DB', '#40E0D0']
        colors = config.CHART_COLORS if config.CHART_COLORS is not None else default_colors
        
        if len(colors) < len(stages):
            colors = colors * (len(stages) // len(colors) + 1)
        
        with plt.rc_context(rc_params):
            plt.figure(figsize=config.CHART_FIGSIZE)
            
            bars = plt.barh(stage_labels, durations, color=colors[:len(stages)])
            
            for i, bar in enumerate(bars):
                if bar.get_width() > 10:
                    plt.text(bar.get_width()/2, bar.get_y() + bar.get_height()/2, 
                            f"{durations[i]}天", 
                            va='center', ha='center', color='black', fontweight='bold')
                else:
                    plt.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2, 
                            f"{durations[i]}天", 
                            va='center', ha='left', color='black')
            
            if current_stage:
                current_stage_name = current_stage["阶段"]
                for i, stage_name in enumerate(stages):
                    if current_stage_name == stage_name:
                        # 确保颜色索引有效
                        if i < len(bars): 
                            bars[i].set_color('orange')
                            
                            # 智能计算标注位置
                            w = bars[i].get_width()
                            bar_y = bars[i].get_y()
                            bar_height = bars[i].get_height()
                            
                            # 根据条形图宽度智能选择标注位置
                            if w >= 20:
                                # 宽度足够，标注在条形图内部右侧
                                x = w - 10
                                ha = 'right'
                                color = 'white'
                            elif w >= 10:
                                # 中等宽度，标注在条形图中央
                                x = w / 2
                                ha = 'center'
                                color = 'white'
                            else:
                                # 宽度较小，标注在条形图外部右侧
                                x = w + 5
                                ha = 'left'
                                color = 'red'
                            
                            plt.text(x, bar_y + bar_height/2, 
                                    "当前", 
                                    va='center', ha=ha, color=color, 
                                    fontweight='bold', fontsize=10,
                                    bbox=dict(boxstyle="round,pad=0.3", fc='red', alpha=0.8, edgecolor='darkred'))
                        else:
                            logger.warning(f"索引 {i} 超出 bars 列表范围 (长度 {len(bars)})，无法高亮当前阶段 '{current_stage_name}'")
                        break
            
            # 设置图表属性
            plt.title('小麦生育阶段时间分布', fontsize=14)
            plt.xlabel('持续天数', fontsize=12)
            plt.grid(axis='x', linestyle='--', alpha=0.7)
            plt.gca().invert_yaxis()
            plt.tight_layout()
            
            # 保存图表
            os.makedirs(images_dir, exist_ok=True)
            growth_stages_img_path = os.path.join(images_dir, 'growth_stages.png')
            
            plt.savefig(growth_stages_img_path, dpi=config.DPI, bbox_inches='tight')
            plt.close()
        
        logger.info(f"生育期可视化图表已保存到: {growth_stages_img_path}")
        return growth_stages_img_path
        
    except Exception as e:
        logger.error(f"创建生育期可视化图表时出错: {str(e)}", exc_info=True)
        if plt.get_fignums():
            plt.close()
        raise

def analyze_growth_stages(daily_crop_growth):
    """分析小麦生育期，确保日期完全连续"""
    logger.info("===== 小麦生育阶段分析（冠层覆盖度） =====")
    from config import current_config
    config = current_config().AQUACROP_CONFIG
    growth_stages = config.get('GROWTH_STAGES_CANOPY_COVER', [
        #保留默认值防御
        {"阶段": "播种-出苗期", "min_cc": 0, "max_cc": 0.07},
        {"阶段": "出苗-分蘖期", "min_cc": 0.07, "max_cc": 0.3},
        {"阶段": "分蘖-越冬期", "min_cc": 0.3, "max_cc": 0.5},
        {"阶段": "返青-拔节期", "min_cc": 0.5, "max_cc": 0.8},
        {"阶段": "拔节-抽穗期", "min_cc": 0.8, "max_cc": 0.95},
        {"阶段": "抽穗-成熟期", "min_cc": 0.95, "max_cc": 1.0}
    ])
    
    # 归一化列名，确保使用统一的列名
    df = _normalize_column_names(daily_crop_growth)
    df = df.sort_values("Date")
    
    stage_ranges = []
    
    for i, stage in enumerate(growth_stages):
        # 对于最后一个阶段，使用闭区间包含最大值
        if i == len(growth_stages) - 1:
            stage_data = df[(df["_cc"] >= stage["min_cc"]) & (df["_cc"] <= stage["max_cc"])]
        else:
            stage_data = df[(df["_cc"] >= stage["min_cc"]) & (df["_cc"] < stage["max_cc"])]
        
        if not stage_data.empty:
            stage_ranges.append({
                "阶段": stage["阶段"],
                "原始开始日期": stage_data["Date"].min(),
                "原始结束日期": stage_data["Date"].max(),
                "开始DAP": stage_data["_dap"].min(),
                "结束DAP": stage_data["_dap"].max()
            })
    
    if len(stage_ranges) < 2:
        logger.warning("未找到足够的生育阶段数据，无法分析")
        return []
    
    stage_order = {stage["阶段"]: i for i, stage in enumerate(growth_stages)}
    stage_ranges.sort(key=lambda x: stage_order.get(x["阶段"], 99))
    
    logger.info("原始阶段日期范围:")
    for stage in stage_ranges:
        logger.info(f"{stage['阶段']}: {stage['原始开始日期'].strftime('%Y-%m-%d')} 至 {stage['原始结束日期'].strftime('%Y-%m-%d')} (DAP: {stage['开始DAP']:.1f}-{stage['结束DAP']:.1f})")
    
    stage_results = []
    
    current_start_date = stage_ranges[0]["原始开始日期"]
    current_start_dap = stage_ranges[0]["开始DAP"]
    
    for i, stage in enumerate(stage_ranges):
        if i == len(stage_ranges) - 1:
            end_date = stage["原始结束日期"]
            end_dap = stage["结束DAP"]
        else:
            next_start_date = stage_ranges[i+1]["原始开始日期"]
            
            if stage["原始结束日期"] >= next_start_date:
                end_date = next_start_date - pd.Timedelta(days=1)
                end_day_data = df[df["Date"] <= end_date].iloc[-1] if not df[df["Date"] <= end_date].empty else None
                end_dap = end_day_data["_dap"] if end_day_data is not None else stage["结束DAP"]
            else:
                end_date = next_start_date - pd.Timedelta(days=1)
                end_day_data = df[df["Date"] <= end_date].iloc[-1] if not df[df["Date"] <= end_date].empty else None
                end_dap = end_day_data["_dap"] if end_day_data is not None else stage["结束DAP"]
        
        duration = (end_date - current_start_date).days + 1
        
        if duration > 0:
            stage_results.append({
                "阶段": stage["阶段"],
                "开始日期": current_start_date,
                "结束日期": end_date,
                "开始DAP": current_start_dap,
                "结束DAP": end_dap,
                "持续天数": duration
            })
            
            logger.info(f"{stage['阶段']}: {current_start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}，持续{duration}天 (DAP: {current_start_dap:.1f}-{end_dap:.1f})")
            
            if i < len(stage_ranges) - 1:
                current_start_date = end_date + pd.Timedelta(days=1)
                next_day_data = df[df["Date"] >= current_start_date].iloc[0] if not df[df["Date"] >= current_start_date].empty else None
                current_start_dap = next_day_data["_dap"] if next_day_data is not None else end_dap + 1
    
    is_continuous = True
    for i in range(1, len(stage_results)):
        prev_end = stage_results[i-1]["结束日期"]
        curr_start = stage_results[i]["开始日期"]
        
        days_diff = (curr_start - prev_end).days
        
        if days_diff != 1:
            is_continuous = False
            logger.warning(f"连续性检查失败! {stage_results[i-1]['阶段']}结束于{prev_end.strftime('%Y-%m-%d')}，{stage_results[i]['阶段']}开始于{curr_start.strftime('%Y-%m-%d')}，间隔{days_diff}天")
    
    if is_continuous:
        logger.info("验证成功: 所有生育期日期完全连续!")
    
    if stage_results:
        total_start_date = stage_results[0]["开始日期"]
        total_end_date = stage_results[-1]["结束日期"]
        total_duration = (total_end_date - total_start_date).days + 1
        logger.info(f"总生育期: {total_start_date.strftime('%Y-%m-%d')} 至 {total_end_date.strftime('%Y-%m-%d')}，共{total_duration}天")
    
    return stage_results

def run_model_and_save_results() -> Dict:
    """运行模型并保存结果
    
    该函数执行以下操作：
    1. 加载并转换气象数据
    2. 初始化模型参数
    3. 运行模型仿真
    4. 生成可视化图表
    5. 保存结果数据
    
    Returns:
        Dict: 包含以下键值对的字典：
            - stage_results: 生育期阶段列表
            - current_stage: 当前生育阶段信息
            - canopy_cover_img: 冠层覆盖度图表路径
            - growth_stages_img: 生育期分布图表路径
            
    Raises:
        ValueError: 当必要的输入文件缺失时
        RuntimeError: 当模型运行失败时
    """
    try:
        logger.info("开始运行模型并保存结果")
        
        model_irr_dir = os.path.dirname(__file__)
        project_root = os.path.abspath(os.path.join(model_irr_dir, '../../'))
        sys.path.append(project_root)
        
        from config import current_config
        config = current_config().AQUACROP_CONFIG
        fao_config = current_config().FAO_CONFIG
        
        # 配置校验
        validate_config(config)
        
        # 使用配置中的图像目录路径
        images_dir = os.path.join(project_root, config['IMAGES_DIR'])
        os.makedirs(images_dir, exist_ok=True)
        
        # 转换气象数据 - 优先使用.wth文件
        output_txt_path = os.path.join(project_root, config['WEATHER_OUTPUT_TXT'])
        
        # 尝试使用.wth文件，如果不存在则回退到使用CSV文件
        input_wth_path = os.path.join(project_root, fao_config['TEMP_WEATHER_FILE'])
        if os.path.exists(input_wth_path):
            logger.info(f"使用.wth格式气象文件: {input_wth_path}")
            converted_file = convert_irrigation_weather_to_aquacrop_format(input_wth_path, output_txt_path, config)
        else:
            input_csv_path = os.path.join(project_root, config['WEATHER_INPUT_CSV'])
            if not os.path.exists(input_csv_path):
                raise FileNotFoundError(f"未找到任何有效的气象数据文件: 既不存在.wth文件 {input_wth_path} 也不存在CSV文件 {input_csv_path}")
            logger.info(f"使用CSV格式气象文件: {input_csv_path}")
            converted_file = convert_irrigation_weather_to_aquacrop_format(input_csv_path, output_txt_path, config)
            
        # 获取文件路径，添加错误处理
        try:
            filepath = get_filepath(converted_file)
            logger.debug(f"获取到气象文件路径: {filepath}")
        except Exception as e:
            logger.error(f"获取气象文件路径失败: {str(e)}")
            # 如果get_filepath失败，直接使用转换后的文件路径
            filepath = converted_file
            logger.info(f"使用转换后的文件路径: {filepath}")
        
        # 验证文件是否存在
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"气象文件不存在: {filepath}")
        
        # 准备气象数据
        try:
            weather_data = prepare_weather(filepath)
            logger.info(f"成功加载气象数据，共 {len(weather_data)} 条记录")
        except Exception as e:
            logger.error(f"准备气象数据失败: {str(e)}")
            raise
        weather_data["Date"] = pd.to_datetime(weather_data["Date"])
        
        # 初始化模型参数
        initWC = InitialWaterContent(
            wc_type=config['INITIAL_WC_TYPE'],
            method=config['INITIAL_WC_METHOD'],
            depth_layer=config['INITIAL_WC_DEPTH_LAYER'],
            value=config['INITIAL_WC_VALUE']
        )
        
        # 设置土壤参数
        # method1：传感器-获取水力特征参数
        try:
            from src.devices.soil_sensor import SoilSensor
            # 正确获取灌溉配置
            irrigation_config = current_config().IRRIGATION_CONFIG
            device_id = irrigation_config.get('DEFAULT_DEVICE_ID', '16031600028481')
            field_id = irrigation_config.get('DEFAULT_FIELD_ID', '1810564502987649024')
            
            soil_sensor = SoilSensor(device_id, field_id)
            soil_params = soil_sensor.get_current_data()
            
            # 使用传感器数据，如果获取失败则使用配置值
            thS = soil_params.get('sat', config['SOIL_SATURATION'])
            thFC = soil_params.get('fc', config['SOIL_FIELD_CAPACITY'])
            thWP = soil_params.get('pwp', config['SOIL_WILTING_POINT'])
            
            logger.info(f"使用土壤传感器参数: 饱和含水量={thS}, 田间持水量={thFC}, 凋萎点={thWP}")
        except Exception as e:
            logger.warning(f"获取土壤传感器数据失败，使用配置文件默认值: {str(e)}")
            thS = config['SOIL_SATURATION']
            thFC = config['SOIL_FIELD_CAPACITY']
            thWP = config['SOIL_WILTING_POINT']
            logger.info(f"使用配置文件参数: 饱和含水量={thS}, 田间持水量={thFC}, 凋萎点={thWP}")
        
        # 验证土壤参数的合理性
        if not (0 < thWP < thFC < thS < 1):
            logger.warning("土壤参数不符合物理规律 (PWP < FC < SAT)，使用配置文件默认值")
            thS = config['SOIL_SATURATION']
            thFC = config['SOIL_FIELD_CAPACITY']
            thWP = config['SOIL_WILTING_POINT']

        soil_texture = Soil(soil_type=config['SOIL_TEXTURE'])
        
        # 计算每层的厚度，避免重复累计
        total_depth = soil_texture.zSoil
        model_config = ModelConfig()
        layer_thickness = total_depth / model_config.SOIL_LAYERS
        
        for i in range(model_config.SOIL_LAYERS):
            soil_texture.add_layer(
                thickness=layer_thickness,
                thWP=thWP,
                thFC=thFC,
                thS=thS,
                Ksat=config['SOIL_KSAT'],
                penetrability=config['SOIL_PENETRABILITY']
            )
        # method2:经纬度-获取水力特征参数

        # 设置作物参数
        set_crop = Crop(config['CROP_NAME'], planting_date=config['PLANTING_DATE'])
        
        # 设置灌溉管理
        irr_freq = normalize_irr_frequency(config['IRR_FREQUENCY'])
        irr_dates = pd.date_range(
            start=config['SIM_START_TIME'],
            end=config['SIM_END_TIME'],
            freq=irr_freq
        )
        irr_schedule = pd.DataFrame({
            "Date": irr_dates,
            "Depth": [config['IRR_DEPTH']] * len(irr_dates)
        })
        # 增强兼容性：将Date列转为datetime.date格式（有些版本要求纯date而非Timestamp）
        irr_schedule["Date"] = pd.to_datetime(irr_schedule["Date"]).dt.date
        # 使用标准的灌溉管理设置方式
        try:
            # 尝试使用Schedule参数（如果库支持）
            irr_mngt = IrrigationManagement(irrigation_method=1, Schedule=irr_schedule)
        except TypeError:
            # 如果不支持Schedule参数，使用标准方式
            logger.warning("IrrigationManagement不支持Schedule参数，使用标准irrigation_method=1")
            irr_mngt = IrrigationManagement(irrigation_method=1)
            # 如果库有其他方式设置日程，可以在这里添加
            if hasattr(irr_mngt, 'schedule'):
                irr_mngt.schedule = irr_schedule
            elif hasattr(irr_mngt, 'set_schedule'):
                irr_mngt.set_schedule(irr_schedule)
        
        # 创建并运行模型
        model = AquaCropModel(
            sim_start_time=config['SIM_START_TIME'],
            sim_end_time=config['SIM_END_TIME'],
            weather_df=weather_data,
            soil=soil_texture,
            crop=set_crop,
            initial_water_content=initWC,
            irrigation_management=irr_mngt
        )
        
        logger.info("开始运行模型仿真")
        model.run_model(till_termination=True)
        logger.info("模型仿真完成")
        
        # 获取模型结果
        daily_water_flux = model.get_water_flux()
        daily_water_storage = model.get_water_storage()
        daily_crop_growth = model.get_crop_growth()
        model_result = model.get_simulation_results()
        
        # 保存结果
        output_dir = os.path.join(project_root, config['OUTPUT_DIR'])
        os.makedirs(output_dir, exist_ok=True)
        
        # 使用安全的Date列处理函数
        start_date = pd.to_datetime(config['SIM_START_TIME'])
        daily_crop_growth = _ensure_date_col(daily_crop_growth, start_date)
        daily_water_storage = _ensure_date_col(daily_water_storage, start_date)
        daily_water_flux = _ensure_date_col(daily_water_flux, start_date)
        
        # 保存数据文件
        daily_crop_growth.to_csv(os.path.join(output_dir, "daily_crop_growth.csv"), index=False)
        daily_water_storage.to_csv(os.path.join(output_dir, "daily_water_storage.csv"), index=False)
        daily_water_flux.to_csv(os.path.join(output_dir, "aquacrop_daily_water_flux.csv"), index=False)
        
        # 健壮的产量字段处理，支持不同版本的列名
        yield_col = 'Dry yield (tonne/ha)'
        if isinstance(model_result, pd.DataFrame) and yield_col in model_result.columns:
            yield_output = model_result[yield_col].mean()
            logger.info(f"预计产量: {yield_output:.2f} 吨/公顷")
        else:
            # 尝试其他可能的产量列名
            possible_yield_cols = [
                'Dry yield (tonne/ha)',
                'Dry yield',
                'Yield (tonne/ha)',
                'Yield',
                'dry_yield',
                'yield_tonne_ha'
            ]
            yield_output = float('nan')
            for col in possible_yield_cols:
                if isinstance(model_result, pd.DataFrame) and col in model_result.columns:
                    yield_output = model_result[col].mean()
                    logger.info(f"预计产量: {yield_output:.2f} 吨/公顷 (使用列: {col})")
                    break
            
            if pd.isna(yield_output):
                logger.warning(f"未找到有效的产量列，可用列: {list(model_result.columns) if isinstance(model_result, pd.DataFrame) else 'N/A'}")
                yield_output = 0.0
        
        # 创建冠层覆盖度图表 - 检查是否有非零数据
        # 归一化列名，确保使用统一的列名
        daily_crop_growth_normalized = _normalize_column_names(daily_crop_growth)
        daily_crop_growth_filtered = daily_crop_growth_normalized[daily_crop_growth_normalized["_cc"] != 0]
        
        # 使用配置化的matplotlib参数
        model_config = ModelConfig()
        rc_params = model_config.get_matplotlib_rc_params()
        rc_params.update({
            'font.size': 12
        })
        
        canopy_cover_img_path = os.path.join(images_dir, 'canopy_cover.png')
        
        if daily_crop_growth_filtered.empty:
            logger.warning("冠层覆盖度全为0，创建空状态图表")
            with plt.rc_context(rc_params):
                plt.figure(figsize=model_config.CHART_FIGSIZE)
                plt.text(0.5, 0.5, '冠层覆盖度数据全为0\n暂无可显示内容', 
                         ha='center', va='center', transform=plt.gca().transAxes,
                         fontsize=16, color='gray')
                plt.title('小麦生长过程中的冠层覆盖度变化', fontsize=14)
                plt.xlabel('播种后天数 (DAP)', fontsize=12, fontweight='bold')
                plt.ylabel('冠层覆盖度', fontsize=12, fontweight='bold')
                plt.grid(True, linestyle='--', alpha=0.3)
                plt.tight_layout(pad=2.0)
                plt.savefig(canopy_cover_img_path, dpi=model_config.DPI, bbox_inches='tight')
        else:
            with plt.rc_context(rc_params):
                plt.figure(figsize=model_config.CHART_FIGSIZE)
                plt.plot(daily_crop_growth_filtered["_dap"].values,
                         daily_crop_growth_filtered["_cc"].values,
                         label='冠层覆盖度',
                         marker='o',
                         color='green',
                         linewidth=2,
                         markersize=4)
                plt.title('小麦生长过程中的冠层覆盖度变化', fontsize=14)
                plt.xlabel('播种后天数 (DAP)', fontsize=12, fontweight='bold')
                plt.ylabel('冠层覆盖度', fontsize=12, fontweight='bold')
                plt.grid(True, linestyle='--', alpha=0.7)
                plt.legend(fontsize=12)
                plt.tight_layout(pad=2.0)  # 增加边距，防止文字被截断
                plt.savefig(canopy_cover_img_path, dpi=model_config.DPI, bbox_inches='tight')
        
        # 两个分支都savefig后统一close，避免内存泄漏
        plt.close()
        
        # 获取图片的相对路径用于前端显示，从配置读取URL前缀
        static_url_prefix = config.get('STATIC_URL_PREFIX', '/static/')
        static_root = config.get('STATIC_ROOT', None)
        canopy_img_web_path = _get_web_path(canopy_cover_img_path, images_dir, static_url_prefix, static_root)
        
        logger.info(f"冠层覆盖度图表文件已保存到: {canopy_cover_img_path}")
        logger.info(f"冠层覆盖度图表Web路径: {canopy_img_web_path}")
        
        # 分析生育期
        stage_results = analyze_growth_stages(daily_crop_growth)
        if not stage_results:
            logger.warning("使用基于DAP的标准生育期")
            stage_results = get_growth_stages_from_model(daily_crop_growth)
        
        # 保存生育期数据
        stage_df = pd.DataFrame(stage_results)
        growth_stages_path = os.path.join(project_root, config['OUTPUT_DIR'], 'growth_stages.csv')
        stage_df.to_csv(growth_stages_path, index=False)
        logger.info(f"生育期数据已保存到: {growth_stages_path}")
        
        # 获取当前生育阶段
        current_stage = get_current_growth_stage(stage_results)
        
        # 保存当前生育阶段信息
        with open(os.path.join(images_dir, 'current_growth_stage.json'), 'w', encoding='utf-8') as f:
            json.dump(current_stage, f, ensure_ascii=False, indent=2)
        
        # 生成生育期图表
        growth_stages_img_path = create_growth_stages_visualization(stage_results, current_stage, images_dir)
        growth_stages_img_web_path = _get_web_path(growth_stages_img_path, images_dir, static_url_prefix, static_root)
        
        logger.info("模型运行和结果保存完成")
        return {
            "stage_results": stage_results,
            "current_stage": current_stage,
            "canopy_cover_img": canopy_img_web_path,
            "growth_stages_img": growth_stages_img_web_path
        }
        
    except Exception as e:
        logger.error(f"模型运行过程中出错: {str(e)}", exc_info=True)
        raise

def get_root_depth_data() -> Optional[List[Dict[str, Union[str, float]]]]:
    """获取根系深度历史数据用于图表
    
    Returns:
        Optional[List[Dict[str, Union[str, float]]]]: 包含日期和根系深度的字典列表,
            如果获取失败则返回None
    """
    try:
        logger.info("开始获取根系深度历史数据")
        
        # 从配置中获取OUTPUT_DIR，确保与保存路径一致
        model_irr_dir = os.path.dirname(__file__)
        project_root = os.path.abspath(os.path.join(model_irr_dir, '../../'))
        sys.path.append(project_root)
        from config import current_config
        
        cfg = current_config().AQUACROP_CONFIG
        output_dir = os.path.join(project_root, cfg['OUTPUT_DIR'])
        crop_growth_file = os.path.join(output_dir, 'daily_crop_growth.csv')
        crop_growth_file = os.path.abspath(crop_growth_file)
        
        if not os.path.exists(crop_growth_file):
            logger.warning(f"根系深度数据文件不存在: {crop_growth_file}")
            return None
        
        df = pd.read_csv(crop_growth_file)
        
        required_columns = ['Date', 'RZ']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            logger.warning(f"根系深度数据文件缺少必要列: {missing_columns}")
            return None
        
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date')
        
        results = []
        for _, row in df.iterrows():
            results.append({
                'date': row['Date'].strftime('%Y-%m-%d'),
                'root_depth': round(row['RZ'], 2) if not pd.isna(row['RZ']) else 0
            })
        
        logger.info(f"成功获取 {len(results)} 条根系深度历史数据")
        return results
        
    except Exception as e:
        logger.error(f"获取根系深度历史数据失败: {str(e)}", exc_info=True)
        return None

if __name__ == '__main__':
    try:
        # 设置日志文件路径
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        log_file = os.path.join(log_dir, f'aquacrop_{datetime.datetime.now().strftime("%Y%m%d")}.log')
        
        # 重新配置日志器以包含文件输出
        logger = setup_logger(__name__, level=logging.INFO, log_file=log_file)
        
        logger.info("=" * 50)
        logger.info("AquaCrop 模型开始运行")
        logger.info("=" * 50)
        
        run_model_and_save_results()
        
        logger.info("=" * 50)
        logger.info("AquaCrop 模型运行完成")
        logger.info("=" * 50)
        
    except Exception as e:
        logger.error(f"程序运行失败: {str(e)}", exc_info=True)
        sys.exit(1)