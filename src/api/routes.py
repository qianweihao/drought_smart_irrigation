import os
import sys
import json
import traceback
from flask import Blueprint, request, jsonify, render_template, abort, current_app, redirect, Response, url_for
import io
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import logging
from src.utils.auth import token_required, api_key_required  
from functools import wraps
from src.aquacrop.aquacrop_modeling import run_model_and_save_results

logger = logging.getLogger(__name__)

try:
    from src.config.config import get_config
    config = get_config()
except ImportError as e:
    logger.error(f"无法导入配置: {e}")
    from src.config.config import Config
    config = Config()
    logger.warning("使用默认配置")

# 从配置中获取常量
SOIL_DEPTH_CM = config.IRRIGATION_CONFIG.get('SOIL_DEPTH_CM', 30.0)  # 土壤深度（厘米）
MAX_DAYS_RANGE = config.API_CONFIG.get('MAX_DAYS_RANGE', 365)  # 最大查询天数范围
DEFAULT_DAYS = config.API_CONFIG.get('DEFAULT_DAYS', 30)     # 默认查询天数
ET_DATA_MIN_COLUMNS = config.API_CONFIG.get('ET_DATA_MIN_COLUMNS', 20)  # ET数据文件最小列数要求

# 错误处理辅助函数
def create_error_response(message, status_code=500, additional_data=None):
    """创建标准化的错误响应"""
    response_data = {
        'status': 'error',
        'message': message,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    if additional_data:
        response_data.update(additional_data)
    return jsonify(response_data), status_code

try:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except Exception as e:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    logger.warning(f"使用备用方法确定项目根目录: {project_root}")

try:
    from src.services.irrigation_service import IrrigationService
except ImportError as e:
    logger.error(f"无法导入服务类: {e}")

# 定义全局变量
try:
    field_id = config.IRRIGATION_CONFIG.get('DEFAULT_FIELD_ID', '1810564502987649024')
    device_id = config.IRRIGATION_CONFIG.get('DEFAULT_DEVICE_ID', '16031600028481')
    logger.info(f"从配置文件获取field_id={field_id}, device_id={device_id}")
except Exception as e:
    field_id = '1810564502987649024'  
    device_id = '16031600028481'
    logger.warning(f"无法从配置获取device/field ID,使用备用值: {e}")

try:
    from src.devices.soil_sensor import SoilSensor
    logger.info("成功导入SoilSensor类")
except ImportError as e:
    logger.error(f"无法导入SoilSensor类: {e}")

def create_routes(config):
    """创建API路由"""
    try:
        try:
            api = Blueprint('api', __name__, url_prefix='')
        except Exception as e:
            logger.error(f"创建Blueprint时出错: {e}")
            logger.error(traceback.format_exc())
            api = Blueprint('api', __name__)
        
        logger.info(f"创建API Blueprint")
        irrigation_decision_result = None
        
        try:
            irrigation_service = IrrigationService(config)
            logger.info("成功实例化灌溉服务")
        except Exception as e:
            logger.error(f"实例化服务出错: {e}")
            logger.error(traceback.format_exc())
            return api  
        
        def add_cors_headers(response):
            """向响应添加CORS头,允许前端访问"""
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key'
            return response
        
        @api.after_request
        def after_request(response):
            return add_cors_headers(response)
            
        def api_error_handler(f):
            @wraps(f)
            def decorated(*args, **kwargs):
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    logger.error(f"API错误: {str(e)}")
                    logger.error(traceback.format_exc())
                    return jsonify({
                        'status': 'error',
                        'message': str(e),
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }), 500
            return decorated
        
        # 根路径路由
        @api.route('/')
        @api_error_handler
        def index():
            """首页"""
            return render_template('index.html')
        
        # 系统状态API路由
        @api.route('/system_status')
        @api.route('/api/system_status')
        @api.route(f'{config.API_PREFIX}/system_status')
        @api_error_handler
        def system_status():
            """系统状态API"""
            try:
                data_dir = os.path.join(project_root, 'data')
                static_dir = os.path.join(project_root, 'src/static')
                templates_dir = os.path.join(project_root, 'src/templates')
                
                response = {
                    'status': 'ok',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'versions': {
                        'api': config.API_VERSION,
                        'app': '1.0.0'
                    },
                    'directories': {
                        'data': os.path.exists(data_dir),
                        'static': os.path.exists(static_dir),
                        'templates': os.path.exists(templates_dir)
                    }
                }
                
                return jsonify(response)
            except Exception as e:
                logger.error(f"系统状态检查失败: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e),
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }), 500

        # dashboard路由
        @api.route('/dashboard')
        @api_error_handler
        def dashboard():
            """仪表盘页面"""
            try:
                # 调用模型或获取最新结果
                logger.info("开始调用run_model_and_save_results函数")
                model_results = run_model_and_save_results()
                logger.info(f"模型结果: {model_results}")
                default_img = 'images/placeholder.png'
                canopy_cover_img = model_results.get('canopy_cover_img', default_img)
                
                logger.info(f"从模型结果获取的图片路径: {model_results.get('canopy_cover_img', '未找到')}")
                logger.info(f"最终传递给模板的冠层覆盖度图片路径: {canopy_cover_img}")
                return render_template('dashboard.html', 
                                      title='作物智能灌溉仪表盘',
                                      canopy_cover_img=canopy_cover_img)
            except Exception as e:
                logger.error(f"渲染仪表盘时出错: {str(e)}", exc_info=True)
                logger.info("使用默认placeholder.png图片")
                return render_template('dashboard.html', 
                                      title='作物智能灌溉仪表盘',
                                      canopy_cover_img='images/placeholder.png')

        # 实际含水量API路由
        @api.route('/soil_data')
        @api_error_handler
        def view_soil_data():
            """查看土壤数据页面 (可以考虑也用 JS 加载)"""
            try:
                soil_sensor = SoilSensor(device_id, field_id)
                logger.info(f"开始获取土壤数据页面数据: field_id={field_id}")
                sensor_data = soil_sensor.get_current_data()

                if not sensor_data.get('is_mock_data', False):
                    soil_data = {
                        'max_humidity': sensor_data.get('max_humidity', config.SOIL_SENSOR_DEFAULTS['DEFAULT_MAX_HUMIDITY']),
                        'min_humidity': sensor_data.get('min_humidity', config.SOIL_SENSOR_DEFAULTS['DEFAULT_MIN_HUMIDITY']),
                        'real_humidity': sensor_data.get('real_humidity', config.SOIL_SENSOR_DEFAULTS['DEFAULT_REAL_HUMIDITY'])
                    }
                    logger.info(f"成功获取真实土壤数据: {soil_data}")
                    return render_template('soil_data.html', soil_data=soil_data, field_id=field_id)
                else:
                    logger.warning("无法获取真实土壤数据，显示空页面或提示")
                    return render_template('soil_data.html', soil_data=None, error='无法获取真实土壤数据', field_id=field_id)
            except Exception as e:
                logger.error(f"查看土壤数据时出错: {str(e)}")
                return render_template('soil_data.html', soil_data=None, error='加载土壤数据失败', field_id=field_id), 500
        
        @api.route('/soil_humidity_history')
        @api.route('/api/soil_humidity_history')
        @api_error_handler
        def soil_humidity_history():
            """获取土壤湿度历史数据 API"""
            try:
                soil_sensor = SoilSensor(device_id, field_id)
                days = request.args.get('days', default=DEFAULT_DAYS, type=int)
                if days <= 0 or days > MAX_DAYS_RANGE:
                    return create_error_response(
                        f'无效的天数参数: {days},天数应在1-{MAX_DAYS_RANGE}之间',
                        400,
                        {'valid_range': f'1-{MAX_DAYS_RANGE}'}
                    )
                history_data_df = soil_sensor.get_history_humidity_data(days=days)
                if history_data_df is None or history_data_df.empty or 'date' not in history_data_df.columns:
                    logger.warning("获取土壤湿度历史数据 API: 未找到有效数据")
                    return create_error_response('无法获取有效的土壤湿度历史数据', 404)
                if not pd.api.types.is_datetime64_any_dtype(history_data_df['date']):
                    history_data_df['date'] = pd.to_datetime(history_data_df['date'], errors='coerce')
                history_data_df = history_data_df.replace({np.nan: None})
                result = {
                    'dates': history_data_df['date'].dt.strftime('%Y-%m-%d').tolist(),
                    'soilHumidity10Value': history_data_df['soilHumidity10Value'].tolist(),
                    'soilHumidity20Value': history_data_df['soilHumidity20Value'].tolist(),
                    'soilHumidity30Value': history_data_df['soilHumidity30Value'].tolist(),
                }
                logger.info(f"API成功返回土壤湿度历史数据: {len(result['dates'])}天")
                return jsonify({'status': 'success', 'data': result})

            except Exception as e:
                logger.error(f"获取土壤湿度历史数据 API 时出错: {str(e)}")
                logger.error(traceback.format_exc())
                return create_error_response('获取土壤湿度历史数据失败', 500)
        
        # 灌溉决策触发 API 路由 (POST)
        @api.route('/make_decision', methods=['POST'])
        @api_error_handler
        def make_decision_api():
            """触发灌溉决策生成任务"""
            try:
                soil_sensor = SoilSensor(device_id, field_id)
                logger.info(f"API 触发灌溉决策: field_id={field_id}")
                sensor_data = soil_sensor.get_current_data()

                if not sensor_data.get('is_real_data', False): # 修改判断条件，检查is_real_data而不是is_mock_data
                     logger.warning("生成决策失败: 无法获取真实土壤数据")
                     return create_error_response('无法获取真实土壤数据进行决策', 400)
                result = irrigation_service.make_irrigation_decision(
                    field_id,
                    sensor_data['max_humidity'],
                    sensor_data['min_humidity'],
                    sensor_data['real_humidity']
                )

                if result and isinstance(result, dict):
                    logger.info(f"成功触发/生成灌溉决策 (结果不再存储于全局变量)")
                    return jsonify({'status': 'success', 'message': '灌溉决策任务已启动/完成'})
                else:
                    logger.error(f"irrigation_service.make_irrigation_decision 未返回预期结果: {result}")
                    return create_error_response('灌溉决策服务内部错误', 500)

            except FileNotFoundError as e: # 特定错误处理
                 logger.error(f"生成灌溉决策失败: 缺少必要文件 - {str(e)}")
                 return create_error_response(f'缺少模型文件: {str(e)}', 500)
            except ValueError as e: # 特定错误处理
                 logger.error(f"生成灌溉决策失败: 数据错误 - {str(e)}")
                 return create_error_response(f'数据错误: {str(e)}', 400)
            except Exception as e:
                logger.error(f"触发灌溉决策 API 时出错: {str(e)}")
                logger.error(traceback.format_exc())
                return create_error_response('生成灌溉决策时发生意外错误', 500)
        
        # 系统健康状态路由
        @api.route('/health')
        @api_error_handler
        def health():
            """健康检查接口，返回系统状态"""
            try:
                data_dir_exists = os.path.exists(os.path.join(project_root, 'data'))
                static_dir_exists = os.path.exists(os.path.join(project_root, 'src/static'))
                
                status = 'ok' if (data_dir_exists and static_dir_exists) else 'error'
                
                if request.headers.get('Accept', '').find('application/json') != -1 or request.args.get('format') == 'json':
                    return jsonify({
                        'status': status,
                        'message': '系统健康检查完成',
                        'checks': {
                            'data_directory': data_dir_exists,
                            'static_directory': static_dir_exists
                        },
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                
                return render_template('health.html',
                                      data_dir=data_dir_exists,
                                      static_dir=static_dir_exists,
                                      templates=True,
                                      model_output=True,
                                      timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            except Exception as e:
                logger.error(f"健康检查失败: {str(e)}")
                return jsonify({
                    'status': 'error',
                    'message': f'健康检查失败: {str(e)}',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }), 500
        
        # 真实数据API接口
        @api.route('/api/soil_data')
        @api.route(f'{config.API_PREFIX}/soil_data')
        @api_error_handler
        def soil_data():
            """土壤数据端点"""
            try:
                request_field_id = request.args.get("field_id", field_id)
                logger.info(f"API请求土壤数据: field_id={request_field_id}")
                
                request_sensor = SoilSensor(device_id, request_field_id)
                sensor_data = request_sensor.get_current_data()
                
                if sensor_data.get('is_real_data', False):
                    max_humidity = sensor_data['max_humidity']
                    min_humidity = sensor_data['min_humidity']
                    real_humidity = sensor_data['real_humidity']
                    
                    logger.info(f"使用irrigation_service计算土壤墒情参数: max_humidity={max_humidity}, min_humidity={min_humidity}, real_humidity={real_humidity}")
                    
                    try:
                        SAT, FC, PWP, diff_max_real_mm, diff_min_real_mm, diff_com_real_mm = irrigation_service.calculate_soil_humidity_differences(
                            max_humidity, real_humidity, min_humidity
                        )
                        
                        logger.info(f"irrigation_service计算结果: SAT={SAT}, FC={FC}, PWP={PWP}")
                        logger.info(f"差异参数: diff_max_real_mm={diff_max_real_mm}, diff_min_real_mm={diff_min_real_mm}, diff_com_real_mm={diff_com_real_mm}")
                        
                        current_humidity_mm = real_humidity * SOIL_DEPTH_CM / 10
                        wilting_point = PWP * SOIL_DEPTH_CM / 10
                        
                        response_data = {
                            'max_humidity': sensor_data['max_humidity'],
                            'min_humidity': sensor_data['min_humidity'],
                            'real_humidity': sensor_data['real_humidity'],
                            'sat': round(SAT * 10 / SOIL_DEPTH_CM, 2),  
                            'fc': round(FC * 10 / SOIL_DEPTH_CM, 2),    
                            'pwp': round(PWP * 10 / SOIL_DEPTH_CM, 2),  
                            'is_real_data': True,
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'unit': '%',
                            'storage_potential': round(diff_max_real_mm, 2),  # 蓄水潜力
                            'effective_storage': round(diff_min_real_mm, 2),  # 有效储水量
                            'available_storage': round(diff_min_real_mm, 2)   # 可用储水量
                        }
                        
                        logger.info(f"返回给前端的墒情数据: sat={response_data['sat']}%, fc={response_data['fc']}%, pwp={response_data['pwp']}%")
                        
                        logger.info(f"成功返回使用irrigation_service计算的土壤墒情数据")
                        return jsonify(response_data)
                    except Exception as e:
                        logger.error(f"使用irrigation_service计算土壤墒情参数时出错: {str(e)}")
                        current_humidity_mm = sensor_data.get('real_humidity', 0) * SOIL_DEPTH_CM / 10
                        wilting_point = sensor_data.get('pwp', 0) * SOIL_DEPTH_CM / 10
                        
                        response_data = {
                            'max_humidity': sensor_data['max_humidity'],
                            'min_humidity': sensor_data['min_humidity'],
                            'real_humidity': sensor_data['real_humidity'],
                            'sat': sensor_data.get('sat', 0),
                            'fc': sensor_data.get('fc', 0),
                            'pwp': sensor_data.get('pwp', 0),
                            'is_real_data': False,
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'unit': '%',
                            'storage_potential': (sensor_data.get('sat', 0) - sensor_data.get('real_humidity', 0)) * SOIL_DEPTH_CM / 10,
                            'effective_storage': max(0, sensor_data.get('real_humidity', 0) - sensor_data.get('fc', 0)) * SOIL_DEPTH_CM / 10,
                            'available_storage': max(0, current_humidity_mm - wilting_point)
                        }
                        
                        logger.warning(f"由于计算错误,返回原始sensor_data基础数据: {str(e)}")
                        logger.warning("数据完整性警告: 返回的土壤墒情参数未经过irrigation_service计算验证")
                        return jsonify(response_data)
                else:
                    return create_error_response('无法获取真实土壤数据', 503)
            except Exception as e:
                logger.error(f"获取土壤数据时出错: {str(e)}")
                return create_error_response('获取土壤数据失败', 500)
        
        # 气象监测接口
        @api.route('/api/weather_data')
        @token_required
        @api_error_handler
        def weather_data():
            """天气数据端点"""
            try:
                days = request.args.get('days', default=7, type=int)  
                data_type = request.args.get('type', 'daily')  
                start_date = request.args.get('start_date')  
                end_date = request.args.get('end_date')  
                
                if days <= 0 or days > MAX_DAYS_RANGE:
                    return jsonify({
                        'status': 'error',
                        'message': f'无效的天数参数: {days},天数应在1-{MAX_DAYS_RANGE}之间',
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }), 400
                
                if start_date and end_date:
                    try:
                        start = datetime.strptime(start_date, '%Y-%m-%d')
                        end = datetime.strptime(end_date, '%Y-%m-%d')
                        if start > end:
                            return jsonify({
                                'status': 'error',
                                'message': '开始日期不能晚于结束日期',
                                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            }), 400
                    except ValueError:
                        return jsonify({
                            'status': 'error',
                            'message': '日期格式无效,请使用YYYY-MM-DD格式',
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }), 400
                else:
                    end = datetime.now()
                    start = end - timedelta(days=days)
                
                weather_file = os.path.join(project_root, 'data/weather/drought_irrigation.wth')
                if not os.path.exists(weather_file):
                    alt_paths = [
                        os.path.join(project_root, 'data/weather/irrigation_weather.csv'),
                        os.path.join(project_root, 'data/weather/weather_history_data.csv'),
                    ]
                    
                    old_paths = [
                        os.path.join(project_root, 'weather_history_data.csv'),
                        os.path.join(project_root, 'irrigation_weather.csv'),
                    ]
                    
                    for alt_path in alt_paths + old_paths:
                        if os.path.exists(alt_path):
                            weather_file = alt_path
                            logger.info(f"使用天气数据文件: {alt_path}")
                            break
                    else:
                        raise FileNotFoundError(f"天气数据文件不存在")
                
                if weather_file.endswith('.wth'):
                    df = pd.read_csv(weather_file, delim_whitespace=True, skiprows=4)
                    if 'DAY' in df.columns and 'MONTH' in df.columns and 'YEAR' in df.columns:
                        df['Date'] = pd.to_datetime(df[['YEAR', 'MONTH', 'DAY']])
                else:
                    df = pd.read_csv(weather_file)
                    date_columns = [col for col in df.columns if 'date' in col.lower() or 'time' in col.lower()]
                    if date_columns:
                        df['Date'] = pd.to_datetime(df[date_columns[0]])
                    elif 'DAY' in df.columns and 'MONTH' in df.columns and 'YEAR' in df.columns:
                        df['Date'] = pd.to_datetime(df[['YEAR', 'MONTH', 'DAY']])
                    else:
                        logger.warning(f"无法在天气数据文件中识别日期列: {list(df.columns)}")
                        return jsonify({
                            'status': 'error',
                            'message': '无法在天气数据文件中识别日期列',
                            'columns': list(df.columns),
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }), 400
                
                if 'Date' in df.columns:
                    df = df[(df['Date'] >= pd.to_datetime(start)) & (df['Date'] <= pd.to_datetime(end))]
                    
                    df['formatted_date'] = df['Date'].dt.strftime('%Y-%m-%d')
                
                if df.empty:
                    return jsonify({
                        'status': 'warning',
                        'message': '在指定日期范围内没有天气数据',
                        'time_range': {
                            'start': start.strftime('%Y-%m-%d'),
                            'end': end.strftime('%Y-%m-%d')
                        },
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }), 404
                
                weather_data = {
                    'dates': df['formatted_date'].tolist() if 'formatted_date' in df.columns else [],
                    'time_range': {
                        'start': start.strftime('%Y-%m-%d'),
                        'end': end.strftime('%Y-%m-%d')
                    }
                }
                
                weather_elements = {
                    'TMAX': 'max_temperature',
                    'TMIN': 'min_temperature',
                    'RAIN': 'precipitation',
                    'SRAD': 'solar_radiation',
                    'WIND': 'wind_speed',
                    'RHUM': 'relative_humidity',
                    'ET0': 'reference_evapotranspiration'
                }
                
                for orig, new_name in weather_elements.items():
                    if orig in df.columns:
                        weather_data[new_name] = df[orig].tolist()
                
                return jsonify({
                    'status': 'ok',
                    'data': weather_data,
                    'data_type': data_type,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
            except Exception as e:
                logger.error(f"获取天气数据时出错: {str(e)}")
                return jsonify({
                    'status': 'error',
                    'message': f'获取天气数据失败: {str(e)}',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }), 500
        
        # 灌溉推荐API接口
        @api.route('/api/irrigation_recommendation')
        @api_error_handler
        def irrigation_recommendation():
            """获取灌溉推荐数据"""
            try:
                # 尝试获取真实灌溉决策数据
                soil_sensor = SoilSensor(device_id, field_id)
                logger.info(f"API请求灌溉决策: field_id={field_id}")
                sensor_data = soil_sensor.get_current_data()
                
                if not sensor_data.get('is_real_data', False):
                    logger.warning("获取灌溉推荐数据: 无法获取真实土壤数据")
                    return jsonify({
                        'status': 'error', 
                        'message': '无法获取真实土壤数据进行决策',
                        'data': {
                            'irrigation_amount': 0,
                            'message': '无法获取真实土壤数据，无法提供灌溉决策',
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                    }), 503
                
                try:
                    # 生成真实的灌溉决策
                    result = irrigation_service.make_irrigation_decision(
                        field_id,
                        sensor_data['max_humidity'],
                        sensor_data['min_humidity'],
                        sensor_data['real_humidity']
                    )
                    
                    if result and isinstance(result, dict):
                        # 提取灌溉决策结果
                        recommendation = {
                            'irrigation_amount': result.get('irrigation_value', 0),
                            'message': result.get('message', '无灌溉决策信息'),
                            'calculated_deficit': result.get('soil_data', {}).get('available_storage', 0),
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'soil_moisture_status': 'sufficient' if result.get('irrigation_value', 0) == 0 else 'insufficient',
                            'next_check_time': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
                        }
                        
                        logger.info(f"返回真实灌溉推荐数据: 灌溉量={recommendation['irrigation_amount']}mm")
                        return jsonify({'status': 'success', 'data': recommendation})
                    else:
                        logger.warning("灌溉服务返回了无效的结果")
                except Exception as e:
                    logger.error(f"生成灌溉决策时出错: {str(e)}")
                    logger.error(traceback.format_exc())
                
                # 如果无法获取真实数据或生成失败，返回默认数据
                logger.warning("无法获取真实灌溉决策，返回模拟数据")
                mock_recommendation = {
                    'irrigation_amount': 0,  # 单位：mm
                    'message': '当前土壤水分充足，无需灌溉',
                    'calculated_deficit': 0,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'soil_moisture_status': 'sufficient',
                    'next_check_time': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
                }
                
                return jsonify({'status': 'success', 'data': mock_recommendation})
            except Exception as e:
                logger.error(f"获取灌溉推荐数据时出错: {str(e)}")
                return create_error_response('获取灌溉推荐数据失败', 500)
        
        # ETref和ETc历史数据API接口
        @api.route('/api/et_history')
        @api_error_handler
        def et_history():
            """获取ETref和ETc历史数据"""
            try:
                days = request.args.get('days', default=DEFAULT_DAYS, type=int)
                if days <= 0 or days > MAX_DAYS_RANGE:
                    return create_error_response(
                        f'无效的天数参数: {days},天数应在1-{MAX_DAYS_RANGE}之间',
                        400,
                        {'valid_range': f'1-{MAX_DAYS_RANGE}'}
                    )
                
                # 读取wheat2024.out文件
                wheat_output_file = os.path.join(project_root, 'data/model_output/wheat2024.out')
                
                if not os.path.exists(wheat_output_file):
                    logger.error(f"wheat2024.out文件不存在: {wheat_output_file}")
                    return create_error_response('ETref和ETc数据文件不存在', 404)
                with open(wheat_output_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                data_start_line = None
                for i, line in enumerate(lines):
                    if 'Year-DOY' in line and 'ETref' in line and 'ETc' in line:
                        data_start_line = i + 1  # 数据从下一行开始
                        break
                
                if data_start_line is None:
                    logger.error("无法在wheat2024.out文件中找到数据开始行")
                    return create_error_response('无法解析ETref和ETc数据文件格式', 500)
                dates = []
                etref_values = []
                etc_values = []
                data_lines = lines[data_start_line:]
                
                for line_number, line in enumerate(data_lines, start=data_start_line + 1):
                    if line.strip():
                        parts = line.strip().split()
                        if len(parts) >= ET_DATA_MIN_COLUMNS:  # 确保有足够的列（ETc在第20列）
                            try:
                                date_str = parts[4]
                                date_obj = datetime.strptime(date_str, '%m/%d/%y')
                                etref = float(parts[5])
                                etc = float(parts[19])  
                                
                                dates.append(date_obj.strftime('%Y-%m-%d'))
                                etref_values.append(etref)
                                etc_values.append(etc)
                                
                            except (ValueError, IndexError) as e:
                                logger.warning(f"跳过无效数据行 (行号: {line_number}): {line.strip()[:50]}... 错误: {e}")
                                continue
                
                if not dates:
                    logger.warning("未能从wheat2024.out文件中解析出有效数据")
                    return create_error_response('未找到有效的ETref和ETc数据', 404)
                
                result = {
                    'dates': dates,
                    'etref': etref_values,
                    'etc': etc_values,
                    'count': len(dates)
                }
                
                logger.info(f"成功返回ETref和ETc历史数据: {len(dates)}天")
                return jsonify({'status': 'success', 'data': result})
                
            except Exception as e:
                logger.error(f"获取ETref和ETc历史数据时出错: {str(e)}")
                logger.error(traceback.format_exc())
                return create_error_response('获取ETref和ETc历史数据失败', 500)
        
        # 作物生长阶段API接口
        @api.route('/api/growth_stage')
        @api_error_handler
        def growth_stage():
            """获取作物生长阶段数据"""
            try:
                mock_growth_data = {
                    'stage': '营养生长期',
                    'dap': 45,  
                    'root_depth': 0.25, 
                    'canopy_cover': 0.68,  
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'plant_height': 0.6, 
                    'current_stage_days': 15,
                    'next_stage': '抽穗期',
                    'days_to_next_stage': 12
                }
                
                logger.info("返回作物生长阶段数据")
                return jsonify({'status': 'success', 'data': mock_growth_data})
            except Exception as e:
                logger.error(f"获取作物生长阶段数据时出错: {str(e)}")
                return create_error_response('获取作物生长阶段数据失败', 500)
        
        # API文档接口
        @api.route('/api/docs')
        @api.route('/api_docs')  # 添加新路由
        @api_error_handler
        def api_docs():
            """API文档页面"""
            api_routes = []
            for rule in current_app.url_map.iter_rules():
                if "/static/" not in rule.rule and not rule.rule.endswith(".map"):
                    methods = ','.join(sorted(rule.methods - set(['OPTIONS', 'HEAD'])))
                    api_routes.append({
                        'endpoint': rule.endpoint,
                        'methods': methods,
                        'path': rule.rule,
                        'description': globals().get(rule.endpoint).__doc__ if rule.endpoint in globals() else ""
                    })
            
            api_routes.sort(key=lambda r: r['path'])
            
            return render_template('api_docs.html', api_routes=api_routes)
        
        return api
    
    except Exception as e:
        logger.error(f"创建API路由失败: {e}")
        logger.error(traceback.format_exc())
        api = Blueprint('api', __name__, url_prefix='')
        return api