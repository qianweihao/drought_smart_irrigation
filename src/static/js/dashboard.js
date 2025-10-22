/**
 * dashboard.js
 * 灌溉系统仪表盘交互功能 (Refactored for API interaction)
 */

// 全局变量存储 Chart 实例
let humidityChart = null;
let etChart = null; // 新增ETref和ETc图表变量

// --- Helper Functions ---

/**
 * 通用 API 请求函数
 * @param {string} url API 端点 URL
 * @param {object} options Fetch API 选项 (method, headers, body, etc.)
 * @param {HTMLElement} buttonElement (可选) 触发请求的按钮，用于显示加载状态
 * @returns {Promise<object>} 解析后的 JSON 数据
 */
async function fetchData(url, options = {}, buttonElement = null) {
    if (buttonElement) {
        buttonElement.disabled = true;
        buttonElement.classList.add('loading');
    }
    try {
        console.log(`发起请求: ${url}`, options);
        const response = await fetch(url, options);
        
        // 输出响应状态和头信息以便调试
        console.log(`API响应: ${url}`, {
            status: response.status,
            statusText: response.statusText,
            headers: Object.fromEntries([...response.headers])
        });
        
        if (!response.ok) {
            let errorMsg = `请求失败: ${response.status} ${response.statusText}`;
            let errorData = { message: errorMsg };
            
            try {
                // 尝试解析错误响应的JSON数据
                errorData = await response.json();
                console.error(`API错误详情: ${url}`, errorData);
            } catch (parseError) {
                console.error(`无法解析错误响应为JSON: ${url}`, parseError);
            }
            
            // 对特定状态码提供更有用的错误信息
            if (response.status === 404) {
                throw new Error(errorData.message || '未找到数据或资源');
            } else if (response.status === 503) {
                throw new Error(errorData.message || '服务暂时不可用，可能是无法获取真实数据');
            } else {
                throw new Error(errorData.message || errorMsg);
            }
        }
        
        const data = await response.json();
        console.log(`API数据: ${url}`, data);
        return data;
    } catch (error) {
        console.error(`请求 ${url} 出错:`, error);
        showToast(`错误: ${error.message}`, 'error');
        throw error; // 重新抛出错误，以便调用者可以处理
    } finally {
        if (buttonElement) {
            buttonElement.disabled = false;
            buttonElement.classList.remove('loading');
        }
    }
}

