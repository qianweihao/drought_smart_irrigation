# 智能土壤灌溉系统

基于FAO-56模型的智能土壤灌溉决策系统，用于优化农作物灌溉策略。

## 功能特点

- 基于FAO-56模型的灌溉决策
- 实时土壤湿度监测
- 天气数据集成
- 自动灌溉控制
- 告警通知系统
- 安全认证机制

## 系统要求

- Python 3.8+
- 其他依赖见 requirements.txt

## 项目结构

```
drought-soil-irrigation-wheat/
├── src/                    # 源代码目录
│   ├── api/               # API接口
│   │   └── routes.py     # 路由定义
│   ├── models/           # 模型
│   │   └── fao_model.py # FAO模型实现
│   ├── services/         # 业务逻辑
│   │   ├── irrigation_service.py
│   │   └── alert_service.py
│   ├── utils/           # 工具函数
│   │   ├── auth.py     # 认证
│   │   ├── validators.py # 数据验证
│   │   ├── logger.py   # 日志
│   │   └── email_sender.py # 邮件发送
│   └── app.py          # 应用入口
├── data/               # 数据目录
│   ├── weather/       # 天气数据
│   ├── soil/         # 土壤数据
│   └── model_output/ # 模型输出
├── config/           # 配置文件
│   └── config.py    # 配置定义
├── tests/           # 测试代码
├── docs/           # 文档
├── requirements.txt # 依赖管理
├── .env.example    # 环境变量示例
└── README.md      # 项目说明
```

## 安装步骤

1. 克隆项目：
```bash
git clone [项目地址]
cd drought-soil-irrigation-wheat
```

2. 创建虚拟环境：
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. 安装依赖：
```bash
pip install -r requirements.txt
```

4. 配置环境变量：
```bash
cp .env.example .env
# 编辑 .env 文件，填入必要的配置信息
```

## 配置说明

项目使用`.env`文件进行配置，可以从`.env.example`复制并修改：

```bash
# Windows PowerShell
Copy-Item .env.example .env

# Linux/MacOS
cp .env.example .env
```

主要配置项：

1. **API设置**
   - `SOIL_API_URL`: 土壤湿度API的基础URL
   - `SOIL_API_KEY`: 访问API的密钥

2. **设备和地块设置**
   - `DEFAULT_FIELD_ID`: 默认地块ID
   - `DEFAULT_DEVICE_ID`: 默认设备ID

3. **土壤湿度传感器默认值**（当API无法访问时使用）
   - `DEFAULT_MAX_HUMIDITY`: 默认最大湿度值
   - `DEFAULT_MIN_HUMIDITY`: 默认最小湿度值
   - `DEFAULT_SAT`: 默认饱和含水量
   - `DEFAULT_PWP`: 默认凋萎点

4. **灌溉决策参数**
   - `SOIL_DEPTH_CM`: 土壤深度(厘米)
   - `MAX_FORECAST_DAYS`: 天气预报最大天数
   - `IRRIGATION_THRESHOLD`: 灌溉阈值

5. **数据查询日期范围**
   - `MOISTURE_DATA_START_YEAR/MONTH/DAY`: 湿度数据查询起始日期
   - `FORECAST_DATA_START_YEAR/MONTH/DAY`: 预测数据开始日期
   - `FORECAST_DATA_END_YEAR/MONTH/DAY`: 预测数据结束日期
   - `FAO_MODEL_START_YEAR/DOY`: FAO模型开始日期（格式：年份和一年中的第几天）
   - `FAO_MODEL_END_YEAR/DOY`: FAO模型结束日期（格式：年份和一年中的第几天）

## 运行说明

### 开发环境设置

1. 启用调试模式：
```bash
export FLASK_ENV=development  # Linux/Mac
set FLASK_ENV=development     # Windows
```

2. 运行开发服务器：
```bash
python src/app.py
```

### 在Windows PowerShell中运行

在Windows PowerShell中，命令分隔符使用分号(;)，而不是&&。例如：

```powershell
cd drought-soil-irrigation-wheat; python run.py
```

或者单独执行两个命令：

```powershell
cd drought-soil-irrigation-wheat
python run.py
```

## 贡献指南

1. Fork 项目
2. 创建特性分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

## 许可证

MIT License 