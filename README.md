# 智能土壤灌溉系统

基于FAO-56和AquaCrop模型的智能土壤灌溉决策系统，集成实时土壤监测、天气预报和作物模拟，为农作物提供精准灌溉策略。

## 功能特点

### 核心功能
- **双模型驱动**: 集成FAO-56蒸散发模型和AquaCrop作物生长模型
- **实时监测**: 土壤湿度传感器数据实时采集与分析
- **智能决策**: 基于土壤水分、作物需水量和天气预报的智能灌溉决策
- **精准控制**: 多级灌溉量控制，支持5-50mm精准灌溉
- **生育期管理**: 根据作物生育阶段动态调整灌溉阈值

### 技术特色
- **Web界面**: 提供直观的数据可视化和系统监控界面
- **API接口**: RESTful API支持第三方系统集成
- **告警系统**: 邮件通知和多级告警机制
- **数据存储**: 完整的历史数据记录和分析
- **安全认证**: JWT令牌认证和权限管理

## 系统要求

- **Python**: 3.8+ (推荐3.11)
- **操作系统**: Windows/Linux/macOS
- **内存**: 最小2GB，推荐4GB+
- **存储**: 最小1GB可用空间

## 项目结构

```
drought_smart_irrigation/
├── src/                          # 源代码目录
│   ├── api/                     # API接口层
│   │   └── routes.py           # 路由定义和接口实现
│   ├── models/                 # 模型层
│   │   ├── fao_model.py       # FAO-56蒸散发模型
│   │   ├── fao_model_autoirr.py # 自动灌溉FAO模型
│   │   ├── soil.py            # 土壤模型
│   │   ├── weather.py         # 天气模型
│   │   └── weather_api.py     # 天气API接口
│   ├── aquacrop/              # AquaCrop模型
│   │   ├── aquacrop_modeling.py # AquaCrop作物模拟
│   │   └── data/              # AquaCrop数据文件
│   ├── services/              # 业务逻辑层
│   │   └── irrigation_service.py # 灌溉决策服务
│   ├── devices/               # 设备接口层
│   │   └── soil_sensor.py     # 土壤传感器接口
│   ├── utils/                 # 工具函数
│   │   ├── auth.py           # 认证工具
│   │   ├── validators.py     # 数据验证
│   │   ├── logger.py         # 日志工具
│   │   └── email_sender.py   # 邮件发送
│   ├── config/               # 配置模块
│   │   └── config.py        # 配置管理
│   ├── static/              # 静态资源
│   │   ├── css/            # 样式文件
│   │   ├── js/             # JavaScript文件
│   │   └── images/         # 图片资源
│   ├── templates/           # HTML模板
│   │   ├── index.html      # 主页
│   │   ├── dashboard.html  # 仪表板
│   │   ├── soil_data.html  # 土壤数据页面
│   │   └── api_docs.html   # API文档
│   └── app.py              # Flask应用入口
├── data/                    # 数据目录
│   ├── weather/            # 天气数据
│   │   ├── irrigation_weather.csv
│   │   ├── drought_irrigation.wth
│   │   └── weather_history_data.csv
│   ├── soil/               # 土壤数据
│   │   ├── drought_irrigation.sol
│   │   └── irrigation_soilprofile_sim.csv
│   ├── model_output/       # 模型输出
│   │   ├── daily_crop_growth.csv
│   │   ├── daily_water_storage.csv
│   │   └── growth_stages.csv
│   └── autoirr/           # 自动灌溉数据
├── logs/                   # 日志目录
├── config.py              # 主配置文件
├── requirements.txt       # Python依赖
├── run.py                # 应用启动脚本
├── run_model.py          # 模型运行脚本
├── .env.example          # 环境变量示例
└── README.md            # 项目说明
```

## 核心依赖

### 主要框架
- **Flask 2.0.3**: Web应用框架
- **pandas 2.2.2**: 数据处理和分析
- **numpy 1.22.4**: 数值计算
- **matplotlib 3.8.0**: 数据可视化

