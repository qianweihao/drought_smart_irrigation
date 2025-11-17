"""
天气数据处理模块
主要组件:
- clean_weather_data: 天气数据清理和修复函数
- validate_weather_data: 天气数据验证函数
- process_weather_data: 天气数据处理和格式转换函数
- Weather_wth: 兼容旧版接口的天气数据处理函数
- WeatherET: 天气数据处理类,主要用于FAO模型
1. WEATHER_CONFIG (4个参数)
在 WeatherET 类和 process_weather_data 函数中使用：
- elevation - 海拔高度 (默认值: 100.0)
- latitude - 纬度 (默认值: 35.0)
- wind_height - 风速测量高度 (默认值: 2.0)
- reference_crop - 参考作物类型 (默认值: 'S')
"""
import os
import sys
import logging
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

def parse_date_to_year_doy(date_str):
    """解析日期字符串为年份和年积日(DOY)
    
    Args:
        date_str: 日期字符串，支持多种格式：
            - "YYYY-DOY" (如 "2024-001")
            - "YYYYMMDD" (如 "20241001")
            - "YYYY-MM-DD" (如 "2024-10-01")
            - pandas可解析的其他格式
    
    Returns:
        tuple: (year, doy) - 年份和年积日
    
    Raises:
        ValueError: 如果无法解析日期格式
    """
    try:
        date_str = str(date_str).strip()
        
        # 格式1: "YYYY-DOY" (如 "2024-001")
        if '-' in date_str and len(date_str.split('-')) == 2:
            parts = date_str.split('-')
            if len(parts[0]) == 4 and len(parts[1]) == 3:
                year = int(parts[0])
                doy = int(parts[1])
                if 1 <= doy <= 366:
                    return year, doy
        
        # 格式2: "YYYYMMDD" (如 "20241001")
        if len(date_str) == 8 and date_str.isdigit():
            year = int(date_str[:4])
            month = int(date_str[4:6])
            day = int(date_str[6:8])
            date_obj = pd.Timestamp(year, month, day)
            doy = date_obj.timetuple().tm_yday
            return year, doy
        
        # 格式3: 使用pandas解析其他格式
        try:
            date_obj = pd.to_datetime(date_str)
            year = date_obj.year
            doy = date_obj.timetuple().tm_yday
            return year, doy
        except:
            pass
        
        # 如果都失败了，尝试提取前4位作为年份，后3位作为DOY
        if len(date_str) >= 7:
            try:
                year = int(date_str[:4])
                doy = int(date_str[-3:])
                if 1 <= doy <= 366:
                    logger.warning(f"使用备用方法解析日期: {date_str} -> {year}-{doy:03d}")
                    return year, doy
            except:
                pass
        
        raise ValueError(f"无法解析日期格式: {date_str}")
        
    except Exception as e:
        logger.error(f"解析日期时出错: {date_str}, 错误: {str(e)}")
        raise ValueError(f"无法解析日期格式: {date_str}")

