"""
### 1. AQUACROP_CONFIG 配置项，模拟时间范围参数：
- SIM_START_TIME : '2025/10/1' - 模拟开始时间
- SIM_END_TIME : '2026/6/1' - 模拟结束时间
### 2. FAO_CONFIG 配置项，文件路径参数：
- PAR_FILE : 'wheat2024.par' - FAO模型参数文件名
- OUTPUT_FILE : 'wheat2024.out' - FAO模型输出文件名
- SUMMARY_FILE : 'wheat2024.sum' - FAO模型摘要文件名
- WEATHER_FILE : 'data/weather/irrigation_weather.csv' - 原始天气数据文件路径
- TEMP_WEATHER_FILE : 'data/weather/drought_irrigation.wth' - 临时天气文件路径
- FIXED_WEATHER_FILE : 'data/weather/drought_irrigation_fixed.wth' - 修复后天气文件路径
- SOIL_FILE : 'data/soil/irrigation_soilprofile_sim.csv' - 土壤数据文件路径
- SOIL_OUTPUT_FILE : 'data/soil/drought_irrigation.sol' - 土壤输出文件路径
### 3. CROP_PARAMS 配置项，作物系数参数：
- Kcbini : 0.15 - 初期作物系数
- Kcbmid : 1.10 - 中期作物系数
- Kcbend : 0.20 - 末期作物系数 生育期长度参数（天数）：
- Lini : 20 - 初期阶段长度
- Ldev : 50 - 发育阶段长度
- Lmid : 70 - 中期阶段长度
- Lend : 30 - 末期阶段长度 作物高度参数：
- hmax : 1.0 - 最大作物高度（米）
### 4. SOIL_PARAMS 配置项， 土壤水分特征参数：
- thetaFC : 0.327 - 田间持水量（体积含水量）
- thetaWP : 0.10 - 萎蔫点含水量（体积含水量）
- theta0 : 0.327 - 初始土壤含水量（体积含水量） 根系发育参数：
- Zrini : 0.20 - 初始根系深度（米）
- Zrmax : 1.7 - 最大根系深度（米） 土壤物理参数：
- pbase : 0.55 - 基础土壤水分消耗系数
- Ze : 0.10 - 土壤蒸发层深度（米）
- REW : 9.0 - 易蒸发水量（毫米）
"""
import os
import time
import subprocess
import pandas as pd
import pyfao56 as fao
import sys
import numpy as np
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(project_root)

from src.utils.logger import logger
from src.models.soil import SoilProfile
from src.models.weather import WeatherET, Weather_wth
from config import current_config

