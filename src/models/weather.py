"""
天气数据处理模块

本模块提供天气数据处理和格式转换功能，主要包括：
1. 气象数据验证和清理
2. 参考作物蒸散发量计算(基于FAO-56 Penman-Monteith方程)
3. 天气数据转换为FAO模型所需格式

主要组件:
- clean_weather_data: 天气数据清理和修复函数
- validate_weather_data: 天气数据验证函数
- process_weather_data: 天气数据处理和格式转换函数
- Weather_wth: 兼容旧版接口的天气数据处理函数
- WeatherET: 天气数据处理类,主要用于FAO模型

使用示例:
```python
# 使用WeatherET类处理数据
weather_data = pd.read_csv("irrigation_weather.csv")
wth_et = WeatherET(comment='drought irrigation')
wth_et.customload(weather_data, start_date="2024-001", end_date="2024-365")
wth_et.savefile("weather.wth")

# 直接处理数据文件
process_weather_data("irrigation_weather.csv", "weather.wth", auto_fix=True)

# 使用兼容接口
Weather_wth("input.wth", "output.wth")
```
"""
import os
import sys
import logging
import datetime
import numpy as np
import pandas as pd
import pyfao56

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
        'elevation': float(os.environ.get('WEATHER_STATION_ELEVATION', 100.0)),
        'latitude': float(os.environ.get('WEATHER_LATITUDE', 35.0)),
        'wind_height': float(os.environ.get('WEATHER_STATION_WIND_HEIGHT', 2.0)),
        'reference_crop': os.environ.get('WEATHER_STATION_REFERENCE_CROP', 'S')
    }

def clean_weather_data(df):
    """清理天气数据中的异常值和缺失值
    Args:
        df (pd.DataFrame): 天气数据DataFrame 
    Returns:
        pd.DataFrame: 清理后的数据
    """
    try:
        clean_df = df.copy()
        
        numeric_cols = ['Srad', 'Tmax', 'Tmin', 'Vapr', 'Tdew', 'RHmax', 'RHmin', 'Wndsp', 'Rain']
        for col in numeric_cols:
            if col in clean_df.columns:
                if col == 'Vapr' or col == 'Tdew':
                    clean_df[col] = clean_df[col].fillna(0)
                elif col == 'Rain':
                    clean_df[col] = clean_df[col].fillna(0)
                elif col == 'Wndsp':
                    clean_df[col] = clean_df[col].fillna(2.0)  
                elif col == 'RHmax':
                    clean_df[col] = clean_df[col].fillna(70.0)  
                elif col == 'RHmin':
                    clean_df[col] = clean_df[col].fillna(30.0)  
        
        # 修复逻辑错误: 确保Tmax > Tmin
        mask = clean_df['Tmax'] < clean_df['Tmin']
        if mask.any():
            logger.warning(f"修复{mask.sum()}条记录中最高温度小于最低温度的情况")
            temp = clean_df.loc[mask, 'Tmax'].copy()
            clean_df.loc[mask, 'Tmax'] = clean_df.loc[mask, 'Tmin']
            clean_df.loc[mask, 'Tmin'] = temp
        
        # 修复逻辑错误: 确保RHmax > RHmin
        mask = clean_df['RHmax'] < clean_df['RHmin']
        if mask.any():
            logger.warning(f"修复{mask.sum()}条记录中最大湿度小于最小湿度的情况")
            temp = clean_df.loc[mask, 'RHmax'].copy()
            clean_df.loc[mask, 'RHmax'] = clean_df.loc[mask, 'RHmin']
            clean_df.loc[mask, 'RHmin'] = temp
        
        return clean_df
        
    except Exception as e:
        logger.error(f"清理天气数据时出错: {str(e)}")
        return df  # 如果清理失败，返回原始数据

def validate_weather_data(df):
    """验证气象数据的有效性
    Args:
        df (pd.DataFrame): 天气数据DataFrame
        
    Returns:
        tuple: (bool, str) - (是否有效, 错误信息)
    """
    try:
        # 检查数值范围
        validations = {
            'Tmax': (-50, 60),   
            'Tmin': (-50, 60),
            'RHmax': (0, 100),   
            'RHmin': (0, 100),
            'Wndsp': (0, 150),   
            'Rain': (0, 1000),    
            'Srad': (0, 50)   
        }
        
        for col, (min_val, max_val) in validations.items():
            if col in df.columns:
                invalid = df[df[col].notna() & ((df[col] < min_val) | (df[col] > max_val))]
                if not invalid.empty:
                    return False, f"{col}列包含无效值，应在{min_val}到{max_val}之间"
        
        if 'Tmax' in df.columns and 'Tmin' in df.columns:
            invalid = df[df['Tmax'] < df['Tmin']]
            if not invalid.empty:
                return False, "最高温度小于最低温度"
        
        if 'RHmax' in df.columns and 'RHmin' in df.columns:
            invalid = df[df['RHmax'] < df['RHmin']]
            if not invalid.empty:
                return False, "最大相对湿度小于最小相对湿度"
        
        return True, ""
        
    except Exception as e:
        return False, f"验证天气数据时出错: {str(e)}"