### 模型库
- **pyfao56 1.4.0**: FAO-56蒸散发模型
- **aquacrop 3.0.7**: AquaCrop作物生长模型
- **scipy 1.13.0**: 科学计算
- **netCDF4 1.7.2**: 气象数据处理

### 工具库
- **requests 2.31.0**: HTTP请求
- **python-dotenv 1.0.1**: 环境变量管理
- **PyJWT 2.10.1**: JWT认证
- **loguru 0.7.3**: 日志管理
- **APScheduler 3.10.4**: 任务调度

完整依赖列表请参考 <mcfile name="requirements.txt" path="f:/drought_smart_irrigation/requirements.txt"></mcfile>

## 安装步骤

### 1. 克隆项目
```bash
git clone [项目地址]
cd drought_smart_irrigation
```

### 2. 创建虚拟环境
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python -m venv venv
source venv/bin/activate
```

### 3. 安装依赖
```bash
pip install -r requirements.txt
```

### 4. 配置环境变量
```bash
# Windows PowerShell
Copy-Item .env.example .env

# Linux/macOS
cp .env.example .env
```

编辑 `.env` 文件，配置必要的参数（详见配置说明）。

## 配置说明

项目使用 `.env` 文件进行环境配置，主要配置项包括：

### 基础配置
```env
FLASK_ENV=development              # 运行环境
SECRET_KEY=your-secret-key-here    # Flask密钥
JWT_SECRET_KEY=your-jwt-secret     # JWT密钥
```

### 设备配置
```env
DEFAULT_FIELD_ID=1810565648737284096    # 默认地块ID
DEFAULT_DEVICE_ID=16031600028481        # 默认设备ID
SOIL_API_URL=https://iland.zoomlion.com/open-sharing-platform/zlapi/
SOIL_API_KEY=your-api-key-here          # 土壤API密钥
```

### 作物参数
```env
# 作物系数
KCBINI=0.15        # 初期作物系数
KCBMID=1.10        # 中期作物系数  
KCBEND=0.20        # 末期作物系数

# 生育期长度（天）
LINI=20            # 初期阶段
LDEV=50            # 发育阶段
LMID=70            # 中期阶段
LEND=30            # 末期阶段

HMAX=1             # 最大作物高度（米）
```

### 土壤参数
```env
THETA_FC=0.327     # 田间持水量
THETA_WP=0.10      # 萎蔫点含水量
THETA_0=0.327      # 初始土壤含水量
ZR_INI=0.20        # 初始根系深度（米）
ZR_MAX=1.7         # 最大根系深度（米）
P_BASE=0.55        # 基础土壤水分消耗系数
ZE=0.10            # 土壤蒸发层深度（米）
REW=9              # 易蒸发水量（毫米）
```

### 灌溉决策参数
```env
SOIL_DEPTH_CM=30              # 土壤深度（厘米）
MAX_FORECAST_DAYS=15          # 最大预报天数
IRRIGATION_THRESHOLD=0.6      # 灌溉阈值
HUMIDITY_LOW_THRESHOLD=0.3    # 湿度低阈值
HUMIDITY_HIGH_THRESHOLD=0.8   # 湿度高阈值
```

### 邮件告警配置
```env
EMAIL_FROM=your-email@example.com
EMAIL_PASSWORD=your-password
SMTP_SERVER=smtp.qq.com
SMTP_PORT=465
ALERT_EMAIL_RECIPIENTS=user1@example.com,user2@example.com
```

### 天气配置
```env
WEATHER_LATITUDE=35           # 纬度
WEATHER_LONGITUDE=113         # 经度
CROP_TYPE=wheat              # 作物类型
WEATHER_STATION_ELEVATION=100.0    # 气象站海拔（米）
WEATHER_STATION_WIND_HEIGHT=2.0    # 风速测量高度（米）
```

## 运行说明

### 开发环境运行

1. **启动应用**:
```bash
python run.py
```

2. **运行模型**:
```bash
python run_model.py
```

3. **访问应用**:
- 主页: http://localhost:5000
- 仪表板: http://localhost:5000/dashboard  
- API文档: http://localhost:5000/api/docs

### 生产环境部署

1. **使用Gunicorn**:
```bash
gunicorn -w 4 -b 0.0.0.0:5000 src.app:app
```

2. **使用Waitress** (Windows推荐):
```bash
waitress-serve --host=0.0.0.0 --port=5000 src.app:app
```

### Windows PowerShell运行

```powershell
# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 运行应用
python run.py