class FAOModel:
    def __init__(self, config=None):
        """
        初始化FAO模型
        
        参数:
            config: 配置对象，如果未提供，将使用全局配置
        """
        self.config = config or current_config()
        self.fao_config = self.config.FAO_CONFIG
        self.module_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = project_root
        
    def run_model(self):
        """运行FAO模型"""
        try:
            start = time.time()
            try:
                
                sim_start = datetime.strptime(self.config.AQUACROP_CONFIG['SIM_START_TIME'], '%Y/%m/%d')
                sim_end = datetime.strptime(self.config.AQUACROP_CONFIG['SIM_END_TIME'], '%Y/%m/%d')
                
                # 转换为 FAO 模型所需的格式 (YYYY-DOY)
                start_year = sim_start.year
                start_doy = sim_start.timetuple().tm_yday
                end_year = sim_end.year
                end_doy = sim_end.timetuple().tm_yday
                
                start_date = f"{start_year}-{start_doy}"
                end_date = f"{end_year}-{end_doy}"
                
                logger.info(f"从AQUACROP配置获取模拟日期范围: {sim_start.strftime('%Y/%m/%d')} 到 {sim_end.strftime('%Y/%m/%d')}")
                logger.info(f"转换为FAO模型日期格式: {start_date} 到 {end_date}")
            except Exception as e:
                # 如果出错，使用默认值
                default_start = datetime.strptime('2024/10/1', '%Y/%m/%d')
                default_end = datetime.strptime('2025/6/1', '%Y/%m/%d')
                start_date = f"{default_start.year}-{default_start.timetuple().tm_yday}"
                end_date = f"{default_end.year}-{default_end.timetuple().tm_yday}"
                logger.warning(f"无法从配置获取模拟日期范围，使用默认值: {e}")
            
            # 模型参数
            par = fao.Parameters(comment='2024 Wheat')
            for key, value in self.config.CROP_PARAMS.items():
                setattr(par, key, value)
            for key, value in self.config.SOIL_PARAMS.items():
                setattr(par, key, value)
                
            # 创建输出目录
            output_dir = os.path.join(self.project_root, 'data/model_output')
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            # 参数文件
            par_file = os.path.join(output_dir, self.fao_config['PAR_FILE'])
            par.savefile(par_file)
            logger.info(f"参数文件已保存到: {par_file}")
            
            # 气象数据
            weather_api_path = os.path.join(self.module_dir, 'weather_api.py')
            subprocess.run([sys.executable, weather_api_path])
            
            # 创建天气目录
            weather_dir = os.path.join(self.project_root, 'data/weather')
            weather_file = self.fao_config['WEATHER_FILE']
            
            if os.path.isabs(weather_file):
                drought_weather = weather_file
            elif weather_file.startswith('data/weather'):
                drought_weather = os.path.join(self.project_root, weather_file)
            else:
                drought_weather = os.path.join(weather_dir, weather_file)

            # 打印调试信息
            logger.info(f"weather_dir: {weather_dir}")
            logger.info(f"weather_file: {weather_file}")
            logger.info(f"drought_weather: {drought_weather}")

            drought_weather_data = pd.read_csv(drought_weather)
            logger.info(f"原始天气数据日期范围: {drought_weather_data['Date'].min()} 到 {drought_weather_data['Date'].max()}")
            
            if start_date not in drought_weather_data['Date'].values:
                logger.error(f"开始日期 {start_date} 不在天气数据中")
                raise ValueError(f"天气数据缺少开始日期 {start_date}")
            
            weather_end_year = end_year
            weather_end_doy = end_doy  
            
            if weather_end_year % 4 == 0 and (weather_end_year % 100 != 0 or weather_end_year % 400 == 0):
                days_in_year = 366
            else:
                days_in_year = 365
                
            if weather_end_doy > days_in_year:
                weather_end_year += 1
                weather_end_doy = weather_end_doy - days_in_year
                
            weather_end_date = f"{weather_end_year}-{weather_end_doy:03d}"
            
            if weather_end_date not in drought_weather_data['Date'].values:
                logger.error(f"结束日期 {weather_end_date} 不在天气数据中")
                raise ValueError(f"天气数据缺少结束日期 {weather_end_date}")
            
            start_year = int(start_date.split('-')[0])
            start_doy = int(start_date.split('-')[1])
            
            start_dt = datetime(start_year, 1, 1) + pd.Timedelta(days=start_doy-1)
            end_dt = datetime(weather_end_year, 1, 1) + pd.Timedelta(days=weather_end_doy-1)
            
            date_range = pd.date_range(start=start_dt, end=end_dt, freq='D')
            date_range_str = [(date.year, date.timetuple().tm_yday) for date in date_range]
            date_range_str = [f"{year}-{doy:03d}" for year, doy in date_range_str]
            
            missing_dates = [date for date in date_range_str if date not in drought_weather_data['Date'].values]
            
            if missing_dates:
                logger.error(f"天气数据缺少以下日期: {missing_dates}")
                raise ValueError(f"天气数据不完整，缺少 {len(missing_dates)} 天的数据")
            
            wth_et = WeatherET(comment='drought irrigation')
            wth_et.customload(drought_weather_data, start_date, weather_end_date)
            
            temp_wth_file = os.path.join(weather_dir, os.path.basename(self.fao_config['TEMP_WEATHER_FILE']))
            wth_et.savefile(temp_wth_file)
            logger.info(f"中间格式天气文件已保存到: {temp_wth_file}")
            
            fixed_wth_file = os.path.join(weather_dir, os.path.basename(self.fao_config['FIXED_WEATHER_FILE']))
            Weather_wth(temp_wth_file, fixed_wth_file)
            logger.info(f"修复后的天气文件已保存到: {fixed_wth_file}")
            
            wth = fao.Weather()
            wth.loadfile(fixed_wth_file)
            logger.info(f"加载到FAO模型的天气数据日期范围: {wth.wdata.index.min()} 到 {wth.wdata.index.max()}")
            
            soil_dir = os.path.join(self.project_root, 'data/soil')
            if not os.path.exists(soil_dir):
                os.makedirs(soil_dir)
                
            drought_soil = os.path.join(soil_dir, os.path.basename(self.fao_config['SOIL_FILE']))
            soil = SoilProfile(comment='drought irrigation')
            soil.customload(drought_soil)
            soil_file = os.path.join(soil_dir, os.path.basename(self.fao_config['SOIL_OUTPUT_FILE']))
            soil.savefile(soil_file)
            logger.info(f"土壤数据文件已保存到: {soil_file}")
            
            # 运行模型
            logger.info("开始运行FAO模型...")
            mdl = fao.Model(start_date, end_date, par, wth, sol=soil)
            mdl.run()
            
            # 模型输出
            output_file = os.path.join(output_dir, self.fao_config['OUTPUT_FILE'])
            summary_file = os.path.join(output_dir, self.fao_config['SUMMARY_FILE'])
            mdl.savefile(output_file)
            mdl.savesums(summary_file)
            
            end = time.time()
            logger.info(f'FAO模型运行完成,耗时: {end - start:.2f}秒')
            logger.info(f'模型输出已保存到: {output_file}')
            logger.info(f'模型摘要已保存到: {summary_file}')
            
            # 返回模型结果文件路径
            return {
                'output_file': output_file,
                'summary_file': summary_file
            }
            
        except Exception as e:
            logger.error(f"运行FAO模型时出错: {str(e)}")
            raise

if __name__ == "__main__":
    # 使用新的统一配置
    model = FAOModel()
    model.run_model()