/** 更新ETref和ETc趋势图 */
async function updateETChart(buttonElement = null) {
    console.log('开始更新ETref和ETc趋势图...');
    
    // 显示加载状态
    const loadingElement = document.getElementById('et-chart-loading');
    const errorElement = document.getElementById('et-chart-error');
    const chartContainer = document.getElementById('et-chart-container');
    
    if (loadingElement) loadingElement.style.display = 'block';
    if (errorElement) errorElement.style.display = 'none';
    if (chartContainer) chartContainer.style.display = 'block';
    
    // 设置按钮加载状态
    if (buttonElement) {
        buttonElement.disabled = true;
        const originalText = buttonElement.innerHTML;
        buttonElement.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>加载中...';
        
        // 恢复按钮状态的函数
        const restoreButton = () => {
            buttonElement.disabled = false;
            buttonElement.innerHTML = originalText;
        };
        
        // 5秒后自动恢复按钮状态
        setTimeout(restoreButton, 5000);
    }
    
    try {
        // 获取ETref和ETc数据
        const response = await fetchData('/api/et_history');
        console.log('ETref和ETc数据响应:', response);
        
        if (loadingElement) loadingElement.style.display = 'none';
        
        if (response && response.status === 'success' && response.data) {
            const data = response.data;
            
            // 验证数据有效性
            if (!data.dates || !data.etref || !data.etc || 
                data.dates.length === 0 || data.etref.length === 0 || data.etc.length === 0) {
                throw new Error('ETref和ETc数据为空或格式无效');
            }
            
            // 销毁现有图表
            if (etChart) {
                etChart.destroy();
                etChart = null;
            }
            
            // 获取canvas元素
            const canvas = document.getElementById('et-chart');
            if (!canvas) {
                console.error('找不到ETref和ETc图表canvas元素，ID: et-chart');
                throw new Error('找不到ETref和ETc图表canvas元素');
            }
            
            console.log('找到canvas元素:', canvas);
            
            const ctx = canvas.getContext('2d');
            console.log('ETref和ETc数据:', {
                dates: data.dates,
                etref: data.etref,
                etc: data.etc,
                etref_length: data.etref.length,
                etc_length: data.etc.length,
                etref_sample: data.etref.slice(0, 5),
                etc_sample: data.etc.slice(0, 5),
                etref_types: data.etref.slice(0, 5).map(v => typeof v),
                etc_types: data.etc.slice(0, 5).map(v => typeof v)
            });
            
            // 确保数据是数字类型
            const etrefData = data.etref.map(v => parseFloat(v));
            const etcData = data.etc.map(v => parseFloat(v));
            
            console.log('转换后的数据:', {
                etref_converted: etrefData.slice(0, 5),
                etc_converted: etcData.slice(0, 5)
            });
            
            // 创建新的图表
            etChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.dates,
                    datasets: [
                        {
                            label: 'ETref (参考蒸散量)',
                            data: etrefData,
                            borderColor: '#007bff',
                            backgroundColor: 'rgba(0, 123, 255, 0.1)',
                            borderWidth: 2,
                            fill: false,
                            tension: 0.1,
                            pointRadius: 3,
                            pointHoverRadius: 5
                        },
                        {
                            label: 'ETc (作物蒸散量)',
                            data: etcData,
                            borderColor: '#28a745',
                            backgroundColor: 'rgba(40, 167, 69, 0.1)',
                            borderWidth: 2,
                            fill: false,
                            tension: 0.1,
                            pointRadius: 3,
                            pointHoverRadius: 5
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: {
                            display: true,
                            text: 'ETref和ETc趋势图',
                            font: {
                                size: 16,
                                weight: 'bold'
                            }
                        },
                        legend: {
                            display: true,
                            position: 'top'
                        },
                        tooltip: {
                            mode: 'index',
                            intersect: false,
                            callbacks: {
                                label: function(context) {
                                    return context.dataset.label + ': ' + context.parsed.y.toFixed(2) + ' mm/day';
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            display: true,
                            title: {
                                display: true,
                                text: '日期'
                            },
                            ticks: {
                                maxTicksLimit: 8,
                                maxRotation: 45
                            }
                        },
                        y: {
                            display: true,
                            title: {
                                display: true,
                                text: '蒸散量 (mm/day)'
                            },
                            beginAtZero: false,
                            ticks: {
                                callback: function(value) {
                                    return value.toFixed(2) + ' mm';
                                }
                            }
                        }
                    },
                    interaction: {
                        mode: 'nearest',
                        axis: 'x',
                        intersect: false
                    }
                }
            });
            
            console.log(`ETref和ETc图表创建成功，数据点数: ${data.dates.length}`);
            
            // 确保图表容器可见
            if (chartContainer) {
                chartContainer.style.display = 'block';
                console.log('ETref和ETc图表容器已显示');
            }
            
        } else {
            throw new Error(response?.message || '获取ETref和ETc数据失败');
        }
        
    } catch (error) {
        console.error('更新ETref和ETc图表失败:', error);
        
        if (loadingElement) loadingElement.style.display = 'none';
        if (errorElement) {
            errorElement.style.display = 'block';
            const errorMessageElement = document.getElementById('et-chart-error-message');
            if (errorMessageElement) {
                errorMessageElement.textContent = error.message || '加载ETref和ETc数据失败';
            }
        }
        
        // 隐藏图表容器
        if (chartContainer) chartContainer.style.display = 'none';
        
        showToast(`ETref和ETc图表更新失败: ${error.message}`, 'error');
    } finally {
        // 恢复按钮状态
        if (buttonElement) {
            buttonElement.disabled = false;
            const originalText = buttonElement.getAttribute('data-original-text') || '刷新';
            buttonElement.innerHTML = originalText;
        }
    }
}

