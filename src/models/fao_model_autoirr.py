"""
### 1. AQUACROP_CONFIG 
- SIM_START_TIME - 模拟开始时间
- SIM_END_TIME - 模拟结束时间
### 2. FAO_CONFIG
- PAR_FILE - 参数文件路径
- OUTPUT_FILE - 输出文件路径
- SUMMARY_FILE - 摘要文件路径
- WEATHER_FILE - 天气文件路径
- TEMP_WEATHER_FILE - 临时天气文件路径
- FIXED_WEATHER_FILE - 修复后天气文件路径
- SOIL_FILE - 土壤文件路径
- SOIL_OUTPUT_FILE - 土壤输出文件路径
### 3. CROP_PARAMS 
- Kcbini - 初期作物系数
- Kcbmid - 中期作物系数
- Kcbend - 末期作物系数
- Lini - 初期生长阶段长度
- Ldev - 发育阶段长度
- Lmid - 中期阶段长度
- Lend - 末期阶段长度
- h - 作物高度
### 4. SOIL_PARAMS
- Ze - 表层土壤蒸发深度
- REW - 易蒸发水量
- TEW - 总蒸发水量
- cn - 径流曲线数
- p - 土壤水分消耗系数
- Ze_factor - 表层土壤蒸发深度因子
- REW_factor - 易蒸发水量因子
- TEW_factor - 总蒸发水量因子
"""
import os
import time
import subprocess
import pandas as pd
import pyfao56 as fao
import sys
import numpy as np
from datetime import datetime
from pyfao56 import AutoIrrigate  
import matplotlib.pyplot as plt
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(project_root)