# 或者一行命令
cd drought_smart_irrigation; python run.py
```

## API接口

系统提供完整的RESTful API接口：

### 核心接口
- `GET /api/soil/moisture` - 获取土壤湿度数据
- `POST /api/irrigation/decision` - 获取灌溉决策
- `GET /api/weather/forecast` - 获取天气预报
- `GET /api/crop/growth` - 获取作物生长数据
- `GET /api/model/fao` - 运行FAO模型
- `GET /api/model/aquacrop` - 运行AquaCrop模型

### 系统接口  
- `GET /api/health` - 系统健康检查
- `GET /api/status` - 系统状态
- `POST /api/auth/login` - 用户登录
- `GET /api/logs` - 系统日志

详细API文档请访问: http://localhost:5000/api/docs

## 模型说明

### FAO-56蒸散发模型
- **功能**: 计算参考作物蒸散量(ET0)和作物蒸散量(ETc)
- **输入**: 气象数据、作物系数、土壤参数
- **输出**: 日蒸散量、土壤水分平衡、灌溉需求

### AquaCrop作物模型  
- **功能**: 模拟作物生长发育和产量形成
- **输入**: 气象数据、土壤参数、作物参数、管理措施
- **输出**: 生物量、产量、水分利用效率、生育期

### 灌溉决策算法
- **多因子决策**: 综合土壤湿度、作物需水、天气预报
- **生育期调节**: 根据作物生育阶段动态调整阈值
- **精准控制**: 支持5-50mm多级灌溉量控制
- **风险评估**: 考虑降雨概率和灌溉风险

## 数据流程

1. **数据采集**: 土壤传感器 → 实时湿度数据
2. **天气获取**: 气象API → 历史和预报数据  
3. **模型计算**: FAO-56/AquaCrop → 蒸散量和需水量
4. **决策分析**: 灌溉算法 → 灌溉建议和控制指令
5. **结果输出**: Web界面/API → 可视化展示和系统集成

## 开发指南

### 项目架构
- **MVC模式**: 模型-视图-控制器分离
- **模块化设计**: 功能模块独立，便于维护扩展
- **配置驱动**: 统一配置管理，支持多环境部署
- **日志记录**: 完整的操作日志和错误追踪

### 代码规范
- **PEP 8**: Python代码风格规范
- **类型注解**: 使用类型提示提高代码可读性
- **文档字符串**: 完整的函数和类文档
- **单元测试**: 核心功能测试覆盖

### 扩展开发
- **新增作物**: 在配置文件中添加作物参数
- **自定义模型**: 继承基础模型类实现新算法
- **API扩展**: 在routes.py中添加新的接口
- **前端定制**: 修改templates和static文件

## 故障排除

### 常见问题

1. **依赖安装失败**
```bash
# 升级pip
python -m pip install --upgrade pip
# 使用国内镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
```

2. **模型运行错误**
- 检查气象数据格式和完整性
- 确认土壤参数配置正确
- 查看logs目录下的错误日志

3. **API访问失败**  
- 检查网络连接和API密钥
- 确认设备ID和地块ID配置
- 查看API响应日志

4. **数据库连接问题**
- 检查数据库配置和权限
- 确认数据库服务运行状态
- 查看数据库连接日志

### 日志查看
```bash
# 应用日志
tail -f logs/app.log

# 灌溉系统日志  
tail -f logs/irrigation_system.log

# API响应日志
ls logs/api_response_*.json
```

## 许可证

MIT License

## 贡献指南

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 联系方式

- 项目维护者: [维护者信息]
- 技术支持: [支持邮箱]
- 问题反馈: [GitHub Issues链接]

---

*最后更新: 2025年3月*