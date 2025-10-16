"""
天气数据处理模块：
1. 获取历史天气数据
2. 获取未来15天天气预报
3. 格式：实际值+预测数据+历史均值
### 1. WEATHER_CONFIG (20个参数) 地理位置参数
- latitude - 纬度 (默认值: 35)
- longitude - 经度 (默认值: 113) 作物类型参数 (1个)
- crop_type - 作物类型 (默认值: 'wheat') 小麦生长季参数 (4个)
- wheat_season_start_month - 小麦生长季开始月份 (默认值: 10)
- wheat_season_start_day - 小麦生长季开始日期 (默认值: 1)
- wheat_season_end_month - 小麦生长季结束月份 (默认值: 6)
- wheat_season_end_day - 小麦生长季结束日期 (默认值: 1) 玉米生长季参数 (4个)
- corn_season_start_month - 玉米生长季开始月份 (默认值: 7)
- corn_season_start_day - 玉米生长季开始日期 (默认值: 1)
- corn_season_end_month - 玉米生长季结束月份 (默认值: 9)
- corn_season_end_day - 玉米生长季结束日期 (默认值: 30) 棉花生长季参数 (4个)
- cotton_season_start_month - 棉花生长季开始月份 (默认值: 4)
- cotton_season_start_day - 棉花生长季开始日期 (默认值: 10)
- cotton_season_end_month - 棉花生长季结束月份 (默认值: 10)
- cotton_season_end_day - 棉花生长季结束日期 (默认值: 31) API请求参数 (3个)
- history_years - 历史数据年数 (默认值: 5)
- api_timeout - API请求超时时间(默认值: 15)
- max_retries - API请求最大重试次数 (默认值: 3) 历史数据处理参数 (2个)
- wheat_season_start_month - 用于历史数据筛选 (默认值: 8,在 is_after_forecast 函数中)
- wheat_season_end_month - 用于历史数据筛选 (默认值: 7,在 is_after_forecast 函数中)
- wheat_season_end_day - 用于历史数据筛选 (默认值: 31,在 is_after_forecast 函数中)
"""
import os
import sys
import requests
import pandas as pd 
import numpy as np
import datetime
import logging

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(project_root)

try:
    from src.config.config import get_config
    config = get_config()
    logger = logging.getLogger(__name__)
except ImportError:
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    logger.warning("无法导入配置模块，将使用默认配置")
    
    class EmptyConfig:
        def __init__(self):
            self.WEATHER_CONFIG = {}
    config = EmptyConfig()

if not hasattr(config, 'WEATHER_CONFIG'):
    config.WEATHER_CONFIG = {
        'latitude': 35,
        'longitude': 113,
        'crop_type': 'wheat',  # 作物类型：wheat, corn, cotton
        'wheat_season_start_month': 10,    # 小麦生长季开始月份
        'wheat_season_start_day': 1,      # 小麦生长季开始日期
        'wheat_season_end_month': 6,      # 小麦生长季结束月份
        'wheat_season_end_day': 1,       # 小麦生长季结束日期
        'corn_season_start_month': 7,     # 玉米生长季开始月份
        'corn_season_start_day': 1,      # 玉米生长季开始日期
        'corn_season_end_month': 9,       # 玉米生长季结束月份
        'corn_season_end_day': 30,        # 玉米生长季结束日期
        'cotton_season_start_month': 4,   # 棉花生长季开始月份
        'cotton_season_start_day': 10,    # 棉花生长季开始日期
        'cotton_season_end_month': 10,    # 棉花生长季结束月份
        'cotton_season_end_day': 31,      # 棉花生长季结束日期
        'history_years': 5,               # 历史数据年数
        'api_timeout': 15,                # API请求超时时间（秒）
        'max_retries': 3                  # API请求最大重试次数
    }
    logger.info("在配置中添加天气模块默认配置")

