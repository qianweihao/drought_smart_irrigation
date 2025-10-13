import os
import pandas as pd
from datetime import datetime
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(project_root)

from src.utils.logger import logger
from src.models.fao_model import FAOModel

class IrrigationService:
    def __init__(self, config):
        self.config = config
        self.fao_model = FAOModel(config)
        self._last_model_run = None
        
    def get_root_depth_coefficient(self, out_file):
        """获取根系深度系数
        Args:
            out_file (str): 模型输出文件路径 
        Returns:
            float: 根系深度系数 (0.5 或 1.0)
        """
        try:
            if not os.path.exists(out_file):
                logger.warning(f"模型输出文件不存在: {out_file},使用默认根系深度系数1.0")
                return 1.0
            df = pd.read_csv(out_file, delim_whitespace=True, skiprows=10)
            if df.empty:
                logger.warning("模型输出文件为空,使用默认根系深度系数1.0")
                return 1.0
            df['Date'] = pd.to_datetime(df['Date'], format='%m/%d/%y')
            now = pd.to_datetime(datetime.now().date())
            today_data = df[df['Date'] == now]
            
            if today_data.empty:
                logger.warning(f"无法找到当前日期({now.strftime('%Y-%m-%d')})的数据，使用最接近的日期")
                df['date_diff'] = abs((df['Date'] - now).dt.days)
                today_data = df.loc[df['date_diff'].idxmin()]
            else:
                today_data = today_data.iloc[0]
            root_depth = today_data['Zr'] if 'Zr' in today_data else 0.2
            if root_depth < 0.3:
                logger.info(f"当前根系深度为{root_depth}m,小于0.3m,应用系数0.5")
                return 0.5
            else:
                logger.info(f"当前根系深度为{root_depth}m,大于等于0.3m,应用系数1.0")
                return 1.0   
        except Exception as e:
            logger.error(f"获取根系深度系数时出错: {str(e)}")
            return 1.0  
    
    def get_growth_stage_coefficient(self):
        """获取生育阶段系数
        Returns:
            float: 生育阶段系数
        """
        try:
            growth_stages_file = os.path.join(project_root, 'data/growth/growth_stages.csv')
            if not os.path.exists(growth_stages_file):
                logger.warning(f"生育阶段文件不存在: {growth_stages_file},使用默认系数1.0")
                return 1.0
                
            growth_stages_df = pd.read_csv(growth_stages_file)
            if growth_stages_df.empty:
                logger.warning("生育阶段文件为空,使用默认系数1.0")
                return 1.0
            growth_stages_df['开始日期'] = pd.to_datetime(growth_stages_df['开始日期'])
            growth_stages_df['结束日期'] = pd.to_datetime(growth_stages_df['结束日期'])
            now = datetime.now().date()
            current_stage = None
            for _, stage in growth_stages_df.iterrows():
                start_date = stage['开始日期'].date()
                end_date = stage['结束日期'].date()
                
                if start_date <= now <= end_date:
                    current_stage = stage['阶段']
                    break
            #获取生育阶段系数
            stage_coefficients = self.config.GROWTH_STAGE_COEFFICIENTS
            if current_stage and current_stage in stage_coefficients:
                coefficient = stage_coefficients[current_stage]
                logger.info(f"当前生育阶段为：{current_stage}，应用系数{coefficient}")
                return coefficient
            else:
                logger.warning(f"无法确定当前生育阶段或找不到对应系数,使用默认系数1.0")
                return 1.0
                
        except Exception as e:
            logger.error(f"获取生育阶段系数时出错: {str(e)}")
            return 1.0  
        
    def calculate_soil_humidity_differences(self, max_humidity, real_humidity, min_humidity):
        """计算土壤湿度指标
        
        Args:
            max_humidity (float): 最大土壤湿度，即饱和含水量(SAT) (%)
            real_humidity (float): 实际土壤湿度 (%)
            min_humidity (float): 最小土壤湿度，即萎蔫点(PWP) (%)
            
        Returns:
            tuple: (田间持水量(mm), 萎蔫点(Pmm), 蓄水潜力(mm), 有效储水量(mm))
        """
        try:
            
            diff_max_real = max_humidity - real_humidity  
            diff_real_min = real_humidity - min_humidity  
            
            logger.info(f"计算土壤湿度差异:max={max_humidity}%, real={real_humidity}%, min={min_humidity}%")
            logger.info(f"差异结果:diff_max_real={diff_max_real}%, diff_real_min={diff_real_min}%")
            
            soil_depth = self.config.IRRIGATION_CONFIG.get('SOIL_DEPTH_CM', 30.0)
            
            out_file = os.path.join(project_root, 'data/model_output/wheat2024.out')
            root_depth_coefficient = self.get_root_depth_coefficient(out_file)
            
            growth_stage_coefficient = self.get_growth_stage_coefficient()
            
            device_id = self.config.IRRIGATION_CONFIG.get('DEFAULT_DEVICE_ID', '16031600028481')
            field_id = self.config.IRRIGATION_CONFIG.get('DEFAULT_FIELD_ID', '1810564502987649024')
            
            from src.devices.soil_sensor import SoilSensor
            soil_sensor = SoilSensor(device_id=device_id, field_id=field_id)
            sensor_data = soil_sensor.get_current_data()
            fc_percent = sensor_data.get('fc', 25.0)
            sat_percent = sensor_data.get('sat',35.5)
            pwp_percent = sensor_data.get('pwp',15.2)
            
            SAT = sat_percent * soil_depth / 10 * root_depth_coefficient * growth_stage_coefficient
            FC = fc_percent * soil_depth / 10 * root_depth_coefficient * growth_stage_coefficient
            PWP = pwp_percent * soil_depth / 10 * root_depth_coefficient * growth_stage_coefficient
            
            diff_max_real_mm = diff_max_real * soil_depth / 10 * root_depth_coefficient * growth_stage_coefficient
            diff_min_real_mm = diff_real_min * soil_depth / 10 * root_depth_coefficient * growth_stage_coefficient
            diff_com_real_mm = (fc_percent-real_humidity) * soil_depth / 10 * root_depth_coefficient * growth_stage_coefficient
            
            logger.info(f"土壤湿度计算结果: FC={FC:.2f}, PWP={PWP:.2f}")
            logger.info(f"应用系数: 根系深度系数={root_depth_coefficient}, 生育阶段系数={growth_stage_coefficient}")
            return SAT,FC, PWP, diff_max_real_mm, diff_min_real_mm,diff_com_real_mm
            
        except Exception as e:
            logger.error(f"计算土壤湿度差异时出错: {str(e)}")
            raise
            
    def get_irrigation_decision(self, out_file, diff_max_real_mm, diff_min_real_mm,diff_com_real_mm):
        """获取灌溉决策
        Args:
            out_file (str): 模型输出文件路径
            diff_max_real_mm (float): 最大与实际湿度差值(mm)
            diff_min_real_mm (float): 实际与最小湿度差值(mm)
            
        Returns:
            tuple: (date, irrigation_value, message)
        """
        try:
            if not os.path.exists(out_file):
                raise FileNotFoundError(f"模型输出文件不存在: {out_file}")
                
            df = pd.read_csv(out_file, delim_whitespace=True, skiprows=10)
            if df.empty:
                raise ValueError("模型输出文件为空")
                
            df['Date'] = pd.to_datetime(df['Date'], format='%m/%d/%y')
            now = pd.to_datetime(datetime.now().date())
            
            # 获取预测天数和数据
            max_forecast_days = self.config.IRRIGATION_CONFIG['MAX_FORECAST_DAYS']
            future_data = df[
                (df['Date'] >= now) & 
                (df['Date'] <= (now + pd.to_timedelta(f'{max_forecast_days} days')))
            ]
            
            if len(future_data) < 3:  
                raise ValueError(f"没有足够的未来数据用于决策，当前仅有{len(future_data)}天")
            
            # 获取生育阶段系数和灌溉阈值
            growth_stage_coefficient = self.get_growth_stage_coefficient()
            irrigation_threshold = self.config.IRRIGATION_CONFIG['IRRIGATION_THRESHOLD'] * growth_stage_coefficient
            
            # 分析降雨情况
            has_rain = (future_data["Rain"] > 0).any()
            first_rain_day = None
            first_rain_amount = 0
            
            if has_rain:
                rain_days = future_data[future_data['Rain'] > 0]
                if not rain_days.empty:
                    first_rain_day = rain_days.iloc[0]['Date']
                    first_rain_amount = rain_days.iloc[0]['Rain']
            
            # 计算蒸散量
            future_data['Cumulative_ETcadj'] = future_data['ETc'].cumsum()
            
            # 获取关键天数的数据
            third_day = min(now + pd.to_timedelta('2 days'), future_data.iloc[-1]['Date'])
            third_day_data = future_data.loc[future_data["Date"]==third_day]
            
            if third_day_data.empty:
                raise ValueError(f"无法找到第三天({third_day.strftime('%Y-%m-%d')})的数据")
                
            third_day_etcadj = third_day_data['Cumulative_ETcadj'].values[0]
            
            # 获取最小有效灌溉量（默认5mm）
            min_effective_irrigation = self.config.IRRIGATION_CONFIG.get('MIN_EFFECTIVE_IRRIGATION', 5.0)
            
            # 决策逻辑
            if diff_min_real_mm <= 0:
                # 土壤水分已低于萎蔫点，立即灌溉至持水点
                irrigation_value = min(diff_com_real_mm, 30.0) 
                irrigation_value = self._quantize_irrigation(irrigation_value)
                return now, irrigation_value, "土壤水分已达临界水平，立即灌溉"
                
            if third_day_etcadj <= diff_min_real_mm * irrigation_threshold:
                # 水分足够未来三天使用
                return now, 0, "水分充足，今日不灌溉"
            
            # 未来有降雨的情况
            if has_rain:
                days_to_rain = (first_rain_day - now).days if first_rain_day else max_forecast_days
                
                # 降雨在3天以内且雨量充足（>5mm）
                if days_to_rain <= 3 and first_rain_amount >= 5:
                    return now, 0, f"未来{days_to_rain}天内有{first_rain_amount:.1f}mm降雨，延迟灌溉"
                    
                # 降雨在三天后，需要判断是否需要部分灌溉
                if first_rain_day and first_rain_day > third_day:
                    irrigation_value = third_day_etcadj - diff_min_real_mm * irrigation_threshold
                    if irrigation_value > min_effective_irrigation:
                        irrigation_value = self._quantize_irrigation(irrigation_value)
                        return now, irrigation_value, f"今日需灌溉{irrigation_value:.1f}mm，降雨在三天后"
                
                # 近日有降雨但不足以满足需求
                if first_rain_day and first_rain_day > now:
                    first_rain_data = future_data[future_data["Date"]==first_rain_day]
                    if not first_rain_data.empty:
                        irrigation_value = first_rain_data['Cumulative_ETcadj'].values[0] - diff_min_real_mm * irrigation_threshold
                        if irrigation_value > min_effective_irrigation:
                            irrigation_value = self._quantize_irrigation(irrigation_value)
                            return now, irrigation_value, f"今日需灌溉{irrigation_value:.1f}mm，近日有降雨但不足以满足需求"
                    
                return now, 0, "今日有降雨预报，不灌溉"
                
            # 无降雨情况
            irrigation_value = min(
                diff_com_real_mm, 
                third_day_etcadj - diff_min_real_mm * irrigation_threshold  
            )
            
            # 确保灌溉量大于最小有效值
            if irrigation_value <= min_effective_irrigation:
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
        # 灌溉档位
        irrigation_levels = [0, 5, 10, 15, 20, 25, 30, 40, 50]
        
        if irrigation_value <= 0:
            return 0
            
        for level in irrigation_levels:
            if irrigation_value <= level:
                return level
                
        return irrigation_levels[-1]  # 返回最大档位
            
    def make_irrigation_decision(self, field_id, max_humidity, min_humidity, real_humidity):
        """生成灌溉决策
        
        Args:
            field_id (str): 地块ID
            max_humidity (float): 最大土壤湿度(饱和含水量SAT)
            min_humidity (float): 最小土壤湿度(萎蔫点PWP)
            real_humidity (float): 实际土壤湿度
            
        Returns:
            dict: 包含灌溉决策信息的字典
        """
        try:
            device_id = self.config.IRRIGATION_CONFIG.get('DEFAULT_DEVICE_ID', '16031600028481')
            from src.devices.soil_sensor import SoilSensor
            soil_sensor = SoilSensor(device_id=device_id, field_id=field_id)
            sensor_data = soil_sensor.get_current_data()
            fc_percent = sensor_data.get('fc', 25.0)  
            sat_percent = sensor_data.get('sat',35.5)
            pwp_percent = sensor_data.get('pwp',15.2)
            logger.info(f"使用湿度参数: sat_percent={sat_percent}, fc_percent={fc_percent}, pwp_percent={pwp_percent}, real_humidity={real_humidity}")
            
            SAT,FC, PWP, diff_max_real_mm, diff_min_real_mm,diff_com_real_mm = self.calculate_soil_humidity_differences(
                max_humidity, real_humidity, min_humidity
            )
            
            now = datetime.now()
            if (self._last_model_run is None or 
                self._last_model_run.date() != now.date()):
                self.fao_model.run_model()
                self._last_model_run = now
            
            out_file = os.path.join(project_root, 'data/model_output/wheat2024.out')
            date, irrigation_value, message = self.get_irrigation_decision(
                out_file, diff_max_real_mm, diff_min_real_mm,diff_com_real_mm
            )
            
            root_depth_coefficient = self.get_root_depth_coefficient(out_file)
            growth_stage_coefficient = self.get_growth_stage_coefficient()
            soil_depth = self.config.IRRIGATION_CONFIG['SOIL_DEPTH_CM']
            # 蓄水潜力 (mm)
            storage_potential_mm = (max_humidity - real_humidity) * soil_depth / 10 * root_depth_coefficient * growth_stage_coefficient
            # 有效储水量 (mm)
            effective_storage_mm = (real_humidity - fc_percent) * soil_depth / 10 * root_depth_coefficient * growth_stage_coefficient
            # 可利用储水量 (mm)
            available_storage_mm = (real_humidity - min_humidity) * soil_depth / 10 * root_depth_coefficient * growth_stage_coefficient
            if storage_potential_mm < 0:
                logger.warning(f"蓄水潜力计算出负值 ({storage_potential_mm}),调整为0")
                storage_potential_mm = 0
                
            if effective_storage_mm < 0:
                logger.warning(f"有效储水量计算出负值 ({effective_storage_mm}),调整为0")
                effective_storage_mm = 0
            
            logger.info(f"储水指标计算详情: 土壤深度={soil_depth}cm, 根系系数={root_depth_coefficient}, 生育阶段系数={growth_stage_coefficient}")
            logger.info(f"百分比数据: 饱和含水量={max_humidity}%, 田间持水量={fc_percent}%, 凋萎点={min_humidity}%, 当前湿度={real_humidity}%")
            logger.info(f"毫米数据: 蓄水潜力={storage_potential_mm}mm, 有效储水量={effective_storage_mm}mm, 可利用储水量={available_storage_mm}mm")
            
            return {
                "date": date.strftime('%Y-%m-%d'),
                "field_id": field_id,
                "message": f"当前土壤体积含水量为：{real_humidity:.2f} %, {message}",
                "irrigation_value": round(irrigation_value, 2) if irrigation_value else 0,
                "soil_data": {
                    "current_humidity": round(real_humidity, 2),  
                    "root_depth_coefficient": root_depth_coefficient,  
                    "growth_stage_coefficient": growth_stage_coefficient, 
                    "soil_depth": soil_depth,  
                    "storage_potential": round(storage_potential_mm, 2), 
                    "effective_storage": round(effective_storage_mm, 2),  
                    "available_storage": round(available_storage_mm, 2),  
                    "sat": round(SAT, 2),  
                    "fc": round(FC, 2),  
                    "pwp": round(PWP, 2),  
                    "max_humidity": round(max_humidity, 2),  
                    "min_humidity": round(min_humidity, 2), 
                    "is_real_data": True
                }
            }
            
        except Exception as e:
            logger.error(f"生成灌溉决策时出错: {str(e)}")
            raise
    # 未引用（备用）
    def get_soil_data(self, field_id=None):
        """获取土壤数据
        Args:
            field_id (str, optional): 地块ID. 如果不提供，则使用默认值
        Returns:
            dict: 土壤数据对象
        """
        try:
            if field_id is None:
                field_id = self.config.IRRIGATION_CONFIG.get('DEFAULT_FIELD_ID')
                
            device_id = self.config.IRRIGATION_CONFIG.get('DEFAULT_DEVICE_ID', '16031600028481')
            
            from src.devices.soil_sensor import SoilSensor
            soil_sensor = SoilSensor(device_id=device_id, field_id=field_id)
            sensor_data = soil_sensor.get_current_data()
            
            sat = sensor_data.get('sat', 35.5)  
            fc = sensor_data.get('fc', 25.0)    
            pwp = sensor_data.get('pwp', 15.2) 
            real_humidity = sensor_data.get('real_humidity', 31.90) 
            is_real_data = sensor_data.get('is_real_data', True)
            
            out_file = os.path.join(project_root, 'data/model_output/wheat2024.out')
            root_depth_coefficient = self.get_root_depth_coefficient(out_file)
            
            growth_stage_coefficient = self.get_growth_stage_coefficient()
            
            soil_depth = self.config.IRRIGATION_CONFIG.get('SOIL_DEPTH_CM', 30.0)
            
            field_capacity = fc * soil_depth / 10 * root_depth_coefficient * growth_stage_coefficient
            
            wilting_point = pwp * soil_depth / 10 * root_depth_coefficient * growth_stage_coefficient
            
            saturation_water = sat * soil_depth / 10 * root_depth_coefficient * growth_stage_coefficient
            
            storage_potential = (sat - real_humidity) * soil_depth / 10 * root_depth_coefficient * growth_stage_coefficient
            
            effective_storage = (real_humidity - fc) * soil_depth / 10 * root_depth_coefficient * growth_stage_coefficient
            if effective_storage < 0:
                effective_storage = 0
            
            available_storage = (real_humidity - pwp) * soil_depth / 10 * root_depth_coefficient * growth_stage_coefficient
            
            result = {
                'field_id': field_id,
                'device_id': device_id,
                'max_humidity': sat,  
                'min_humidity': pwp,  
                'real_humidity': real_humidity,
                'sat': sat,  
                'pwp': pwp,  
                'fc': fc, 
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'is_real_data': is_real_data,
                'soil_depth': soil_depth,
                'root_depth_coefficient': root_depth_coefficient,
                'growth_stage_coefficient': growth_stage_coefficient,
                'field_capacity_mm': field_capacity,
                'wilting_point_mm': wilting_point,
                'saturation_water_mm':saturation_water,
                'storage_potential_mm': storage_potential,
                'effective_storage_mm': effective_storage,
                'available_storage_mm': available_storage
            }
            
            logger.info(f"获取土壤数据成功: field_id={field_id}, real_humidity={result['real_humidity']}, is_real_data={result['is_real_data']}")
            logger.info(f"土壤水分参数: 饱和含水量={sat}%, 田间持水量={fc}%, 凋萎点={pwp}%, 当前湿度={real_humidity}%")
            logger.info(f"系数: 根系系数={root_depth_coefficient}, 生育期系数={growth_stage_coefficient}")
            logger.info(f"计算的mm值: 饱和含水量={saturation_water:.2f}mm,田间持水量={field_capacity:.2f}mm, 凋萎点={wilting_point:.2f}mm, 可利用储水量={available_storage:.2f}mm,有效储水量={effective_storage:.2f}mm,蓄水潜力={storage_potential:.2f}mm")
            
            return result
        except Exception as e:
            logger.error(f"获取土壤数据失败: {str(e)}")
            raise

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
        field_id = config.IRRIGATION_CONFIG['DEFAULT_FIELD_ID']
        max_humidity = 35.5  # 最大土壤湿度
        min_humidity = 15.2  # 最小土壤湿度
        real_humidity = 25.8  # 实际土壤湿度
        
        # 生成灌溉决策
        result = irrigation_service.make_irrigation_decision(
            field_id, max_humidity, min_humidity, real_humidity
        )
        
        # 打印结果
        print("\n=== 灌溉决策结果 ===")
        print(f"日期: {result['date']}")
        print(f"地块ID: {result['field_id']}")
        print(f"消息: {result['message']}")
        print(f"灌溉量(mm): {result['irrigation_value']}")
        print("\n土壤数据:")
        print(f"田间持水量: {result['soil_data']['field_capacity']}")
        print(f"凋萎点: {result['soil_data']['wilting_point']}")
        print(f"当前湿度: {result['soil_data']['current_humidity']}")
        print(f"根系深度系数: {result['soil_data']['root_depth_coefficient']}")
        print(f"生育阶段系数: {result['soil_data']['growth_stage_coefficient']}")
        
    except Exception as e:
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()
"""