def clean_weather_data(df):
    """清理天气数据中的异常值和缺失值
    Args:
        df (pd.DataFrame): 天气数据DataFrame 
    Returns:
        pd.DataFrame: 清理后的数据
    """
    try:
        clean_df = df.copy()
        
        # 检查是否有完全缺失的行（所有关键气象数据都是NaN）
        key_weather_cols = ['Srad', 'Tmax', 'Tmin', 'RHmax', 'RHmin', 'Wndsp']
        completely_missing_mask = clean_df[key_weather_cols].isna().all(axis=1)
        
        if completely_missing_mask.any():
            missing_count = completely_missing_mask.sum()
            logger.warning(f"检测到{missing_count}行完全缺失的天气数据，将使用前向填充（forward fill）")
            
            # 对关键气象列使用前向填充
            for col in key_weather_cols:
                if col in clean_df.columns:
                    clean_df[col] = clean_df[col].fillna(method='ffill')
                    # 如果第一行就是NaN，使用后向填充
                    clean_df[col] = clean_df[col].fillna(method='bfill')
            
            # Rain应该填充为0（没有降雨）
            if 'Rain' in clean_df.columns:
                clean_df['Rain'] = clean_df['Rain'].fillna(0)
        
        numeric_cols = ['Srad', 'Tmax', 'Tmin', 'Vapr', 'Tdew', 'RHmax', 'RHmin', 'Wndsp', 'Rain']
        for col in numeric_cols:
            if col in clean_df.columns:
                # 处理剩余的零散缺失值
                remaining_na = clean_df[col].isna().sum()
                if remaining_na > 0:
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
                    elif col == 'Srad':
                        # 太阳辐射使用前后值的平均
                        clean_df[col] = clean_df[col].fillna(method='ffill').fillna(method='bfill').fillna(7.0)
                    elif col == 'Tmax' or col == 'Tmin':
                        # 温度使用前后值填充
                        clean_df[col] = clean_df[col].fillna(method='ffill').fillna(method='bfill')
                    
                    logger.info(f"列{col}有{remaining_na}个缺失值已被填充")
        
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
        
        # 最终验证：确保所有关键列没有NaN
        final_na_check = clean_df[key_weather_cols].isna().sum()
        if final_na_check.any():
            logger.error(f"清理后仍有缺失值: {final_na_check[final_na_check > 0].to_dict()}")
        
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
        weather_config = getattr(config, 'WEATHER_CONFIG', {})
        weather.rfcrp = weather_config.get('reference_crop', 'S')
        weather.z = weather_config.get('elevation', 100.0)
        weather.lat = weather_config.get('latitude', 35.0)
        weather.wndht = weather_config.get('wind_height', 2.0)
        
        for _, row in df.iterrows():
            try:
                date_value = row['Date']
                
                # 如果Date列已经是datetime类型，直接计算year和doy
                if pd.api.types.is_datetime64_any_dtype(df['Date']) or isinstance(date_value, pd.Timestamp):
                    if pd.isna(date_value):
                        logger.warning(f"跳过包含NaN日期的行")
                        continue
                    year = date_value.year
                    doy = date_value.timetuple().tm_yday
                else:
                    # 如果是字符串或其他格式，使用解析函数
                    date_str = str(date_value)
                    year, doy = parse_date_to_year_doy(date_str)
                
                index = f"{year:04d}-{doy:03d}"
            except (ValueError, AttributeError) as e:
                logger.error(f"跳过无效日期行: {date_value}, 错误: {str(e)}")
                continue
            
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
                            # 验证日期格式
                            try:
                                parse_date_to_year_doy(date_str)
                            except ValueError:
                                logger.warning(f"跳过无效日期行: {line.strip()[:50]}")
                                continue
                            
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
            start_date (str, optional): 开始日期 (YYYY-DOY格式或其他pandas可解析格式)
            end_date (str, optional): 结束日期 (YYYY-DOY格式或其他pandas可解析格式)
        """
        df = data.copy()
        
        # 判断Date列的格式并进行转换
        date_is_doy_format = False
        if not pd.api.types.is_datetime64_any_dtype(df['Date']):
            # 检查是否是YYYY-DOY格式
            first_date_str = str(df['Date'].iloc[0]) if not df.empty else ""
            if '-' in first_date_str and len(first_date_str.split('-')) == 2:
                parts = first_date_str.split('-')
                if len(parts[0]) == 4 and len(parts[1]) == 3:
                    date_is_doy_format = True
                    logger.info(f"检测到Date列为YYYY-DOY格式，将转换为日期类型")
                    try:
                        df['Date'] = pd.to_datetime(df['Date'], format='%Y-%j', errors='coerce')
                    except:
                        logger.warning("YYYY-DOY格式转换失败")
            
            # 如果不是DOY格式或转换失败，尝试标准日期解析
            if not date_is_doy_format or df['Date'].isna().all():
                try:
                    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
                except:
                    logger.warning("无法将Date列转换为日期类型，将使用字符串比较")
        
        # 日期过滤
        if start_date and end_date:
            try:
                # 转换start_date和end_date为日期类型（支持YYYY-DOY格式）
                if isinstance(start_date, str):
                    try:
                        # 先尝试YYYY-DOY格式
                        year, doy = parse_date_to_year_doy(start_date)
                        start_dt = pd.to_datetime(f"{year}-{doy:03d}", format='%Y-%j')
                    except:
                        # 如果失败，尝试标准格式
                        try:
                            start_dt = pd.to_datetime(start_date)
                        except:
                            logger.warning(f"无法解析开始日期: {start_date}")
                            start_dt = None
                else:
                    start_dt = start_date
                
                if isinstance(end_date, str):
                    try:
                        # 先尝试YYYY-DOY格式
                        year, doy = parse_date_to_year_doy(end_date)
                        end_dt = pd.to_datetime(f"{year}-{doy:03d}", format='%Y-%j')
                    except:
                        # 如果失败，尝试标准格式
                        try:
                            end_dt = pd.to_datetime(end_date)
                        except:
                            logger.warning(f"无法解析结束日期: {end_date}")
                            end_dt = None
                else:
                    end_dt = end_date
                
                # 如果日期解析失败，跳过过滤
                if start_dt is None or end_dt is None:
                    logger.warning("日期解析失败，将使用全部数据")
                    df = data.copy()
                else:
                    # 如果Date列是日期类型，使用日期比较
                    if pd.api.types.is_datetime64_any_dtype(df['Date']):
                        before_filter = len(df)
                        df = df[(df['Date'] >= start_dt) & (df['Date'] <= end_dt)].copy()
                        after_filter = len(df)
                        logger.info(f"日期过滤: {before_filter}行 -> {after_filter}行 (从 {start_dt.date()} 到 {end_dt.date()})")
                    else:
                        # 使用字符串比较
                        df = df[(df['Date'] >= start_date) & (df['Date'] <= end_date)].copy()
                        logger.info(f"使用字符串过滤日期: 从 {start_date} 到 {end_date}, 结果: {len(df)}行")
            except Exception as e:
                logger.warning(f"日期过滤失败: {str(e)}，将使用全部数据")
                df = data.copy()
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
            try:
                date_value = row['Date']
                
                # 如果Date列已经是datetime类型，直接计算year和doy
                if pd.api.types.is_datetime64_any_dtype(df['Date']) or isinstance(date_value, pd.Timestamp):
                    if pd.isna(date_value):
                        logger.warning(f"跳过包含NaN日期的行")
                        continue
                    year = date_value.year
                    doy = date_value.timetuple().tm_yday
                else:
                    # 如果是字符串或其他格式，使用解析函数
                    date_str = str(date_value)
                    year, doy = parse_date_to_year_doy(date_str)
                
                index = f"{year:04d}-{doy:03d}"
            except (ValueError, AttributeError) as e:
                logger.error(f"跳过无效日期行: {date_value}, 错误: {str(e)}")
                continue
            
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