def process_weather_data(input_file, output_file, auto_fix=True):
    """处理天气数据并生成FAO格式的天气文件
    Args:
        input_file (str or pd.DataFrame): 输入文件路径或DataFrame对象
        output_file (str): 输出文件路径
        auto_fix (bool, optional): 是否自动修复数据问题,默认为True
    Returns:
        bool: 处理成功返回True,失败返回False
    """
    try:
        # 读取输入数据
        if isinstance(input_file, pd.DataFrame):
            logger.info(f"处理DataFrame数据并输出到: {output_file}")
            df = input_file.copy()
        else:
            logger.info(f"开始处理天气文件: {input_file}")
            df = pd.read_csv(input_file)
        
        required_columns = ['Date', 'Srad', 'Tmax', 'Tmin', 'RHmax', 'RHmin', 'Wndsp', 'Rain']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"缺少必要的列: {', '.join(missing_columns)}")
        
        is_valid, error_msg = validate_weather_data(df)
        if not is_valid and auto_fix:
            logger.warning(f"天气数据验证失败: {error_msg}，尝试自动修复")
            df = clean_weather_data(df)
            is_valid, error_msg = validate_weather_data(df)
            if not is_valid:
                logger.warning(f"自动修复后仍有问题: {error_msg}")
        elif not is_valid:
            logger.error(f"天气数据验证失败: {error_msg}")
            return False
        
        if 'Vapr' not in df.columns:
            df['Vapr'] = np.nan
        if 'Tdew' not in df.columns:
            df['Tdew'] = np.nan
        if 'MorP' not in df.columns:
            df['MorP'] = 'M'
            
        columns = ['Date', 'Srad', 'Tmax', 'Tmin', 'Vapr', 'Tdew', 
                  'RHmax', 'RHmin', 'Wndsp', 'Rain', 'ETref', 'MorP']
        
        weather = pyfao56.Weather(comment='drought irrigation')
        weather.rfcrp = config.WEATHER_STATION_CONFIG.get('reference_crop', 'S')
        weather.z = config.WEATHER_STATION_CONFIG.get('elevation', 100.0)
        weather.lat = config.WEATHER_STATION_CONFIG.get('latitude', 35.0)
        weather.wndht = config.WEATHER_STATION_CONFIG.get('wind_height', 2.0)
        
        for _, row in df.iterrows():
            date_str = row['Date']
            year = int(date_str[:4])
            doy = int(date_str[-3:])
            index = f"{year:04d}-{doy:03d}"
            
            data = [
                row['Srad'],
                row['Tmax'],
                row['Tmin'],
                row.get('Vapr', np.nan),
                row.get('Tdew', np.nan),
                row['RHmax'],
                row['RHmin'],
                row['Wndsp'],
                row['Rain'],
                np.nan,  
                row.get('MorP', 'M')
            ]
            
            weather.wdata.loc[index] = data
            
            weather.wdata.loc[index, 'ETref'] = weather.compute_etref(index)
        
        weather.savefile(output_file)
        logger.info(f"天气文件成功保存到: {output_file}")
        return True
        
    except Exception as e:
        logger.error(f"处理天气文件时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def Weather_wth(input_file, output_file):
    """处理天气数据并生成FAO格式的天气文件(兼容旧版接口)
    
    此函数保持与weather_wth.py中Weather_wth函数相同的接口,
    但使用更完善的process_weather_data实现
    
    Args:
        input_file (str): 输入文件路径
        output_file (str): 输出文件路径
        
    Returns:
        bool: 处理成功返回True,失败返回False
    """
    try:
        logger.info(f"使用兼容模式处理天气文件: {input_file} -> {output_file}")
        
        weather = pyfao56.Weather(filepath=input_file, comment='drought irrigation')
        
        if weather.wdata.empty:
            try:
                df = pd.read_csv(input_file)
                if set(['Date', 'Srad', 'Tmax', 'Tmin']).issubset(set(df.columns)):
                    return process_weather_data(input_file, output_file, auto_fix=True)
            except Exception:
                logger.warning(f"标准CSV读取失败,尝试以特殊格式读取文件")
                
            with open(input_file, 'r') as f:
                lines = f.readlines()
                
            data_start = 0
            for i, line in enumerate(lines):
                if '************************************************************************' in line:
                    data_start = i + 3  
                    break
                    
            data = []
            for line in lines[data_start:]:
                if line.strip() and not line.startswith('*'):
                    parts = line.strip().split()
                    if len(parts) >= 11 and not parts[0].startswith('Date') and not parts[0].startswith('MJ'): 
                        try:
                            date_str = parts[0]
                            srad = float(parts[1])
                            tmax = float(parts[2])
                            tmin = float(parts[3])
                            vapr = float(parts[4]) if parts[4] != '' else np.nan
                            tdew = float(parts[5]) if parts[5] != '' else np.nan
                            rhmax = float(parts[6])
                            rhmin = float(parts[7])
                            wndsp = float(parts[8])
                            rain = float(parts[9])
                            
                            data.append({
                                'Date': date_str,
                                'Srad': srad,
                                'Tmax': tmax,
                                'Tmin': tmin,
                                'Vapr': vapr,
                                'Tdew': tdew,
                                'RHmax': rhmax,
                                'RHmin': rhmin,
                                'Wndsp': wndsp,
                                'Rain': rain,
                                'MorP': 'M'
                            })
                        except (ValueError, IndexError) as e:
                            logger.error(f'处理数据行时出错: {str(e)}')
                            continue
            
            if data:
                df = pd.DataFrame(data)
                
                temp_csv = input_file + '.temp.csv'
                df.to_csv(temp_csv, index=False)
                
                result = process_weather_data(temp_csv, output_file, auto_fix=True)
                
                try:
                    os.remove(temp_csv)
                except Exception:
                    pass
                    
                logger.info(f"成功修正天气文件格式: {output_file}")
                return result
            else:
                logger.error("无法从输入文件提取有效数据")
                return False
        else:
            weather.savefile(output_file)
            logger.info(f"使用pyfao56直接处理天气文件: {output_file}")
            return True
        
    except Exception as e:
        logger.error(f"修正天气文件格式时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

class WeatherET:
    """气象数据处理类,用于FAO模型"""
    
    def __init__(self, comment='Weather Data'):
        """初始化气象数据处理类
        Args:
            comment (str, optional): 注释
        """
        self.comment = comment
        self.weather = pyfao56.Weather(comment=comment)
        
        station_config = getattr(config, 'WEATHER_CONFIG', {})
        self.weather.z = station_config.get('elevation', 100.0)
        self.weather.lat = station_config.get('latitude', 35.0) 
        self.weather.wndht = station_config.get('wind_height', 2.0)
        self.weather.rfcrp = station_config.get('reference_crop', 'S')
        
    def customload(self, data, start_date=None, end_date=None):
        """从DataFrame加载数据
        Args:
            data (pd.DataFrame): 天气数据
            start_date (str, optional): 开始日期 (YYYY-DOY格式)
            end_date (str, optional): 结束日期 (YYYY-DOY格式)
        """
        if start_date and end_date:
            df = data[(data['Date'] >= start_date) & (data['Date'] <= end_date)].copy()
        else:
            df = data.copy()
            
        if 'Vapr' not in df.columns:
            df['Vapr'] = np.nan
        if 'Tdew' not in df.columns:
            df['Tdew'] = np.nan
        if 'MorP' not in df.columns:
            df['MorP'] = 'M'
        if 'ETref' not in df.columns:
            df['ETref'] = np.nan
            
        for _, row in df.iterrows():
            date_str = row['Date']
            year = int(date_str[:4])
            doy = int(date_str[-3:])
            index = f"{year:04d}-{doy:03d}"
            
            data_row = [
                row['Srad'],
                row['Tmax'],
                row['Tmin'],
                row.get('Vapr', np.nan),
                row.get('Tdew', np.nan),
                row['RHmax'],
                row['RHmin'],
                row['Wndsp'],
                row['Rain'],
                row.get('ETref', np.nan),
                row.get('MorP', 'M')
            ]
            
            self.weather.wdata.loc[index] = data_row
            
            if pd.isna(self.weather.wdata.loc[index, 'ETref']):
                self.weather.wdata.loc[index, 'ETref'] = self.weather.compute_etref(index)
        
        logger.info(f"成功加载天气数据: {len(self.weather.wdata)}行, 日期范围: {start_date or '全部'} 到 {end_date or '全部'}")
        
    def savefile(self, output_file):
        """保存数据到文件
        
        Args:
            output_file (str): 输出文件路径
            
        Returns:
            bool: 保存成功返回True,失败返回False
        """
        if self.weather.wdata.empty:
            logger.error("没有数据可保存")
            return False
            
        try:
            self.weather.savefile(output_file)
            logger.info(f"天气文件成功保存到: {output_file}")
            return True
        except Exception as e:
            logger.error(f"保存天气文件时出错: {str(e)}")
            return False

if __name__ == '__main__':
    # 测试代码
    input_file = "irrigation_weather.csv"
    output_file = "weather.wth"
    
    if process_weather_data(input_file, output_file):
        print("天气数据处理成功")
    else:
        print("天气数据处理失败")