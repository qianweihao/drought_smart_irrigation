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
        
        # 辅助函数：根据 field_id 获取对应的 device_id
        def get_device_id_by_field(requested_field_id):
            """根据田块ID获取对应的设备ID
            
            Args:
                requested_field_id: 请求的田块ID
                
            Returns:
                tuple: (device_id, field_name) - 如果找不到或device_id为None，返回默认值
            """
            if not requested_field_id:
                logger.warning("请求的田块ID为空，使用默认值")
                return device_id, '默认田块'
            
            fields_config = getattr(config, 'FIELDS_CONFIG', [])
            if not fields_config:
                logger.warning("FIELDS_CONFIG 为空，使用默认值")
                return device_id, '默认田块'
            
            for field in fields_config:
                field_id = field.get('field_id')
                if field_id == requested_field_id:
                    found_device_id = field.get('device_id')
                    found_field_name = field.get('field_name', '未知')
                    
                    # 确保 device_id 不为 None
                    if found_device_id is None:
                        logger.warning(f"田块 {requested_field_id} 的 device_id 为 None，使用默认值")
                        return device_id, found_field_name
                    
                    return found_device_id, found_field_name
            
            # 如果没找到，返回默认值
            logger.warning(f"未找到田块 {requested_field_id} 的配置，使用默认值")
            return device_id, '默认田块'  
        
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
                # 支持通过请求参数指定田块
                request_field_id = request.args.get("field_id", field_id)
                request_device_id, field_name = get_device_id_by_field(request_field_id)
                logger.info(f"API请求土壤湿度历史数据: field_id={request_field_id}, device_id={request_device_id}, field_name={field_name}")
                
                soil_sensor = SoilSensor(request_device_id, request_field_id)
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
                # 支持通过请求参数指定田块
                request_field_id = request.args.get("field_id", field_id)
                request_device_id, field_name = get_device_id_by_field(request_field_id)
                
                logger.info(f"API 触发灌溉决策: field_id={request_field_id}, device_id={request_device_id}, field_name={field_name}")
                
                soil_sensor = SoilSensor(request_device_id, request_field_id)
                sensor_data = soil_sensor.get_current_data()

                # 检查是否有可用的数据
                real_humidity = sensor_data.get('real_humidity', 0)
                # 确保 real_humidity 不为 None
                if real_humidity is None:
                    real_humidity = 0
                real_humidity = float(real_humidity) if real_humidity else 0.0
                is_real_data = sensor_data.get('is_real_data', False)
                
                # 检查是否有可用的数据（至少SAT、FC、PWP中有一个不是默认值）
                has_valid_data = (sensor_data.get('sat', 0) > 0 or 
                                 sensor_data.get('fc', 0) > 0 or 
                                 sensor_data.get('pwp', 0) > 0 or
                                 real_humidity > 0)
                
                if not has_valid_data:
                    logger.warning(f"[田块 {request_field_id}] 生成决策失败: 所有土壤参数都不可用")
                    return create_error_response('无法获取有效的土壤数据进行决策', 400)
                
                # 验证 real_humidity 参数
                if real_humidity is None or not isinstance(real_humidity, (int, float)):
                    logger.error(f"[田块 {request_field_id}] 无效的土壤湿度数据: {real_humidity}")
                    return create_error_response(f'无效的土壤湿度数据: {real_humidity}', 400)
                
                if not is_real_data:
                    logger.warning(f"[田块 {request_field_id}] 部分数据可能不完整 (is_real_data=False)，但将尝试生成决策")
                
                # 生成灌溉决策（SAT/FC/PWP 自动从传感器获取）
                result = irrigation_service.make_irrigation_decision(
                    request_field_id,
                    request_device_id,
                    real_humidity
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
        
        # 田块列表API接口
        @api.route('/api/fields')
        @api.route(f'{config.API_PREFIX}/fields')
        @api_error_handler
        def get_fields():
            """获取所有可用田块列表"""
            try:
                fields_config = getattr(config, 'FIELDS_CONFIG', [])
                if not fields_config:
                    # 如果没有配置多田块，返回默认田块
                    default_field = {
                        'field_id': field_id,
                        'device_id': device_id,
                        'field_name': '默认田块',
                        'crop_type': '小麦',
                        'area': 0,
                        'description': '默认田块'
                    }
                    fields_config = [default_field]
                
                return jsonify({
                    'status': 'success',
                    'data': fields_config,
                    'count': len(fields_config),
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }), 200
            except Exception as e:
                logger.error(f"获取田块列表失败: {str(e)}")
                return create_error_response(f'获取田块列表失败: {str(e)}', 500)
        
        # 真实数据API接口
        @api.route('/api/soil_data')
        @api.route(f'{config.API_PREFIX}/soil_data')
        @api_error_handler
        def soil_data():
            """土壤数据端点"""
            try:
                request_field_id = request.args.get("field_id", field_id)
                request_device_id, field_name = get_device_id_by_field(request_field_id)
                logger.info(f"API请求土壤数据: field_id={request_field_id}, device_id={request_device_id}, field_name={field_name}")
                
                request_sensor = SoilSensor(request_device_id, request_field_id)
                sensor_data = request_sensor.get_current_data()
                
                # 即使is_real_data为False，如果SAT、FC、PWP等参数可用，也应该返回数据
                max_humidity = sensor_data.get('max_humidity', 0) or 0
                min_humidity = sensor_data.get('min_humidity', 0) or 0
                real_humidity = sensor_data.get('real_humidity', 0)
                # 确保 real_humidity 不为 None
                if real_humidity is None:
                    real_humidity = 0
                real_humidity = float(real_humidity) if real_humidity else 0.0
                is_real_data = sensor_data.get('is_real_data', False)
                
                # 检查是否有可用的数据（至少SAT、FC、PWP中有一个不是默认值）
                has_valid_data = (sensor_data.get('sat', 0) > 0 or 
                                 sensor_data.get('fc', 0) > 0 or 
                                 sensor_data.get('pwp', 0) > 0 or
                                 max_humidity > 0 or min_humidity > 0)
                
                if not has_valid_data:
                    logger.warning("所有土壤参数都不可用")
                    return create_error_response('无法获取有效的土壤数据', 503)
                
                logger.info(f"[田块 {request_field_id}] 使用irrigation_service计算土壤墒情参数: real_humidity={real_humidity}%, is_real_data={is_real_data}")
                
                try:
                    # 直接从传感器数据获取SAT/FC/PWP的原始百分比值（已考虑手动配置）
                    sat_percent = sensor_data.get('sat') or 0
                    fc_percent = sensor_data.get('fc') or 0
                    pwp_percent = sensor_data.get('pwp') or 0
                    
                    # 确保是数值类型
                    try:
                        sat_percent = float(sat_percent) if sat_percent is not None else 0
                        fc_percent = float(fc_percent) if fc_percent is not None else 0
                        pwp_percent = float(pwp_percent) if pwp_percent is not None else 0
                    except (ValueError, TypeError):
                        sat_percent = fc_percent = pwp_percent = 0
                    
                    logger.info(f"[田块 {request_field_id}] 传感器原始参数: SAT={sat_percent}%, FC={fc_percent}%, PWP={pwp_percent}%")
                    
                    # 使用irrigation_service计算差异参数（用于决策）
                    SAT, FC, PWP, diff_max_real_mm, diff_min_real_mm, diff_com_real_mm = irrigation_service.calculate_soil_humidity_differences(
                        request_field_id, request_device_id, real_humidity
                    )
                    
                    logger.info(f"irrigation_service计算结果: SAT={SAT}mm, FC={FC}mm, PWP={PWP}mm")
                    logger.info(f"差异参数: diff_max_real_mm={diff_max_real_mm}, diff_min_real_mm={diff_min_real_mm}, diff_com_real_mm={diff_com_real_mm}")
                    
                    current_humidity_mm = real_humidity * SOIL_DEPTH_CM / 10
                    wilting_point = pwp_percent * SOIL_DEPTH_CM / 10
                    
                    response_data = {
                        # 核心土壤参数（直接从传感器数据获取，已考虑手动配置）
                        'real_humidity': round(real_humidity, 2),  # 当前实际湿度
                        'sat': round(sat_percent, 2),  # 饱和含水量（手动配置或统计方法）
                        'fc': round(fc_percent, 2),   # 田间持水量（手动配置或统计方法）
                        'pwp': round(pwp_percent, 2),  # 萎蔫点（手动配置或统计方法）
                        # 兼容性字段（已废弃，保留仅用于向后兼容）
                        'max_humidity': sensor_data.get('max_humidity', 0),  # 已废弃：请使用 sat
                        'min_humidity': sensor_data.get('min_humidity', 0),  # 已废弃：请使用 pwp
                        # 其他信息
                        'is_real_data': is_real_data,
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
                        'max_humidity': sensor_data.get('max_humidity', 0),
                        'min_humidity': sensor_data.get('min_humidity', 0),
                        'real_humidity': sensor_data.get('real_humidity', 0),
                        'sat': sensor_data.get('sat', 0),
                        'fc': sensor_data.get('fc', 0),
                        'pwp': sensor_data.get('pwp', 0),
                        'is_real_data': is_real_data,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'unit': '%',
                        'storage_potential': (sensor_data.get('sat', 0) - sensor_data.get('real_humidity', 0)) * SOIL_DEPTH_CM / 10,
                        'effective_storage': max(0, sensor_data.get('real_humidity', 0) - sensor_data.get('fc', 0)) * SOIL_DEPTH_CM / 10,
                        'available_storage': max(0, current_humidity_mm - wilting_point)
                    }
                    
                    logger.warning(f"由于计算错误,返回原始sensor_data基础数据: {str(e)}")
                    logger.warning("数据完整性警告: 返回的土壤墒情参数未经过irrigation_service计算验证")
                    return jsonify(response_data)
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
        
        # ET历史数据API接口
        @api.route('/api/et_history')
        @api_error_handler
        def et_history():
            """获取ETref和ETc历史数据（整个生育期）"""
            try:
                # 支持通过请求参数指定田块（虽然ET数据可能对所有田块相同，因为使用同一个模型文件）
                request_field_id = request.args.get("field_id", field_id)
                logger.info(f"API请求ET历史数据: field_id={request_field_id}")
                
                # 获取模型输出文件路径
                model_output_file = config.FILE_PATHS.get('model_output', os.path.join('data', 'model_output', 'wheat2024.out'))
                model_output_path = os.path.join(project_root, model_output_file)
                
                if not os.path.exists(model_output_path):
                    logger.error(f"模型输出文件不存在: {model_output_path}")
                    return create_error_response('模型输出文件不存在', 404)
                
                # 读取模型输出文件
                try:
                    df = pd.read_csv(model_output_path, delim_whitespace=True, skiprows=10)
                except Exception as e:
                    logger.error(f"读取模型输出文件失败: {str(e)}")
                    return create_error_response(f'读取模型输出文件失败: {str(e)}', 500)
                
                if df.empty:
                    return create_error_response('模型输出文件为空', 404)
                
                # 验证必要的列
                required_columns = ['Date', 'ETc']
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    return create_error_response(f'模型输出文件缺少必要列: {missing_columns}', 400)
                
                # 解析日期
                df['Date'] = pd.to_datetime(df['Date'], format='%m/%d/%y', errors='coerce')
                df = df.dropna(subset=['Date'])
                
                if df.empty:
                    return create_error_response('模型输出文件中没有有效的日期数据', 404)
                
                # 获取ETref列（如果存在），否则尝试从ET0列获取
                if 'ETref' in df.columns:
                    etref_col = 'ETref'
                elif 'ET0' in df.columns:
                    etref_col = 'ET0'
                else:
                    # 如果没有ETref列，尝试从天气数据计算或使用默认值
                    logger.warning("模型输出文件中没有ETref或ET0列，将使用ETc作为参考")
                    etref_col = None
                
                # 获取整个生育期的数据（不限制天数）
                # 筛选有效数据（去除NaN）
                filtered_df = df.copy()
                filtered_df = filtered_df.sort_values('Date')
                
                if filtered_df.empty:
                    return jsonify({
                        'status': 'warning',
                        'message': '没有ET数据',
                        'data': {
                            'dates': [],
                            'etref': [],
                            'etc': []
                        },
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }), 200
                
                # 提取数据并处理NaN值
                dates = filtered_df['Date'].dt.strftime('%Y-%m-%d').tolist()
                
                # 处理ETc数据：将NaN替换为0
                etc_data = filtered_df['ETc'].fillna(0).replace([np.inf, -np.inf], 0).tolist()
                
                # ETref数据
                if etref_col:
                    etref_data = filtered_df[etref_col].fillna(0).replace([np.inf, -np.inf], 0).tolist()
                else:
                    # 如果没有ETref，使用ETc的1.2倍作为估算（这是一个粗略的估算）
                    etref_data = (filtered_df['ETc'].fillna(0) * 1.2).replace([np.inf, -np.inf], 0).tolist()
                    logger.info("使用ETc的1.2倍作为ETref的估算值")
                
                # 确保所有数据都是有效的数值（不是NaN、Inf等）
                etc_data = [float(x) if pd.notna(x) and np.isfinite(x) else 0.0 for x in etc_data]
                etref_data = [float(x) if pd.notna(x) and np.isfinite(x) else 0.0 for x in etref_data]
                
                logger.info(f"成功返回ET历史数据: {len(dates)}天, field_id={request_field_id}")
                
                return jsonify({
                    'status': 'success',
                    'data': {
                        'dates': dates,
                        'etref': etref_data,
                        'etc': etc_data
                    },
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }), 200
                
            except Exception as e:
                logger.error(f"获取ET历史数据时出错: {str(e)}")
                logger.error(traceback.format_exc())
                return create_error_response(f'获取ET历史数据失败: {str(e)}', 500)
        
        # 作物生长阶段API接口
        @api.route('/api/growth_stage')
        @api_error_handler
        def growth_stage():
            """获取作物生长阶段数据"""
            try:
                # 支持通过请求参数指定田块（虽然生长数据可能对所有田块相同，因为使用同一个模型文件）
                request_field_id = request.args.get("field_id", field_id)
                logger.info(f"API请求作物生长阶段数据: field_id={request_field_id}")
                
                # 获取模型输出文件路径
                model_output_file = config.FILE_PATHS.get('model_output', os.path.join('data', 'model_output', 'wheat2024.out'))
                model_output_path = os.path.join(project_root, model_output_file)
                
                # 获取生育阶段文件路径
                growth_stages_file = config.FILE_PATHS.get('growth_stages', os.path.join('data', 'model_output', 'growth_stages.csv'))
                growth_stages_path = os.path.join(project_root, growth_stages_file)
                
                # 获取当前生育阶段
                current_stage = None
                current_stage_name = '未知'
                try:
                    if os.path.exists(growth_stages_path):
                        growth_stages_df = pd.read_csv(growth_stages_path)
                        if not growth_stages_df.empty and '开始日期' in growth_stages_df.columns:
                            growth_stages_df['开始日期'] = pd.to_datetime(growth_stages_df['开始日期'], errors='coerce')
                            growth_stages_df['结束日期'] = pd.to_datetime(growth_stages_df['结束日期'], errors='coerce')
                            growth_stages_df = growth_stages_df.dropna(subset=['开始日期', '结束日期'])
                            
                            now = datetime.now().date()
                            for _, stage in growth_stages_df.iterrows():
                                start_date = stage['开始日期'].date()
                                end_date = stage['结束日期'].date()
                                if start_date <= now <= end_date:
                                    current_stage_name = stage.get('阶段', '未知')
                                    current_stage = stage.to_dict()
                                    break
                except Exception as e:
                    logger.warning(f"读取生育阶段文件失败: {str(e)}")
                
                # 从模型输出文件获取根系深度和当前数据
                root_depth = None
                dap = None
                canopy_cover = None
                
                try:
                    if os.path.exists(model_output_path):
                        df = pd.read_csv(model_output_path, delim_whitespace=True, skiprows=10)
                        if not df.empty and 'Date' in df.columns:
                            df['Date'] = pd.to_datetime(df['Date'], format='%m/%d/%y', errors='coerce')
                            df = df.dropna(subset=['Date'])
                            
                            now = pd.to_datetime(datetime.now().date())
                            today_data = df[df['Date'] == now]
                            
                            if today_data.empty:
                                # 使用最接近的日期
                                df['date_diff'] = abs((df['Date'] - now).dt.days)
                                closest_row = df.loc[df['date_diff'].idxmin()]
                            else:
                                closest_row = today_data.iloc[0]
                            
                            # 获取根系深度
                            if 'Zr' in closest_row:
                                root_depth = float(closest_row['Zr']) if pd.notna(closest_row['Zr']) else None
                            
                            # 尝试获取DAP（如果有的话）
                            if 'DAP' in closest_row:
                                dap = int(closest_row['DAP']) if pd.notna(closest_row['DAP']) else None
                except Exception as e:
                    logger.warning(f"读取模型输出文件失败: {str(e)}")
                
                # 尝试从AquaCrop输出获取冠层覆盖度
                try:
                    aquacrop_output_dir = os.path.join(project_root, config.AQUACROP_CONFIG.get('OUTPUT_DIR', 'data/model_output'))
                    daily_crop_growth_file = os.path.join(aquacrop_output_dir, 'daily_crop_growth.csv')
                    
                    if os.path.exists(daily_crop_growth_file):
                        crop_df = pd.read_csv(daily_crop_growth_file)
                        if not crop_df.empty and 'Date' in crop_df.columns:
                            crop_df['Date'] = pd.to_datetime(crop_df['Date'], errors='coerce')
                            crop_df = crop_df.dropna(subset=['Date'])
                            
                            now = pd.to_datetime(datetime.now().date())
                            today_crop_data = crop_df[crop_df['Date'] == now]
                            
                            if today_crop_data.empty:
                                crop_df['date_diff'] = abs((crop_df['Date'] - now).dt.days)
                                closest_crop_row = crop_df.loc[crop_df['date_diff'].idxmin()]
                            else:
                                closest_crop_row = today_crop_data.iloc[0]
                            
                            # 获取冠层覆盖度（可能是 CC 或 _cc）
                            for col in ['CC', '_cc', 'canopy_cover']:
                                if col in closest_crop_row:
                                    cc_value = closest_crop_row[col]
                                    if pd.notna(cc_value):
                                        canopy_cover = float(cc_value)
                                        break
                            
                            # 获取DAP（可能是 DAP 或 _dap）
                            if dap is None:
                                for col in ['DAP', '_dap', 'dap']:
                                    if col in closest_crop_row:
                                        dap_value = closest_crop_row[col]
                                        if pd.notna(dap_value):
                                            dap = int(dap_value)
                                            break
                except Exception as e:
                    logger.warning(f"读取AquaCrop输出文件失败: {str(e)}")
                
                # 构建响应数据
                growth_data = {
                    'stage': current_stage_name,
                    'dap': dap,
                    'root_depth': root_depth,
                    'canopy_cover': canopy_cover,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                logger.info(f"返回作物生长阶段数据: stage={current_stage_name}, root_depth={root_depth}m, dap={dap}, canopy_cover={canopy_cover}")
                
                return jsonify({
                    'status': 'success',
                    'data': growth_data
                }), 200
                
            except Exception as e:
                logger.error(f"获取作物生长阶段数据时出错: {str(e)}")
                logger.error(traceback.format_exc())
                return create_error_response(f'获取作物生长阶段数据失败: {str(e)}', 500)
        
        # 灌溉推荐API接口
        @api.route('/api/irrigation_recommendation')
        @api_error_handler
        def irrigation_recommendation():
            """获取灌溉推荐数据"""
            try:
                # 从请求参数获取田块ID
                request_field_id = request.args.get("field_id", field_id)
                request_device_id, field_name = get_device_id_by_field(request_field_id)
                logger.info(f"API请求灌溉决策: field_id={request_field_id}, device_id={request_device_id}, field_name={field_name}")
                
                # 尝试获取真实灌溉决策数据
                soil_sensor = SoilSensor(request_device_id, request_field_id)
                sensor_data = soil_sensor.get_current_data()
                
                # 检查是否有可用的数据
                max_humidity = sensor_data.get('max_humidity', 0) or 0
                min_humidity = sensor_data.get('min_humidity', 0) or 0
                real_humidity = sensor_data.get('real_humidity', 0)
                # 确保 real_humidity 不为 None
                if real_humidity is None:
                    real_humidity = 0
                real_humidity = float(real_humidity) if real_humidity else 0.0
                is_real_data = sensor_data.get('is_real_data', False)
                
                # 检查是否有可用的数据（至少SAT、FC、PWP中有一个不是默认值）
                has_valid_data = (sensor_data.get('sat', 0) > 0 or 
                                 sensor_data.get('fc', 0) > 0 or 
                                 sensor_data.get('pwp', 0) > 0 or
                                 max_humidity > 0 or min_humidity > 0)
                
                if not has_valid_data:
                    logger.warning("获取灌溉推荐数据: 所有土壤参数都不可用")
                    return jsonify({
                        'status': 'error', 
                        'message': '无法获取有效的土壤数据进行决策',
                        'data': {
                            'irrigation_amount': 0,
                            'message': '无法获取有效的土壤数据，无法提供灌溉决策',
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                    }), 503
                
                # 验证 real_humidity 参数
                if real_humidity is None or not isinstance(real_humidity, (int, float)):
                    logger.error(f"[田块 {request_field_id}] 无效的土壤湿度数据: {real_humidity}")
                    return jsonify({
                        'status': 'error',
                        'message': f'无效的土壤湿度数据: {real_humidity}',
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }), 400
                
                # 即使is_real_data为False，只要有可用数据就尝试生成决策
                if not is_real_data:
                    logger.warning(f"获取灌溉推荐数据: 部分数据可能不完整 (is_real_data=False)，但将尝试生成决策")
                
                try:
                    # 生成灌溉决策（SAT/FC/PWP 自动从传感器获取）
                    result = irrigation_service.make_irrigation_decision(
                        request_field_id,
                        request_device_id,
                        real_humidity
                    )
                    
                    if result and isinstance(result, dict):
                        # 提取灌溉决策结果
                        recommendation = {
                            'irrigation_amount': result.get('irrigation_value', 0),
                            'message': result.get('message', '无灌溉决策信息'),
                            'calculated_deficit': result.get('soil_data', {}).get('available_storage', 0),
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'soil_moisture_status': 'sufficient' if result.get('irrigation_value', 0) == 0 else 'insufficient',
                            'next_check_time': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S'),
                            'data_quality': 'real' if is_real_data else 'partial'
                        }
                        
                        logger.info(f"返回灌溉推荐数据: 灌溉量={recommendation['irrigation_amount']}mm, 数据质量={recommendation['data_quality']}")
                        return jsonify({'status': 'success', 'data': recommendation})
                    else:
                        logger.warning("灌溉服务返回了无效的结果")
                except Exception as e:
                    logger.error(f"生成灌溉决策时出错: {str(e)}")
                    logger.error(traceback.format_exc())
                
                # 如果无法生成决策，返回默认数据
                logger.warning("无法生成灌溉决策，返回默认数据")
                mock_recommendation = {
                    'irrigation_amount': 0,  # 单位：mm
                    'message': '当前土壤水分充足，无需灌溉',
                    'calculated_deficit': 0,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'soil_moisture_status': 'sufficient',
                    'next_check_time': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S'),
                    'data_quality': 'default'
                }
                
                return jsonify({'status': 'success', 'data': mock_recommendation})
            except Exception as e:
                logger.error(f"获取灌溉推荐数据时出错: {str(e)}")
                return create_error_response('获取灌溉推荐数据失败', 500)
        
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