def get_crop_season_dates(crop_type, current_date):
    """根据作物类型获取生长季日期范围
    
    Args:
        crop_type (str): 作物类型(wheat, corn, cotton)
        current_date (datetime): 当前日期
        
    Returns:
        tuple: (first_year, second_year, start_month, start_day, end_month, end_day)
    """
    current_year = current_date.year
    current_month = current_date.month
    current_day = current_date.day
    
    # 获取作物配置
    crop_config = {
        'wheat': {
            'start_month': config.WEATHER_CONFIG.get('wheat_season_start_month', 10),
            'start_day': config.WEATHER_CONFIG.get('wheat_season_start_day', 1),
            'end_month': config.WEATHER_CONFIG.get('wheat_season_end_month', 6),
            'end_day': config.WEATHER_CONFIG.get('wheat_season_end_day', 1),
            'cross_year': True
        },
        'corn': {
            'start_month': config.WEATHER_CONFIG.get('corn_season_start_month', 7),
            'start_day': config.WEATHER_CONFIG.get('corn_season_start_day', 1),
            'end_month': config.WEATHER_CONFIG.get('corn_season_end_month', 9),
            'end_day': config.WEATHER_CONFIG.get('corn_season_end_day', 30),
            'cross_year': False
        },
        'cotton': {
            'start_month': config.WEATHER_CONFIG.get('cotton_season_start_month', 4),
            'start_day': config.WEATHER_CONFIG.get('cotton_season_start_day', 10),
            'end_month': config.WEATHER_CONFIG.get('cotton_season_end_month', 10),
            'end_day': config.WEATHER_CONFIG.get('cotton_season_end_day', 31),
            'cross_year': False
        }
    }
    
    if crop_type not in crop_config:
        raise ValueError(f"不支持的作物类型: {crop_type}")
    
    crop = crop_config[crop_type]
    
    if crop['cross_year']:
        # 跨年作物
        if (current_month > crop['start_month'] or 
            (current_month == crop['start_month'] and current_day >= crop['start_day'])):
            first_year = current_year
            second_year = current_year + 1
        else:
            first_year = current_year - 1
            second_year = current_year
    else:
        # 不跨年作物
        first_year = current_year
        second_year = current_year
    
    return (first_year, second_year, crop['start_month'], crop['start_day'],
            crop['end_month'], crop['end_day'])