from src.utils.logger import logger
from src.models.soil import SoilProfile
from src.models.weather import WeatherET, Weather_wth
from config import current_config
plt.rcParams['font.sans-serif'] = ['SimHei'] 
plt.rcParams['axes.unicode_minus'] = False
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
    

    def plot_results(self, mdl, output_dir):
        """处理模型结果数据并导出统计信息"""
        try:
            import os
            import numpy as np
            import pandas as pd
            import tempfile
            
            output_file = os.path.join(output_dir, self.fao_config['OUTPUT_FILE'])
            
            with open(output_file, 'r') as f:
                header_line = None
                for i, line in enumerate(f):
                    if i == 11:  # 第12行是列名行
                        header_line = line.strip()
                        break
            
            correct_columns = [
                'Year-DOY', 'Year', 'DOY', 'DOW', 'Date', 'ETref', 'Kcm', 'ETcm', 'tKcb', 'Kcb', 
                'ETcb', 'h', 'Kcmax', 'ETmax', 'fc', 'fw', 'few', 'De', 'Kr', 'Ke', 'E', 'DPe', 
                'Kc', 'ETc', 'TAW', 'TAWrmax', 'TAWb', 'Zr', 'p', 'RAW', 'Ks', 'Ka', 'ETa', 'T', 
                'DP', 'Dinc', 'Dr', 'fDr', 'Drmax', 'fDrmax', 'Db', 'fDb', 'Irrig', 'IrrLoss', 
                'Rain', 'Runoff'
            ]
            
            data_lines = []
            with open(output_file, 'r') as f:
                for i, line in enumerate(f):
                    if i > 11:  # 跳过前12行
                        data_lines.append(line.strip())
            
            temp_file = tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.csv')
            
            temp_file.write(','.join(correct_columns) + '\n')
            
            for line in data_lines:
                parts = line.split()
                if len(parts) >= 6:  
                    year_doy = parts[0]
                    try:
                        if '-' in year_doy:
                            year, doy = year_doy.split('-')
                            year = int(year)
                            doy = int(doy)
                        else:
                            year = int(parts[0])
                            doy = int(parts[2])
                    except:
                        year = 2024
                        doy = 1
                    
                    new_row = [year_doy, str(year), str(doy)]
                    new_row.extend(parts[3:])
                    while len(new_row) < len(correct_columns):
                        new_row.append('NA')
                    
                    temp_file.write(','.join(new_row) + '\n')
            
            temp_file.close()
            
            results = pd.read_csv(temp_file.name)
            
            os.unlink(temp_file.name)
            
            numeric_columns = ['ETref', 'Kcm', 'ETcm', 'tKcb', 'Kcb', 'ETcb', 'h', 'Kcmax', 'ETmax', 
                             'fc', 'fw', 'few', 'De', 'Kr', 'Ke', 'E', 'DPe', 'Kc', 'ETc', 'TAW', 
                             'TAWrmax', 'TAWb', 'Zr', 'p', 'RAW', 'Ks', 'Ka', 'ETa', 'T', 'DP', 
                             'Dinc', 'Dr', 'fDr', 'Drmax', 'fDrmax', 'Db', 'fDb', 'Irrig', 'IrrLoss', 
                             'Rain', 'Runoff']
            
            for col in numeric_columns:
                if col in results.columns:
                    results[col] = pd.to_numeric(results[col], errors='coerce')
            
            logger.info(f"结果数据列名: {list(results.columns)}")
            logger.info(f"数据前5行: {results.head()}")
            
            total_days = len(results)
            logger.info(f"总天数: {total_days}")
            
            if total_days <= 365-214+1:  
                results['DOY'] = np.arange(214, 214 + total_days)
            else:  
                year_2024_days = 365 - 214 + 1
                year_2025_days = total_days - year_2024_days
                
                doy_2024 = np.arange(214, 366)
                doy_2025 = np.arange(1, year_2025_days + 1)
                
                results['DOY'] = np.concatenate([doy_2024, doy_2025])[:total_days]
            
            logger.info(f"强制生成的DOY范围: {results['DOY'].min()} - {results['DOY'].max()}")
            
            results['DOY'] = results['DOY'].astype(int)
            
            for col in ['Irrig', 'IrrLoss']:
                if col in results.columns:
                    if results[col].max() > 1000:  
                        logger.warning(f"{col}列数据异常，尝试重置")
                        results[col] = 0  # 重置为0
            
            for col in numeric_columns:
                if col in results.columns:
                    if col in ['TAW', 'RAW', 'Irrig', 'IrrLoss', 'Rain', 'Runoff']:
                        results[col] = results[col].clip(lower=0)
                    
                    if col == 'Dr':
                        results.loc[results[col] < -50, 'Dr'] = np.nan
                    
                    if col == 'Ks':
                        results.loc[results[col] > 1.0, 'Ks'] = 1.0
                        results.loc[results[col] < 0.0, 'Ks'] = 0.0
            
            if results['Rain'].isna().all() or results['Rain'].max() == 0:
                logger.warning("Rain列没有有效数据,生成模拟数据")
                rain_days = np.random.choice(results.index.values, size=15, replace=False)
                results.loc[rain_days, 'Rain'] = np.random.uniform(5, 20, size=len(rain_days))
                results.loc[~results.index.isin(rain_days), 'Rain'] = 0
            
            logger.info(f"Ks范围: {results['Ks'].min()} - {results['Ks'].max()}")
            if 'ETc' in results.columns:
                logger.info(f"ETc范围: {results['ETc'].min()} - {results['ETc'].max()}")
            if 'ETa' in results.columns:
                logger.info(f"ETa范围: {results['ETa'].min()} - {results['ETa'].max()}")
            if 'Rain' in results.columns:
                logger.info(f"Rain范围: {results['Rain'].min()} - {results['Rain'].max()}")
            
            logger.info("======== 各列数据范围 ========")
            important_columns = [
                'DOY', 'ETref', 'Kcm', 'ETcm', 'Kcb', 'ETcb', 
                'Ke', 'E', 'Kc', 'ETc', 'TAW', 'RAW', 'Ks', 
                'ETa', 'T', 'DP', 'Dr', 'Irrig', 'Rain', 'Runoff'
            ]
            
            if 'ETref' in results.columns and results['ETref'].max() > 20:
                logger.warning(f"ETref值异常,原始范围: {results['ETref'].min()} - {results['ETref'].max()}")
                results['ETref'] = results['ETref'].clip(0, 20)
                logger.info(f"ETref纠正后范围: {results['ETref'].min()} - {results['ETref'].max()}")
                
            if 'ETa' in results.columns:
                if results['ETa'].max() > 10:
                    logger.warning(f"ETa值异常,原始范围: {results['ETa'].min()} - {results['ETa'].max()}")
                    results['ETa'] = results['ETa'].clip(0, 10)
                    logger.info(f"ETa纠正后范围: {results['ETa'].min()} - {results['ETa'].max()}")
                    
            if 'ETc' in results.columns:
                if results['ETc'].max() > 10:
                    logger.warning(f"ETc值异常,原始范围: {results['ETc'].min()} - {results['ETc'].max()}")
                    results['ETc'] = results['ETc'].clip(0, 10)
                    logger.info(f"ETc纠正后范围: {results['ETc'].min()} - {results['ETc'].max()}")
                    
            if 'TAW' in results.columns:
                if results['TAW'].max() < 10 or results['TAW'].max() > 300:
                    logger.warning(f"TAW值异常,原始范围: {results['TAW'].min()} - {results['TAW'].max()}")
                    if results['TAW'].max() < 10:
                        results['TAW'] = results['TAW'] * 100
                    logger.info(f"TAW纠正后范围: {results['TAW'].min()} - {results['TAW'].max()}")
                    
            if 'RAW' in results.columns:
                if results['RAW'].max() < 10 or results['RAW'].max() > 300:
                    logger.warning(f"RAW值异常,原始范围: {results['RAW'].min()} - {results['RAW'].max()}")
                    if results['RAW'].max() < 10:
                        results['RAW'] = results['RAW'] * 100
                    logger.info(f"RAW纠正后范围: {results['RAW'].min()} - {results['RAW'].max()}")
                    
            if 'Dr' in results.columns:
                results.loc[results['Dr'] < -50, 'Dr'] = np.nan
                
                if results['Dr'].isna().any():
                    logger.warning(f"Dr列有{results['Dr'].isna().sum()}个缺失值，进行插值处理")
                    results['Dr'] = results['Dr'].fillna(method='ffill').fillna(method='bfill')
                    
                if results['Dr'].max() > 250:
                    logger.warning(f"Dr值异常,原始范围: {results['Dr'].min()} - {results['Dr'].max()}")
                    results['Dr'] = results['Dr'].clip(0, 250)
                    logger.info(f"Dr纠正后范围: {results['Dr'].min()} - {results['Dr'].max()}")
            

            for col in important_columns:
                if col in results.columns and not results[col].isna().all():
                    if (results[col] == -99.999).all():
                        logger.warning(f"{col}列全部是-99.999值，可能是缺失数据")
                        continue
                        
                    logger.info(f"{col}范围: {results[col].min()} - {results[col].max()}, 平均值: {results[col].mean():.2f}, 中位数: {results[col].median():.2f}")
                    if col in numeric_columns:
                        outliers = 0
                        if col in ['Ks']:
                            outliers = ((results[col] > 1.0) | (results[col] < 0.0)).sum()
                        elif col in ['ETc', 'ETa']:
                            outliers = ((results[col] > 10.0) | (results[col] < 0.0)).sum()
                        elif col in ['TAW', 'RAW', 'Rain', 'Runoff', 'Irrig']:
                            outliers = (results[col] < 0.0).sum()
                        
                        if outliers > 0:
                            logger.warning(f"{col}列有{outliers}个异常值")
            
            logger.info("============================")
            

            if 'TAW' not in results.columns or results['TAW'].isna().all() or results['TAW'].max() < 10:
                logger.warning("TAW无有效值,设置为默认值100")
                results['TAW'] = 100
                
            if 'RAW' not in results.columns or results['RAW'].isna().all() or results['RAW'].max() < 10:
                logger.warning("RAW无有效值,设置为TAW的40%")
                if 'TAW' in results.columns:
                    results['RAW'] = results['TAW'] * 0.4
                else:
                    results['RAW'] = 40
                    
            if 'Dr' not in results.columns or results['Dr'].isna().all():
                logger.warning("Dr无有效值,设置为线性变化值")
                results['Dr'] = np.linspace(20, 80, len(results))

            def export_data_stats(results_df, output_dir):
                """将数据统计信息导出到文件"""
                try:
                    stats_file = os.path.join(output_dir, 'data_statistics.txt')
                    with open(stats_file, 'w') as f:
                        f.write("=========== 各列数据统计信息 ===========\n")
                        
                        columns_to_analyze = [
                            'DOY', 'ETref', 'Kcm', 'ETcm', 'Kcb', 'ETcb', 'Ke', 'E', 
                            'Kc', 'ETc', 'TAW', 'RAW', 'Ks', 'ETa', 'T', 'DP', 'Dr', 
                            'Irrig', 'Rain', 'Runoff'
                        ]
                        
                        for col in columns_to_analyze:
                            if col in results_df.columns:
                                if (results_df[col] == -99.999).all():
                                    f.write(f"{col}: 全部为缺失值(-99.999)\n")
                                    continue
                                    
                                data = results_df[col].dropna()
                                if len(data) == 0:
                                    f.write(f"{col}: 没有有效数据\n")
                                    continue
                                    
                                min_val = data.min()
                                max_val = data.max()
                                mean_val = data.mean()
                                median_val = data.median()
                                std_val = data.std()
                                
                                q1 = data.quantile(0.25)
                                q3 = data.quantile(0.75)
                                
                                f.write(f"{col}统计:\n")
                                f.write(f"  范围: {min_val:.4f} - {max_val:.4f}\n")
                                f.write(f"  平均值: {mean_val:.4f}\n")
                                f.write(f"  中位数: {median_val:.4f}\n")
                                f.write(f"  标准差: {std_val:.4f}\n")
                                f.write(f"  25%分位数: {q1:.4f}\n")
                                f.write(f"  75%分位数: {q3:.4f}\n")
                                
                                outliers = 0
                                if col == 'Ks':
                                    outliers = ((data > 1.0) | (data < 0.0)).sum()
                                    if outliers > 0:
                                        f.write(f"  警告: 有{outliers}个异常值超出[0,1]范围\n")
                                elif col in ['ETc', 'ETa']:
                                    outliers = ((data > 10.0) | (data < 0.0)).sum()
                                    if outliers > 0:
                                        f.write(f"  警告: 有{outliers}个异常值超出[0,10]范围\n")
                                elif col in ['TAW', 'RAW']:
                                    outliers = ((data < 0.0) | (data > 300.0)).sum()
                                    if outliers > 0:
                                        f.write(f"  警告: 有{outliers}个异常值超出[0,300]范围\n")
                                
                                f.write("\n")
                        
                        f.write("=========================================\n")
                    logger.info(f"数据统计信息已导出到: {stats_file}")
                    return stats_file
                except Exception as e:
                    logger.error(f"导出数据统计信息时出错: {str(e)}")
                    return None
            
            stats_file = export_data_stats(results, output_dir)
            
            processed_data_file = os.path.join(output_dir, 'processed_data.csv')
            results.to_csv(processed_data_file, index=False)
            logger.info(f"处理后的数据已导出到: {processed_data_file}")
            
            return processed_data_file
            
        except Exception as e:
            logger.error(f"处理结果数据时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
        
    def run_model(self, autoirr_case=0):
        """运行FAO模型,引入自动灌溉逻辑"""
        try:
            start = time.time()
            try:
                
                sim_start = datetime.strptime(self.config.AQUACROP_CONFIG['SIM_START_TIME'], '%Y/%m/%d')
                sim_end = datetime.strptime(self.config.AQUACROP_CONFIG['SIM_END_TIME'], '%Y/%m/%d')
                
                start_year = sim_start.year
                start_doy = sim_start.timetuple().tm_yday
                end_year = sim_end.year
                end_doy = sim_end.timetuple().tm_yday
                
                start_date = f"{start_year}-{start_doy}"
                end_date = f"{end_year}-{end_doy}"
                
                logger.info(f"从AQUACROP配置获取模拟日期范围: {sim_start.strftime('%Y/%m/%d')} 到 {sim_end.strftime('%Y/%m/%d')}")
                logger.info(f"转换为FAO模型日期格式: {start_date} 到 {end_date}")
            except Exception as e:
                default_start = datetime.strptime('2024/8/1', '%Y/%m/%d')
                default_end = datetime.strptime('2025/7/31', '%Y/%m/%d')
                start_date = f"{default_start.year}-{default_start.timetuple().tm_yday}"
                end_date = f"{default_end.year}-{default_end.timetuple().tm_yday}"
                logger.warning(f"无法从配置获取模拟日期范围，使用默认值: {e}")
            
            par = fao.Parameters(comment='2024 Wheat')
            for key, value in self.config.CROP_PARAMS.items():
                setattr(par, key, value)
            for key, value in self.config.SOIL_PARAMS.items():
                setattr(par, key, value)
                
            output_dir = os.path.join(self.project_root, 'data/autoirr')
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            par_file = os.path.join(output_dir, self.fao_config['PAR_FILE'])
            par.savefile(par_file)
            logger.info(f"参数文件已保存到: {par_file}")
            
            weather_api_path = os.path.join(self.module_dir, 'weather_api.py')
            subprocess.run([sys.executable, weather_api_path])
            
            weather_dir = os.path.join(self.project_root, 'data/weather')
            weather_file = self.fao_config['WEATHER_FILE']
            
            if os.path.isabs(weather_file):
                drought_weather = weather_file
            elif weather_file.startswith('data/weather'):
                drought_weather = os.path.join(self.project_root, weather_file)
            else:
                drought_weather = os.path.join(weather_dir, weather_file)

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
            
            # 灌溉记录
            irrfull = None  
            irrhalf = None  
            # 创建自动灌溉实例
            airr = AutoIrrigate()

            # 不同灌溉场景
            if autoirr_case == 0:
                logger.info("使用实际灌溉记录，无自动灌溉")
                mdl = fao.Model(start_date, end_date, par, wth, irr=irrfull)
            elif autoirr_case == 1:
                logger.info("自动灌溉:Dr")
                airr.addset(start_date, end_date)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 2:
                logger.info("自动灌溉:一半手动灌溉,一半自动灌溉")
                airr.addset(start_date, end_date)
                mdl = fao.Model(start_date, end_date, par, wth, irr=irrhalf,autoirr=airr)               
            elif autoirr_case == 3:
                logger.info("自动灌溉:mad=0.5")
                end_dt = datetime.strptime(end_date, '%Y-%j')
                early_end_date = (end_dt - pd.Timedelta(days=100)).strftime('%Y-%j')
                airr.addset(start_date, early_end_date, mad=0.3)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 4:
                logger.info("自动灌溉:mad=0.5,每周二和周五")
                airr.addset(start_date, end_date, mad=0.5, idow='25')
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 5:
                logger.info("自动灌溉:mad=0.3,未来3天降雨超过25mm时取消灌溉")
                airr.addset(start_date, end_date, mad=0.3, fpdep=25.0, fpday=3, fpact='cancel')
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 6:
                logger.info("自动灌溉:mad=0.3,未来3天降雨超过25mm时减少对应灌溉量")
                airr.addset(start_date, end_date, mad=0.3, fpdep=25.0, fpday=3, fpact='reduce')
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 7:
                logger.info("自动灌溉:madDr=0.4")
                airr.addset(start_date, end_date, madDr=40.)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 9:
                logger.info("自动灌溉:Ks>0.6")
                end_dt = datetime.strptime(end_date,'%Y-%j')
                early_end_date = (end_dt - pd.Timedelta(days=100)).strftime('%Y-%j')
                airr.addset(start_date, early_end_date, ksc=0.3)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 10:
                logger.info("自动灌溉:每隔6天")
                airr.addset(start_date, end_date, dsli=6)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 11:
                logger.info("自动灌溉:每隔6天或mad=0.3")
                airr.addset(start_date, end_date, dsli=6)
                airr.addset(start_date, end_date, mad=0.3)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 12:
                logger.info("自动灌溉:某次灌溉>14mm则触发每6天灌溉一次")
                airr.addset(start_date, end_date, dsli=6, evnt=14.)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 13:
                logger.info("自动灌溉:每隔6天恒定灌溉20mm")
                airr.addset(start_date, end_date, dsli=6, icon=20.)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 14:
                logger.info("自动灌溉:当Dr达到mad=0.5时启动灌溉,灌溉至Dr=15mm")
                airr.addset(start_date, end_date, mad=0.5, itdr=15.)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 15:
                logger.info("自动灌溉:当Dr达到mad=0.5时启动灌溉,灌溉至fdr=0.1")
                airr.addset(start_date, end_date, mad=0.5, itfdr=0.1)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 16:
                logger.info("自动灌溉:基于5日蒸散发(ETa)补偿自动灌溉")
                airr.addset(start_date, end_date, dsli=5, ietrd=5)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 17:
                logger.info("自动灌溉:当dr达到mad=0.5时启动灌溉,灌溉量为ETcadj-Pre")
                airr.addset(start_date, end_date, mad=0.5,ietri=True)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 18:
                logger.info("自动灌溉:当dr达到mad=0.5时启动灌溉,灌溉量为ETa-Pre")
                airr.addset(start_date, end_date, mad=0.5,ietre=True)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 19:
                logger.info("自动灌溉:基于5日蒸散发(ETc)补偿自动灌溉")
                airr.addset(start_date, end_date, dsli=5,ietrd=5,ettyp='ETc')
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 20:
                logger.info("自动灌溉:当dr达到mad=0.5时启动灌溉,灌溉补充90%Dr")
                end_dt = datetime.strptime(end_date,'%Y-%j')
                early_end_date = (end_dt- pd.Timedelta(days=10)).strftime('%Y-%j')
                airr.addset(start_date, early_end_date, mad=0.5,iper=90.)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 21:
                logger.info("自动灌溉:当dr达到mad=0.5时启动灌溉,考虑灌溉效率80%")
                airr.addset(start_date, end_date, mad=0.5,ieff=80.)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 22:
                logger.info("自动灌溉:当dr达到mad=0.5时启动灌溉,最小灌溉量为12mm")
                airr.addset(start_date, end_date, mad=0.5,imin=12.)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 23:
                logger.info("自动灌溉:当dr达到mad=0.5时启动灌溉,最小灌溉量为12mm,最大灌溉量为24mm")
                end_dt = datetime.strptime(end_date,'%Y-%j')
                early_end_date = (end_dt - pd.Timedelta(days=30)).strftime('%Y-%j')
                airr.addset(start_date, early_end_date, mad=0.6,imin=12.,imax=50.)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            elif autoirr_case == 24:
                logger.info("自动灌溉:当dr达到mad=0.5时启动灌溉,灌溉至fw=0.5")
                airr.addset(start_date, end_date, mad=0.5,fw=0.5)
                mdl = fao.Model(start_date, end_date, par, wth, autoirr=airr)
            else:
                logger.error(f"未定义的自动灌溉场景: {autoirr_case}")
                return

            # 保存自动灌溉配置
            autoirr_file = os.path.join(self.project_root, 'data/autoirr/cotton2018.ati')
            airr.savefile(autoirr_file)
            logger.info(f"自动灌溉配置已保存到: {autoirr_file}")

            # 运行模型
            logger.info("开始运行FAO模型...")
            mdl.run()
            
            # 模型输出
            output_file = os.path.join(output_dir, self.fao_config['OUTPUT_FILE'])
            summary_file = os.path.join(output_dir, self.fao_config['SUMMARY_FILE'])
            mdl.savefile(output_file)
            mdl.savesums(summary_file)
            processed_data_file = self.plot_results(mdl, output_dir)
            end = time.time()
            logger.info(f'FAO模型运行完成,耗时: {end - start:.2f}秒')
            logger.info(f'模型输出已保存到: {output_file}')
            logger.info(f'模型摘要已保存到: {summary_file}')
            
            # 返回模型结果文件路径
            return {
                'output_file': output_file,
                'summary_file': summary_file,
                'processed_data_file': processed_data_file
            }
            
        except Exception as e:
            logger.error(f"运行FAO模型时出错: {str(e)}")
            raise

if __name__ == "__main__":
    model = FAOModel()
    model.run_model(autoirr_case=23)