/**
 * 显示 Toast 消息
 * @param {string} message 消息内容
 * @param {string} type 消息类型 ('success', 'error', 'info')
 */
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) return;

    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type === 'error' ? 'danger' : type === 'success' ? 'success' : 'primary'} border-0 show`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');

    let iconClass = 'fa-info-circle';
    if (type === 'success') iconClass = 'fa-check-circle';
    if (type === 'error') iconClass = 'fa-exclamation-triangle';

    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                <i class="fas ${iconClass} me-2"></i>
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;

    toastContainer.appendChild(toast);

    const bsToast = new bootstrap.Toast(toast, { delay: 5000 });
    bsToast.show();

    toast.addEventListener('hidden.bs.toast', () => {
        toast.remove();
    });
}

/**
 * 更新 DOM 元素内容，处理加载状态和占位符
 * @param {string} elementId 目标元素的 ID
 * @param {string} content 要显示的内容 (HTML)
 * @param {string} loadingContainerId 加载指示器容器的 ID
 * @param {string} placeholderId 占位符元素的 ID
 */
function updateElementContent(elementId, content, loadingContainerId, placeholderId) {
    const element = document.getElementById(elementId);
    const loadingContainer = document.getElementById(loadingContainerId);
    const placeholder = document.getElementById(placeholderId);

    if (element) {
        element.innerHTML = content;
    }
    if (loadingContainer) {
        loadingContainer.classList.add('d-none');
    }
    if (placeholder) {
        placeholder.classList.add('d-none');
    }
}

// --- Data Update Functions ---

/** 更新土壤墒情卡片 */
async function updateSoilCard(buttonElement = null) {
    const contentElementId = 'soil-data-content';
    const loadingElementId = `${contentElementId}-loading`; // 假设加载器 ID
    const placeholderElementId = `${contentElementId}-placeholder`; // 假设占位符 ID

    try {
        showLoading(contentElementId, loadingElementId, placeholderElementId);
        console.log('正在获取土壤墒情数据...');
        const data = await fetchData('/api/soil_data', {}, buttonElement);

        // 详细记录API响应
        console.log('土壤墒情API响应数据:', data);
        
        // API可能直接返回数据或者嵌套在data属性中
        const soil = data.data || data;
        
        console.log('处理后的土壤墒情数据:', {
            max_humidity: soil.max_humidity,
            min_humidity: soil.min_humidity,
            real_humidity: soil.real_humidity,
            pwp: soil.pwp,
            fc: soil.fc,
            sat: soil.sat,
            is_real_data: soil.is_real_data,
            timestamp: soil.timestamp
        });
        
        if (soil && soil.real_humidity) {
            let statusClass = 'moderate';
            let statusText = '水分适中';
            if (soil.real_humidity > soil.fc) {
                statusClass = 'sufficient';
                statusText = '水分充足';
            } else if (soil.real_humidity < soil.pwp) {
                statusClass = 'insufficient';
                statusText = '水分不足';
            }
            
            console.log('土壤墒情状态:', {
                real_humidity: soil.real_humidity,
                fc: soil.fc,
                pwp: soil.pwp,
                status: statusText
            });

            const contentHtml = `
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div>
                        <span class="data-label">当前湿度</span>
                        <span class="data-value ms-2">${soil.real_humidity?.toFixed(1) || '-'}</span><span class="data-unit">%</span>
                    </div>
                    <span class="badge bg-${statusClass === 'sufficient' ? 'success' : statusClass === 'insufficient' ? 'danger' : 'warning'} text-white">${statusText}</span>
                </div>
                <p class="data-label text-muted mb-0 small">更新时间: ${new Date(soil.timestamp).toLocaleString()}</p>
            `;
            updateElementContent(contentElementId, contentHtml);

            // 更新卡片下方的阈值
            const pwpElement = document.getElementById('soil-pwp');
            const fcElement = document.getElementById('soil-fc');
            const satElement = document.getElementById('soil-sat');
            
            if (pwpElement) {
                pwpElement.textContent = `${soil.pwp !== undefined && soil.pwp !== null ? soil.pwp.toFixed(1) : '-'}%`;
                pwpElement.classList.remove('placeholder');
            }
            
            if (fcElement) {
                fcElement.textContent = `${soil.fc !== undefined && soil.fc !== null ? soil.fc.toFixed(1) : '-'}%`;
                fcElement.classList.remove('placeholder');
            }
            
            if (satElement) {
                satElement.textContent = `${soil.sat !== undefined && soil.sat !== null ? soil.sat.toFixed(1) : '-'}%`;
                satElement.classList.remove('placeholder');
            }
            
            console.log('已更新土壤墒情卡片和阈值显示');

            if (buttonElement) showToast('土壤数据已更新', 'success');
        } else {
            console.warn('土壤数据无效或不完整');
            updateElementContent(contentElementId, '<p class="text-danger">无法加载土壤数据。</p>', loadingElementId, placeholderElementId);
        }
    } catch (error) {
        console.error('更新土壤墒情卡片时出错:', error);
        updateElementContent(contentElementId, '<p class="text-danger">加载土壤数据失败。</p>', loadingElementId, placeholderElementId);
    }
}

/** 更新灌溉决策卡片 */
async function updateDecisionCard(buttonElement = null) {
    const contentElementId = 'irrigation-decision-content';
    const loadingElementId = `${contentElementId}-loading`;
    const placeholderElementId = `${contentElementId}-placeholder`;

    try {
        showLoading(contentElementId, loadingElementId, placeholderElementId);
        const data = await fetchData('/api/irrigation_recommendation', {}, buttonElement);
        
        // API可能直接返回数据或者嵌套在data属性中
        const decision = data.data || data;
        
        if (decision && (decision.irrigation_amount !== undefined || decision.message)) {
            let badgeClass = 'bg-secondary';
            let iconClass = 'fa-info-circle';
            if (decision.irrigation_amount > 0) {
                badgeClass = 'bg-primary';
                iconClass = 'fa-tint';
            } else if (decision.message && (decision.message.includes('充足') || decision.message.includes('延迟'))) {
                badgeClass = 'bg-success';
                iconClass = 'fa-check-circle';
            }

            const contentHtml = `
                <div class="alert ${badgeClass} text-white d-flex align-items-center" role="alert">
                    <i class="fas ${iconClass} me-2"></i>
                    <div>
                        <strong>${decision.irrigation_amount > 0 ? `建议灌溉 ${decision.irrigation_amount.toFixed(1)} mm` : '今日无需灌溉'}</strong><br>
                        <small>${decision.message || '无详细信息'}</small>
                    </div>
                </div>
                <p class="data-label text-muted mb-0 small">决策时间: ${new Date(decision.timestamp).toLocaleString()}</p>
            `;
            updateElementContent(contentElementId, contentHtml);
            if (buttonElement) showToast('灌溉决策已更新', 'success');
        } else {
            updateElementContent(contentElementId, '<p class="text-danger">无法加载灌溉决策。</p>', loadingElementId, placeholderElementId);
        }
    } catch (error) {
        updateElementContent(contentElementId, '<p class="text-danger">加载灌溉决策失败。</p>', loadingElementId, placeholderElementId);
    }
}

/** 更新作物生长卡片 */
async function updateGrowthCard(buttonElement = null) {
    const contentElementId = 'growth-stage-content';
    const loadingElementId = `${contentElementId}-loading`;
    const placeholderElementId = `${contentElementId}-placeholder`;

    try {
        showLoading(contentElementId, loadingElementId, placeholderElementId);
        const data = await fetchData('/api/growth_stage', {}, buttonElement);
        
        // API可能直接返回数据或者嵌套在data属性中
        const growth = data.data || data;
        
        if (growth && growth.stage) {
            const contentHtml = `
                <p class="mb-1">
                    <span class="data-label">当前阶段:</span>
                    <strong class="ms-2">${growth.stage || '未知'}</strong>
                </p>
                 <p class="mb-1">
                    <span class="data-label">模拟天数 (DAP):</span>
                    <span class="ms-2">${growth.dap !== null ? growth.dap : '-'} 天</span>
                </p>
                <p class="mb-1">
                    <span class="data-label">根系深度 (Zr):</span>
                    <span class="ms-2">${growth.root_depth?.toFixed(2) || '-'} m</span>
                </p>
                <p class="mb-0">
                    <span class="data-label">冠层覆盖度 (CC):</span>
                    <span class="ms-2">${growth.canopy_cover?.toFixed(2)*100 || '-'} %</span>
                </p>
                 <p class="data-label text-muted mb-0 small mt-2">更新时间: ${new Date(growth.timestamp).toLocaleString()}</p>
            `;
            updateElementContent(contentElementId, contentHtml);

            // Optionally update canopy cover image based on data.data.canopy_cover
            // const imgElement = document.getElementById('canopy-cover-img');
            // imgElement.src = `/static/images/cc_${Math.round(growth.canopy_cover * 10)}.png`; // Example

            if (buttonElement) showToast('生长信息已更新', 'success');
        } else {
             updateElementContent(contentElementId, '<p class="text-danger">无法加载生长信息。</p>', loadingElementId, placeholderElementId);
        }
    } catch (error) {
        updateElementContent(contentElementId, '<p class="text-danger">加载生长信息失败。</p>', loadingElementId, placeholderElementId);
    }
}

/** 更新历史湿度图表 */
async function updateHistoryChart(buttonElement = null) {
    const canvasId = 'humidity-chart';
    const loadingElementId = `${canvasId}-loading`;
    const placeholderElementId = `${canvasId}-placeholder`;

    try {
        showLoading(null, loadingElementId, placeholderElementId); // 只显示加载状态
        
        // 可选：显示调试提示
        console.log('正在获取历史土壤湿度数据...');
        
        const data = await fetchData('/api/soil_humidity_history?days=30', {}, buttonElement);
        
        console.log('历史湿度数据响应:', data); // 添加日志以便调试
        
        // 确保数据存在且格式正确
        const history = data.data || data;
        
        // 检查是否有所有必要的数据
        const hasValidData = history && 
                            history.dates && 
                            Array.isArray(history.dates) && 
                            history.dates.length > 0 && 
                            history.soilHumidity10Value && 
                            history.soilHumidity20Value && 
                            history.soilHumidity30Value;
        
        console.log('数据有效性检查:', {
            hasHistory: !!history,
            hasDates: !!(history && history.dates),
            datesIsArray: !!(history && history.dates && Array.isArray(history.dates)),
            datesLength: history && history.dates ? history.dates.length : 0,
            has10cm: !!(history && history.soilHumidity10Value),
            has20cm: !!(history && history.soilHumidity20Value),
            has30cm: !!(history && history.soilHumidity30Value),
            isValid: hasValidData
        });

        if (hasValidData) {
            const chartData = {
                labels: history.dates,
                datasets: [
                    {
                        label: '10cm 湿度 (%)',
                        data: history.soilHumidity10Value,
                        borderColor: 'rgb(54, 162, 235)',
                        backgroundColor: 'rgba(54, 162, 235, 0.1)',
                        borderWidth: 1.5,
                        fill: true,
                        tension: 0.1
                    },
                    {
                        label: '20cm 湿度 (%)',
                        data: history.soilHumidity20Value,
                        borderColor: 'rgb(255, 159, 64)',
                        backgroundColor: 'rgba(255, 159, 64, 0.1)',
                        borderWidth: 1.5,
                        fill: true,
                        tension: 0.1
                    },
                    {
                        label: '30cm 湿度 (%)',
                        data: history.soilHumidity30Value,
                        borderColor: 'rgb(75, 192, 192)',
                        backgroundColor: 'rgba(75, 192, 192, 0.1)',
                        borderWidth: 1.5,
                        fill: true,
                        tension: 0.1
                    }
                ]
            };

            const config = {
                type: 'line',
                data: chartData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: false,
                            title: {
                                display: true,
                                text: '土壤体积含水量 (%)'
                            }
                        },
                        x: {
                             title: {
                                display: true,
                                text: '日期'
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            position: 'top',
                        },
                        tooltip: {
                            mode: 'index',
                            intersect: false,
                        }
                    },
                     hover: {
                        mode: 'nearest',
                        intersect: true
                    }
                }
            };

            const canvasElement = document.getElementById(canvasId);
            if (!canvasElement) {
                console.error(`找不到canvas元素，ID: ${canvasId}`);
                throw new Error(`找不到画布元素: ${canvasId}`);
            }
            
            const ctx = canvasElement.getContext('2d');

            try {
                // 确保画布元素存在
                if (!ctx) {
                    throw new Error(`找不到画布元素: ${canvasId}`);
                }
                
                // 如果图表已存在，先销毁旧实例
                if (humidityChart) {
                    humidityChart.destroy();
                }
                
                // 创建新图表实例
                humidityChart = new Chart(ctx, config);
                
                // 隐藏加载状态
                hideLoading(null, loadingElementId, placeholderElementId);
                
                // 确保画布显示
                const canvas = document.getElementById(canvasId);
                if (canvas) {
                    canvas.style.display = 'block';
                }
                
                document.getElementById(placeholderElementId).classList.add('d-none');
                
                console.log('成功创建土壤湿度历史图表');
                
                if (buttonElement) showToast('历史数据图表已更新', 'success');
            } catch (chartError) {
                console.error('创建图表时出错:', chartError);
                hideLoading(null, loadingElementId, placeholderElementId);
                document.getElementById(canvasId).style.display = 'none';
                const placeholder = document.getElementById(placeholderElementId);
                placeholder.textContent = `创建图表时出错: ${chartError.message}`;
                placeholder.classList.remove('d-none');
            }
        } else {
            // 如果没有数据，隐藏图表并显示提示
            console.warn('无有效的土壤湿度历史数据');
            hideLoading(null, loadingElementId, placeholderElementId);
            
            const canvasElement = document.getElementById(canvasId);
            if (canvasElement) {
                canvasElement.style.display = 'none';
            }
            
            const placeholder = document.getElementById(placeholderElementId);
            if (placeholder) {
                placeholder.textContent = '无可用历史数据。请检查土壤湿度传感器连接是否正常。';
                placeholder.classList.remove('d-none');
            }
        }
    } catch (error) {
        // 发生错误时，隐藏图表并显示错误提示
        console.error('获取历史湿度数据时出错:', error);
        hideLoading(null, loadingElementId, placeholderElementId);
        
        const canvasElement = document.getElementById(canvasId);
        if (canvasElement) {
            canvasElement.style.display = 'none';
        }
        
        const placeholder = document.getElementById(placeholderElementId);
        if (placeholder) {
            placeholder.textContent = `加载图表数据失败: ${error.message}`;
            placeholder.classList.remove('d-none');
        }
    }
}

/** 处理"生成今日决策"按钮点击 */
async function handleMakeDecision(buttonElement) {
    const statusElement = document.getElementById('make-decision-status');
    statusElement.textContent = '正在生成决策...';
    statusElement.classList.remove('text-danger', 'text-success');
    statusElement.classList.add('text-info');

    try {
        // 调用make_decision API生成灌溉决策
        const result = await fetchData('/make_decision', { method: 'POST' }, buttonElement);
        console.log('生成灌溉决策响应:', result);

        if (result && result.status === 'success') {
            showToast('灌溉决策已生成，正在更新展示...', 'success');
            statusElement.textContent = '决策生成成功!';
            statusElement.classList.remove('text-info', 'text-danger');
            statusElement.classList.add('text-success');
            
            // 立即刷新决策卡片以获取最新结果
            await updateDecisionCard();
        } else {
            const errorMessage = result.message || '未知错误';
            console.error('决策生成失败:', errorMessage);
            statusElement.textContent = `决策生成失败: ${errorMessage}`;
            statusElement.classList.remove('text-info');
            statusElement.classList.add('text-danger');
            showToast(`决策请求失败: ${errorMessage}`, 'error');
        }
    } catch (error) {
        console.error('决策生成出错:', error);
        statusElement.textContent = `决策生成出错: ${error.message}`;
        statusElement.classList.remove('text-info');
        statusElement.classList.add('text-danger');
        showToast(`决策生成出错: ${error.message}`, 'error');
    }
}

// --- Utility for Loading States ---
function showLoading(contentElementId, loadingElementId, placeholderElementId) {
    if (contentElementId) {
         const contentElement = document.getElementById(contentElementId);
         if (contentElement) contentElement.innerHTML = ''; // 清空内容区域
    }
     if (loadingElementId) {
        const loadingElement = document.getElementById(loadingElementId);
        if (loadingElement) loadingElement.classList.remove('d-none');
    }
     if (placeholderElementId) {
        const placeholderElement = document.getElementById(placeholderElementId);
        if (placeholderElement) placeholderElement.classList.remove('d-none');
    }
}

function hideLoading(contentElementId, loadingElementId, placeholderElementId) {
     if (loadingElementId) {
        const loadingElement = document.getElementById(loadingElementId);
        if (loadingElement) loadingElement.classList.add('d-none');
    }
     if (placeholderElementId) {
        const placeholderElement = document.getElementById(placeholderElementId);
        if (placeholderElement) placeholderElement.classList.add('d-none');
    }
}

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    console.log('仪表盘页面加载完成，开始初始化...');
    
    // 详细检查DOM元素状态
    console.log('=== DOM元素检查 ===');
    const etChart = document.getElementById('et-chart');
    const humidityChart = document.getElementById('humidity-chart');
    const etChartContainer = document.getElementById('et-chart-container');
    const etChartLoading = document.getElementById('et-chart-loading');
    const etChartError = document.getElementById('et-chart-error');
    
    console.log('et-chart元素:', etChart);
    console.log('et-chart是否存在:', !!etChart);
    console.log('et-chart容器:', etChartContainer);
    console.log('et-chart加载元素:', etChartLoading);
    console.log('et-chart错误元素:', etChartError);
    
    console.log('humidity-chart元素:', humidityChart);
    console.log('humidity-chart是否存在:', !!humidityChart);
    
    if (etChart) {
        console.log('et-chart样式:', {
            display: etChart.style.display,
            visibility: etChart.style.visibility,
            offsetWidth: etChart.offsetWidth,
            offsetHeight: etChart.offsetHeight
        });
    }
    
    if (humidityChart) {
        console.log('humidity-chart样式:', {
            display: humidityChart.style.display,
            visibility: humidityChart.style.visibility,
            offsetWidth: humidityChart.offsetWidth,
            offsetHeight: humidityChart.offsetHeight
        });
    }
    console.log('=== DOM元素检查结束 ===');

    // 初始加载所有卡片数据
    updateSoilCard();
    updateDecisionCard();
    updateGrowthCard();
    updateHistoryChart();
    updateETChart();

    // 绑定刷新按钮事件
    document.getElementById('refresh-soil-data')?.addEventListener('click', (e) => updateSoilCard(e.currentTarget));
    document.getElementById('refresh-decision-data')?.addEventListener('click', (e) => updateDecisionCard(e.currentTarget));
    document.getElementById('refresh-growth-data')?.addEventListener('click', (e) => updateGrowthCard(e.currentTarget));
    document.getElementById('refresh-history-data')?.addEventListener('click', (e) => updateHistoryChart(e.currentTarget));
    document.getElementById('refresh-et-data')?.addEventListener('click', (e) => updateETChart(e.currentTarget));

    // 绑定"生成决策"按钮事件
    document.getElementById('make-decision-btn')?.addEventListener('click', (e) => handleMakeDecision(e.currentTarget));

    console.log('仪表盘 JS 初始化完成');
});