def fetch_weather_history(lat, lon, start_date, end_date, max_retries=None):
    """获取历史天气数据
    Args:
        lat (float): 纬度
        lon (float): 经度
        start_date (str): 开始日期,格式YYYYMMDD
        end_date (str): 结束日期,格式YYYYMMDD
        max_retries (int, optional): 最大重试次数
        
    Returns:
        dict: 包含天气数据的字典,请求失败时返回None
    """
    max_retries = max_retries or config.WEATHER_CONFIG.get('max_retries', 3)
    api_timeout = config.WEATHER_CONFIG.get('api_timeout', 15)
    
    url = f"http://data-api.91weather.com/Zoomlion/goso_day?lat={lat}&lon={lon}&start={start_date}&end={end_date}"
    
    for retry in range(max_retries):
        try:
            logger.info(f"获取历史天气数据: 从{start_date}到{end_date}")
            response = requests.get(url, timeout=api_timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            if retry < max_retries - 1:
                logger.warning(f"获取历史天气数据失败，正在重试 ({retry+1}/{max_retries}): {str(e)}")
                continue
            else:
                logger.error(f"获取历史天气数据失败: {str(e)}")
                return None


def fetch_weather_forecast(lat, lon, max_retries=None):
    """获取未来15天天气预报
    Args:
        lat (float): 纬度
        lon (float): 经度
        max_retries (int, optional): 最大重试次数
        
    Returns:
        dict: 包含天气预报数据的字典,请求失败时返回None
    """
    max_retries = max_retries or config.WEATHER_CONFIG.get('max_retries', 3)
    api_timeout = config.WEATHER_CONFIG.get('api_timeout', 15)
    
    url = f"http://data-api.91weather.com/Zoomlion/higf_day_plus?lat={lat}&lon={lon}"
    
    for retry in range(max_retries):
        try:
            logger.info(f"获取未来15天天气预报: 经度={lon}, 纬度={lat}")
            response = requests.get(url, timeout=api_timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            if retry < max_retries - 1:
                logger.warning(f"获取天气预报失败，正在重试 ({retry+1}/{max_retries}): {str(e)}")
                continue
            else:
                logger.error(f"获取天气预报失败: {str(e)}")
                return None


def is_after_forecast(row, second_year):
    """判断日期是否在预报期之后（用于筛选历史数据）
    
    Args:
        row (pd.Series): 包含datetime字段的数据行
        second_year (int): 第二年年份（小麦生长季的第二年）
        
    Returns:
        bool: 如果日期在预报期之后且需要该历史数据,则返回True
    """
    history_years = config.WEATHER_CONFIG.get('history_years', 5)
    wheat_season_start_month = config.WEATHER_CONFIG.get('wheat_season_start_month', 8)
    wheat_season_end_month = config.WEATHER_CONFIG.get('wheat_season_end_month', 7)
    wheat_season_end_day = config.WEATHER_CONFIG.get('wheat_season_end_day', 31)
    
    year = row['datetime'].year
    row_date = (row['datetime'].month, row['datetime'].day)
    
    forecast_end_date = datetime.datetime.now() + datetime.timedelta(days=14)
    forecast_end_date_tuple = (forecast_end_date.month, forecast_end_date.day)

    first_history_year = datetime.datetime.now().year - history_years
    
    season_end_date = (wheat_season_end_month, wheat_season_end_day)
    
    # 检查日期是否合理-处理闰年问题
    try:
        pd.to_datetime(f'{second_year}-{row["datetime"].month:02d}-{row["datetime"].day:02d}')
        date_is_valid = True
    except ValueError:
        date_is_valid = False
    
    # 如果日期无效(如非闰年的2月29日),直接返回False
    if not date_is_valid:
        return False
    
    current_month = datetime.datetime.now().month
    
    if current_month < wheat_season_start_month:
        if (season_end_date >= row_date > forecast_end_date_tuple and 
            year >= first_history_year):
            return True
    else:
        if ((row_date > forecast_end_date_tuple) or 
            (row_date <= season_end_date and year > first_history_year)):
            return True
    
    return False


def add_year(row, first_year, second_year):
    """根据月日为历史平均数据添加年份
    
    Args:
        row (pd.Series): 数据行（包含月日信息）
        first_year (int): 第一年年份
        second_year (int): 第二年年份
        
    Returns:
        pd.Series: 添加了年份的数据行
    """
    month, day = row["datetime"]
    
    wheat_season_end_month = config.WEATHER_CONFIG.get('wheat_season_end_month', 7)
    wheat_season_end_day = config.WEATHER_CONFIG.get('wheat_season_end_day', 31)
    season_end_date = (wheat_season_end_month, wheat_season_end_day)
    
    if (month, day) > season_end_date:
        row["datetime"] = pd.to_datetime(f'{first_year}{month:02d}{day:02d}', format="%Y%m%d")
    else:
        row["datetime"] = pd.to_datetime(f'{second_year}{month:02d}{day:02d}', format="%Y%m%d")
    
    return row


def prepare_weather_data(lat=None, lon=None, crop_type=None, output_file=None, 
                        history_file=None):
    """准备作物灌溉所需的天气数据
    
    将历史数据、当前实际数据和未来预测数据合并为完整的天气数据集
    
    Args:
        lat (float, optional): 纬度，默认使用配置值
        lon (float, optional): 经度，默认使用配置值
        crop_type (str, optional): 作物类型，默认使用配置值
        output_file (str, optional): 输出文件名
        history_file (str, optional): 历史数据文件名
        
    Returns:
        pd.DataFrame: 准备好的天气数据,失败时返回None
    """
    try:
        # 使用配置值或提供的参数
        latitude = lat if lat is not None else config.WEATHER_CONFIG.get('latitude', 35)
        longitude = lon if lon is not None else config.WEATHER_CONFIG.get('longitude', 113)
        crop_type = crop_type if crop_type is not None else config.WEATHER_CONFIG.get('crop_type', 'wheat')
        
        # 确保data/weather目录存在
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        weather_dir = os.path.join(project_root, 'data/weather')
        os.makedirs(weather_dir, exist_ok=True)
        
        # 如果没有提供文件路径，使用默认的带完整路径的文件名
        if output_file is None:
            output_file = os.path.join(weather_dir, 'irrigation_weather.csv')
        elif not os.path.isabs(output_file):
            output_file = os.path.join(weather_dir, output_file)
            
        if history_file is None:
            history_file = os.path.join(weather_dir, 'weather_history_data.csv')
        elif not os.path.isabs(history_file):
            history_file = os.path.join(weather_dir, history_file)
        
        current_date = datetime.datetime.now()
        
        # 获取作物生长季日期范围
        first_year, second_year, start_month, start_day, end_month, end_day = get_crop_season_dates(crop_type, current_date)
        
        logger.info(f"确定{crop_type}生长季: 第一年={first_year}, 第二年={second_year}")
        
        # 生成日期范围字符串
        model_start_date = f"{first_year}{start_month:02d}{start_day:02d}"
        current_date_str = current_date.strftime("%Y%m%d")
        history_years = config.WEATHER_CONFIG.get('history_years', 5)
        history_start_date = f"{first_year - history_years}{start_month:02d}{start_day:02d}"
        model_end_date = f"{second_year}{end_month:02d}{end_day:02d}"
        
        weather_current = fetch_weather_history(latitude, longitude, model_start_date, current_date_str)
        weather_forecast = fetch_weather_forecast(latitude, longitude)
        weather_history = fetch_weather_history(latitude, longitude, history_start_date, current_date_str)
        
        if not all([weather_current, weather_forecast, weather_history]):
            logger.error("一个或多个数据源获取失败")
            return None
        
        weather_current_data = pd.DataFrame(weather_current['data'])
        weather_current_data['datetime'] = pd.to_datetime(weather_current_data['datetime'], format='%Y%m%d')
        
        weather_history_data = pd.DataFrame(weather_history['data'])
        weather_history_data['datetime'] = pd.to_datetime(weather_history_data['datetime'], format='%Y%m%d')
        
        weather_history_data = weather_history_data[
            weather_history_data.apply(is_after_forecast, axis=1, args=(second_year,))]
        
        logger.info(f"保存历史天气数据到文件: {history_file}")
        weather_history_data.to_csv(history_file, encoding="utf-8", index=False)
        
        daily_avg = weather_history_data.groupby([
            weather_history_data['datetime'].dt.month, 
            weather_history_data['datetime'].dt.day]).mean(numeric_only=True)
        
        daily_avg["datetime"] = daily_avg.index
        daily_avg = daily_avg.apply(add_year, axis=1, args=(first_year, second_year))
        daily_avg.set_index("datetime", drop=True, inplace=True)
        daily_avg = daily_avg.sort_values(by="datetime")
        
        weather_forecast_data = pd.DataFrame(weather_forecast['data'])
        weather_forecast_data['datetime'] = pd.to_datetime(weather_forecast_data['datatime'], format='%Y%m%d')
        
        weather_forecast_data["nrd"] = weather_forecast_data["nrd"] * 0.0864
        
        forecast_renamed = weather_forecast_data.rename(columns={
            't_max': 'tem_max',
            't_min': 'tem_min',
            'dpt': 'dpt_avg',
            'rh_nax': 'rhu_max',
            'rh_min': 'rhu_min',
            'wins': 'win_s_2mi_avg'
        })
        
        full_date_range = pd.date_range(
            start=model_start_date, end=model_end_date, freq='D').to_frame(index=False, name='datetime')
        
        full_weather_data = full_date_range.join(daily_avg, on=[full_date_range['datetime']])
        full_weather_data.set_index('datetime', inplace=True)
        
        forecast_data = forecast_renamed.set_index('datetime')
        weather_current_data.set_index('datetime', inplace=True)
        
        # 更新数据：历史均值 < 当前实际数据 < 预测数据（优先级顺序）
        data_columns = ['nrd', 'tem_max', 'tem_min', 'dpt_avg', 
                        'rhu_max', 'rhu_min', 'win_s_2mi_avg', 'pre']
        
        for col in data_columns:
            if col in weather_current_data.columns:
                full_weather_data[col].update(weather_current_data[col])
            
            if col in forecast_data.columns:
                full_weather_data[col].update(forecast_data[col])
        
        full_weather_data.reset_index(inplace=True)
        full_weather_data = full_weather_data.rename(columns={
            'nrd': 'Srad',          # 太阳辐射
            'tem_max': 'Tmax',      # 最高温度
            'tem_min': 'Tmin',      # 最低温度
            'dpt_avg': 'Tdew',      # 露点温度
            'rhu_max': 'RHmax',     # 最大相对湿度
            'rhu_min': 'RHmin',     # 最小相对湿度
            'win_s_2mi_avg': 'Wndsp', # 风速
            'pre': 'Rain'           # 降雨量
        })
        
        full_weather_data['Date'] = full_weather_data['datetime'].dt.strftime('%Y-%j')
        full_weather_data.drop('datetime', axis=1, inplace=True)
        
        full_weather_data['Vapr'] = np.nan  # 水汽压
        full_weather_data['Etref'] = np.nan  # 参考蒸散发量
        full_weather_data['MorP'] = 'M'      # 数据类型标志（M表示实测值）
        
        output_columns = ['Date', 'Srad', 'Tmax', 'Tmin', 'Vapr',
                          'Tdew', 'RHmax', 'RHmin', 'Wndsp', 'Rain', 'Etref', 'MorP']
        full_weather_data = full_weather_data[output_columns]
        
        logger.info(f"保存天气数据到文件: {output_file}")
        full_weather_data.to_csv(output_file, index=False)
        
        logger.info(f"天气数据处理完成，共{len(full_weather_data)}条记录")
        return full_weather_data
    
    except Exception as e:
        logger.error(f"处理天气数据时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None


if __name__ == '__main__':
    try:
        # 确保数据目录存在
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        weather_dir = os.path.join(project_root, 'data/weather')
        os.makedirs(weather_dir, exist_ok=True)
        
        # 使用完整路径调用函数
        output_file = os.path.join(weather_dir, 'irrigation_weather.csv')
        history_file = os.path.join(weather_dir, 'weather_history_data.csv')
        
        weather_data = prepare_weather_data(output_file=output_file, history_file=history_file)
        
        if weather_data is not None:
            logger.info("天气数据处理成功")
            print(f"天气数据处理成功,结果已保存到{output_file},共{len(weather_data)}条记录")
        else:
            logger.error("天气数据处理失败")
            print("天气数据处理失败，请查看日志了解详情")
    except Exception as e:
        logger.error(f"运行天气数据处理模块时出错: {str(e)}")
        print(f"处理过程中发生错误: {str(e)}")
