import pandas as pd
import os
import datetime  
from aquacrop import AquaCropModel, Soil, Crop, InitialWaterContent, IrrigationManagement
from aquacrop.utils import prepare_weather, get_filepath
import matplotlib.pyplot as plt
import json
import logging
import sys
from typing import Dict, List, Optional, Union
from dataclasses import dataclass, field

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('aquacrop.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

@dataclass
class ModelConfig:
    """模型配置数据类"""
    SOIL_LAYERS: int = 3
    CHART_FIGSIZE: tuple = (10, 6)
    DPI: int = 100
    CHART_COLORS: List[str] = field(default_factory=lambda: ['#87CEEB', '#FFD700', '#90EE90', '#FFA07A', '#9370DB', '#40E0D0'])
    
    def __post_init__(self):
        pass

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

def convert_irrigation_weather_to_aquacrop_format(input_file_path: str, output_txt_path: str) -> str:
    """转换气象数据格式为AquaCrop模型所需格式
    Args:
        input_file_path: 输入气象数据文件路径 (.csv 或 .wth)
        output_txt_path: 输出的aquacrop_weather.txt文件路径
    
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
                if '-' in date_sample and len(date_sample.split('-')) == 2:
                    logger.info("检测到年份-日序号(DOY)日期格式，正在转换...")
                    
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
                    
                    weather_df['Date'] = weather_df['Date'].apply(convert_year_doy_to_date)
                else:
                    weather_df['Date'] = pd.to_datetime(weather_df['Date'], errors='coerce')
            elif '日期' in weather_df.columns:
                weather_df['Date'] = pd.to_datetime(weather_df['日期'])
                weather_df = weather_df.drop('日期', axis=1)
            
            # 列名映射
            column_mapping = {
                '最高温度': 'Tmax',
                '最低温度': 'Tmin',
                '降雨量': 'Precipitation',
                '参考蒸散量': 'ETo',
            }
            
            for chinese_name, english_name in column_mapping.items():
                if chinese_name in weather_df.columns:
                    weather_df[english_name] = weather_df[chinese_name]
                    weather_df = weather_df.drop(chinese_name, axis=1)
                    logger.info(f"已转换列名: {chinese_name} -> {english_name}")
        
        # 确保必要的列存在
        if 'Rain' in weather_df.columns and 'Precipitation' not in weather_df.columns:
            weather_df['Precipitation'] = weather_df['Rain']
            logger.info("使用Rain列作为Precipitation")
        
        if 'Etref' in weather_df.columns and 'ETo' not in weather_df.columns:
            weather_df['ETo'] = weather_df['Etref']
            logger.info("使用Etref列作为ETo")
        
        # 处理缺失的ETo数据
        if 'ETo' not in weather_df.columns or weather_df['ETo'].isnull().any() or (weather_df['ETo'] == 0).any():
            logger.info("检测到缺失的参考蒸散量(ETo)数据，使用Hargreaves方法估算...")
            # 确保我们有Tmax和Tmin数据
            if 'Tmax' in weather_df.columns and 'Tmin' in weather_df.columns:
                # 如果列不存在，创建它
                if 'ETo' not in weather_df.columns:
                    weather_df['ETo'] = 0.0
                
                # 计算缺失值的索引
                missing_mask = weather_df['ETo'].isnull() | (weather_df['ETo'] == 0)
                
                # 只对缺失值应用Hargreaves公式
                weather_df.loc[missing_mask, 'ETo'] = 0.0023 * ((weather_df.loc[missing_mask, 'Tmax'] + weather_df.loc[missing_mask, 'Tmin']) / 2 + 17.8) * (weather_df.loc[missing_mask, 'Tmax'] - weather_df.loc[missing_mask, 'Tmin'])**0.5 * 0.408
                
                logger.info(f"已估算{missing_mask.sum()}行缺失的ETo数据")
            else:
                raise ValueError("缺少最高温度(Tmax)或最低温度(Tmin)数据，无法估算ETo")
        
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
        os.makedirs(os.path.dirname(output_txt_path), exist_ok=True)
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
    try:
        today = datetime.datetime.now().date()
        logger.debug(f"当前日期: {today}")
        
        for stage in stage_results:
            start_date = stage["开始日期"].date() if isinstance(stage["开始日期"], datetime.datetime) else stage["开始日期"]
            end_date = stage["结束日期"].date() if isinstance(stage["结束日期"], datetime.datetime) else stage["结束日期"]
            
            if start_date <= today <= end_date:
                total_days = (end_date - start_date).days
                days_passed = (today - start_date).days
                progress = round(days_passed / total_days * 100, 2) if total_days > 0 else 0
                
                result = {
                    "阶段": stage["阶段"],
                    "开始日期": start_date.strftime('%Y-%m-%d'),
                    "结束日期": end_date.strftime('%Y-%m-%d'),
                    "进度": progress,
                    "持续天数": stage["持续天数"],
                    "已过天数": days_passed
                }
                logger.info(f"当前生育阶段: {result['阶段']}, 进度: {progress}%")
                return result
        
        if stage_results:
            first_stage_start = stage_results[0]["开始日期"].date() if isinstance(stage_results[0]["开始日期"], datetime.datetime) else stage_results[0]["开始日期"]
            last_stage_end = stage_results[-1]["结束日期"].date() if isinstance(stage_results[-1]["结束日期"], datetime.datetime) else stage_results[-1]["结束日期"]
            
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
    
    print("\n===== 分析小麦生育阶段 =====")
    

    config = current_config().AQUACROP_CONFIG
    standard_stages = config.get('GROWTH_STAGES_DAP', config.get('GROWTH_STAGES', []))
    
    df = daily_crop_growth.copy().sort_values("dap")
    
    stage_results = []
    
    min_available_dap = df["dap"].min()
    max_available_dap = df["dap"].max()
    print(f"模型中可用的DAP范围: {min_available_dap} - {max_available_dap}")
    
    date_diffs = df["Date"].diff().dropna()
    if not all(diff == pd.Timedelta(days=1) for diff in date_diffs):
        print("警告: 模型日期不连续，将尝试修正")
    
    for i, stage in enumerate(standard_stages):
        stage_name = stage["阶段"]
        start_dap = max(stage["开始DAP"], min_available_dap)  
        end_dap = min(stage["结束DAP"], max_available_dap)    
        
        if start_dap > max_available_dap or end_dap < min_available_dap:
            print(f"跳过 {stage_name}: DAP范围 {stage['开始DAP']}-{stage['结束DAP']} 超出模型可用范围")
            continue
        
        stage_data = df[(df["dap"] >= start_dap) & (df["dap"] <= end_dap)]
        
        if not stage_data.empty:
            start_date = stage_data["Date"].min()
            end_date = stage_data["Date"].max()
            
            if i > 0 and stage_results:
                previous_end_date = stage_results[-1]["结束日期"]
                expected_start_date = previous_end_date + pd.Timedelta(days=1)
                
                if start_date != expected_start_date:
                    print(f"调整 {stage_name} 开始日期从 {start_date.strftime('%Y-%m-%d')} 到 {expected_start_date.strftime('%Y-%m-%d')} 以保持连续性")
                    start_date = expected_start_date
                    start_dap_row = df[df["Date"] >= start_date]
                    if not start_dap_row.empty:
                        start_dap = start_dap_row.iloc[0]["dap"]
            
            duration = (end_date - start_date).days + 1
            
            stage_results.append({
                "阶段": stage_name,
                "开始日期": start_date,
                "结束日期": end_date,
                "开始DAP": start_dap,
                "结束DAP": end_dap,
                "持续天数": duration
            })
            
            print(f"{stage_name}: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}，持续{duration}天 (DAP: {start_dap:.1f}-{end_dap:.1f})")
    
    if stage_results:
        total_start_date = stage_results[0]["开始日期"]
        total_end_date = stage_results[-1]["结束日期"]
        total_duration = (total_end_date - total_start_date).days + 1
        print(f"\n总生育期: {total_start_date.strftime('%Y-%m-%d')} 至 {total_end_date.strftime('%Y-%m-%d')}，共{total_duration}天")
    
    return stage_results

def create_growth_stages_visualization(stage_results: List[Dict], current_stage: Optional[Dict], static_dir: str) -> str:
    """创建生育期可视化图表
    
    Args:
        stage_results: 生育阶段结果列表
        current_stage: 当前生育阶段信息
        static_dir: 静态文件目录路径
        
    Returns:
        str: 生成的图表文件路径
        
    Raises:
        ValueError: 当输入数据无效时
    """
    try:
        if not stage_results:
            raise ValueError("生育阶段数据为空")
            
        logger.info("开始创建生育期可视化图表")
        
        plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
        plt.rcParams['axes.unicode_minus'] = False
        
        config = ModelConfig()
        
        plt.figure(figsize=config.CHART_FIGSIZE)
        
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
                        plt.text(bars[i].get_width() - 15, bars[i].get_y() + bars[i].get_height()/2, 
                                "当前", 
                                va='center', ha='right', color='white', 
                                bbox=dict(boxstyle="round,pad=0.3", fc='red', alpha=0.7))
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
        growth_dir = os.path.join(static_dir, 'images')
        os.makedirs(growth_dir, exist_ok=True)
        growth_stages_img_path = os.path.join(growth_dir, 'growth_stages.png')
        
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
    print("\n===== 小麦生育阶段分析（冠层覆盖度） =====")
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
    
    df = daily_crop_growth.copy()
    df = df.sort_values("Date")
    
    stage_ranges = []
    
    for stage in growth_stages:
        stage_data = df[(df["canopy_cover"] >= stage["min_cc"]) & (df["canopy_cover"] < stage["max_cc"])]
        
        if not stage_data.empty:
            stage_ranges.append({
                "阶段": stage["阶段"],
                "原始开始日期": stage_data["Date"].min(),
                "原始结束日期": stage_data["Date"].max(),
                "开始DAP": stage_data["dap"].min(),
                "结束DAP": stage_data["dap"].max()
            })
    
    if len(stage_ranges) < 2:
        print("未找到足够的生育阶段数据，无法分析")
        return []
    
    stage_order = {stage["阶段"]: i for i, stage in enumerate(growth_stages)}
    stage_ranges.sort(key=lambda x: stage_order.get(x["阶段"], 99))
    
    print("\n原始阶段日期范围:")
    for stage in stage_ranges:
        print(f"{stage['阶段']}: {stage['原始开始日期'].strftime('%Y-%m-%d')} 至 {stage['原始结束日期'].strftime('%Y-%m-%d')} (DAP: {stage['开始DAP']:.1f}-{stage['结束DAP']:.1f})")
    
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
                end_dap = end_day_data["dap"] if end_day_data is not None else stage["结束DAP"]
            else:
                end_date = next_start_date - pd.Timedelta(days=1)
                end_day_data = df[df["Date"] <= end_date].iloc[-1] if not df[df["Date"] <= end_date].empty else None
                end_dap = end_day_data["dap"] if end_day_data is not None else stage["结束DAP"]
        
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
            
            print(f"{stage['阶段']}: {current_start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}，持续{duration}天 (DAP: {current_start_dap:.1f}-{end_dap:.1f})")
            
            if i < len(stage_ranges) - 1:
                current_start_date = end_date + pd.Timedelta(days=1)
                next_day_data = df[df["Date"] >= current_start_date].iloc[0] if not df[df["Date"] >= current_start_date].empty else None
                current_start_dap = next_day_data["dap"] if next_day_data is not None else end_dap + 1
    
    is_continuous = True
    for i in range(1, len(stage_results)):
        prev_end = stage_results[i-1]["结束日期"]
        curr_start = stage_results[i]["开始日期"]
        
        days_diff = (curr_start - prev_end).days
        
        if days_diff != 1:
            is_continuous = False
            print(f"警告: 连续性检查失败! {stage_results[i-1]['阶段']}结束于{prev_end.strftime('%Y-%m-%d')}，{stage_results[i]['阶段']}开始于{curr_start.strftime('%Y-%m-%d')}，间隔{days_diff}天")
    
    if is_continuous:
        print("\n验证成功: 所有生育期日期完全连续!")
    
    if stage_results:
        total_start_date = stage_results[0]["开始日期"]
        total_end_date = stage_results[-1]["结束日期"]
        total_duration = (total_end_date - total_start_date).days + 1
        print(f"\n总生育期: {total_start_date.strftime('%Y-%m-%d')} 至 {total_end_date.strftime('%Y-%m-%d')}，共{total_duration}天")
    
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
        
        static_dir = os.path.join(project_root, 'src/static')
        os.makedirs(static_dir, exist_ok=True)
        
        # 转换气象数据 - 优先使用.wth文件
        output_txt_path = os.path.join(model_irr_dir, config['WEATHER_OUTPUT_TXT'])
        
        # 尝试使用.wth文件，如果不存在则回退到使用CSV文件
        input_wth_path = os.path.join(project_root, fao_config['TEMP_WEATHER_FILE'])
        if os.path.exists(input_wth_path):
            logger.info(f"使用.wth格式气象文件: {input_wth_path}")
            converted_file = convert_irrigation_weather_to_aquacrop_format(input_wth_path, output_txt_path)
        else:
            input_csv_path = os.path.join(project_root, config['WEATHER_INPUT_CSV'])
            if not os.path.exists(input_csv_path):
                raise FileNotFoundError(f"未找到任何有效的气象数据文件: 既不存在.wth文件 {input_wth_path} 也不存在CSV文件 {input_csv_path}")
            logger.info(f"使用CSV格式气象文件: {input_csv_path}")
            converted_file = convert_irrigation_weather_to_aquacrop_format(input_csv_path, output_txt_path)
            
        filepath = get_filepath(converted_file)
        
        # 准备气象数据
        weather_data = prepare_weather(filepath)
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
            device_id = config.IRRIGATION_CONFIG.get('DEFAULT_DEVICE_ID', '16031600028481')
            field_id = config.IRRIGATION_CONFIG.get('DEFAULT_FIELD_ID', '1810564502987649024')
            
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
        
        for _ in range(ModelConfig.SOIL_LAYERS):
            soil_texture.add_layer(
                thickness=soil_texture.zSoil,
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
        irr_dates = pd.date_range(
            start=config['SIM_START_TIME'],
            end=config['SIM_END_TIME'],
            freq=config['IRR_FREQUENCY']
        )
        irr_schedule = pd.DataFrame({
            "Date": irr_dates,
            "Depth": [config['IRR_DEPTH']] * len(irr_dates)
        })
        irr_mngt = IrrigationManagement(irrigation_method=1)
        
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
        
        # 保存作物生长数据
        daily_crop_growth.to_csv(os.path.join(model_irr_dir, "daily_crop_growth.csv"), index=False)
        yield_output = model_result['Dry yield (tonne/ha)'].mean()
        logger.info(f"预计产量: {yield_output:.2f} 吨/公顷")
        
        # 添加日期列
        date_range = pd.date_range(start=config['SIM_START_TIME'], end=config['SIM_END_TIME'], freq='D')
        daily_crop_growth.insert(0, "Date", date_range)
        
        # 保存水分数据
        daily_water_storage["Date"] = date_range
        daily_water_storage.to_csv(os.path.join(model_irr_dir, "daily_water_storage.csv"), index=False)
        
        daily_water_flux["Date"] = date_range
        daily_water_flux.to_csv(os.path.join(model_irr_dir, "aquacrop_daily_water_flux.csv"), index=False)
        
        # 创建冠层覆盖度图表
        daily_crop_growth = daily_crop_growth[daily_crop_growth["canopy_cover"] != 0]
        
        # 设置中文字体支持
        plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS', 'sans-serif']
        plt.rcParams['axes.unicode_minus'] = False
        plt.rcParams['font.size'] = 12  # 增加字体大小提高可读性
        
        plt.figure(figsize=ModelConfig.CHART_FIGSIZE)
        plt.plot(daily_crop_growth["dap"].values,
                 daily_crop_growth["canopy_cover"].values,
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
        
        images_dir = os.path.join(project_root, config['IMAGES_DIR'])
        os.makedirs(images_dir, exist_ok=True)
        
        canopy_cover_img_path = os.path.join(images_dir, 'canopy_cover.png')
        # 创建ModelConfig实例，使用其DPI属性
        model_config = ModelConfig()
        plt.savefig(canopy_cover_img_path, dpi=model_config.DPI, bbox_inches='tight')
        plt.close()
        
        # 获取图片的相对路径用于前端显示
        # 假设 images_dir 的格式是 '.../src/static/images'，需要提取出 'images/canopy_cover.png'
        # 注意：这里假设 Flask 静态文件目录是标准的 'static'
        relative_path = f'images/canopy_cover.png'
        canopy_img_web_path = f'images/canopy_cover.png'  # 相对于static目录的路径
        
        logger.info(f"冠层覆盖度图表文件已保存到: {canopy_cover_img_path}")
        logger.info(f"冠层覆盖度图表Web路径: {canopy_img_web_path}")
        
        # 分析生育期
        stage_results = analyze_growth_stages(daily_crop_growth)
        if not stage_results:
            logger.warning("使用基于DAP的标准生育期")
            stage_results = get_growth_stages_from_model(daily_crop_growth)
        
        # 保存生育期数据
        stage_df = pd.DataFrame(stage_results)
        stage_df.to_csv(os.path.join(project_root, 'data/growth/growth_stages.csv'), index=False)
        logger.info("生育期数据已保存")
        
        # 获取当前生育阶段
        current_stage = get_current_growth_stage(stage_results)
        
        # 保存当前生育阶段信息
        with open(os.path.join(static_dir, 'current_growth_stage.json'), 'w', encoding='utf-8') as f:
            json.dump(current_stage, f, ensure_ascii=False, indent=4)
        
        # 创建生育期可视化图表
        growth_stages_img_path = create_growth_stages_visualization(stage_results, current_stage, static_dir)
        growth_stages_img_web_path = f'images/growth_stages.png'  # 相对于static目录的路径
        
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
        
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        
        crop_growth_file = os.path.join(project_root, 'src', 'aquacrop', 'daily_crop_growth.csv')
        
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
        run_model_and_save_results()
    except Exception as e:
        logger.error(f"程序运行失败: {str(e)}", exc_info=True)
        sys.exit(1)