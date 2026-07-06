const bridge = window.AstrBotPluginPage;

// ==================== 状态管理 ====================
const state = {
    selectedFile: null,
    isDistributing: false
};

// ==================== DOM 引用 ====================
const $ = id => document.getElementById(id);
const dropZone = $('dropZone');
const fileInput = $('fileInput');
const fileInfo = $('fileInfo');
const fileName = $('fileName');
const fileSize = $('fileSize');
const removeFileBtn = $('removeFile');
const groupIdsInput = $('groupIdsInput');
const folderInput = $('folderInput');
const autoClassify = $('autoClassify');
const distributeBtn = $('distributeBtn');
const resultArea = $('resultArea');
const totalCount = $('totalCount');
const successCount = $('successCount');
const failedCount = $('failedCount');
const resultList = $('resultList');

// ==================== 初始化 ====================
let pluginName = '';

async function init() {
    try {
        const context = await bridge.ready();
        pluginName = context.pluginName;
        console.log('[FileMover] Plugin context:', context);
        console.log('[FileMover] Plugin name:', pluginName);
        
        // 测试后端连通性
        await testBackend();

        // 监听主题切换
        bridge.onContext(() => {
            const isDark = bridge.getContext()?.isDark || false;
            document.getElementById('app').setAttribute('data-theme', isDark ? 'dark' : 'light');
        });

        // 监听输入变化，更新按钮状态
        groupIdsInput.addEventListener('input', updateDistributeBtn);
        folderInput.addEventListener('input', updateDistributeBtn);
        autoClassify.addEventListener('change', updateDistributeBtn);

        // 初始化按钮状态
        updateDistributeBtn();
    } catch (err) {
        console.error('[FileMover] 初始化失败:', err);
        alert(`插件初始化失败: ${err.message}`);
    }
}

// ==================== 构造请求 URL ====================
function getApiUrl(path) {
    const url = `/api/v1/plugins/extensions/${pluginName}${path}`;
    console.log('[FileMover] 请求 URL:', url);
    return url;
}

// ==================== 测试后端连通性 ====================
async function testBackend() {
    try {
        const response = await fetch(getApiUrl('/ping'), {
            credentials: 'include'
        });
        if (response.ok) {
            const data = await response.json();
            console.log('[FileMover] 后端连通性测试成功:', data);
        } else {
            console.warn('[FileMover] 后端连通性测试失败:', response.status, response.statusText);
        }
    } catch (err) {
        console.error('[FileMover] 后端连通性测试异常:', err);
    }
}

// ==================== 更新分发按钮状态 ====================
function updateDistributeBtn() {
    const hasFile = !!state.selectedFile;
    const raw = groupIdsInput.value;
    const groups = raw.split(',').map(s => s.trim()).filter(Boolean);
    const hasGroups = groups.length > 0;
    
    distributeBtn.disabled = !hasFile || !hasGroups || state.isDistributing;
}

// ==================== 文件上传 ====================
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});
dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
});
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
        handleFile(e.dataTransfer.files[0]);
    }
});
fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
        handleFile(fileInput.files[0]);
    }
});

function handleFile(file) {
    state.selectedFile = file;
    fileName.textContent = file.name;
    fileSize.textContent = (file.size / 1024 / 1024).toFixed(2) + ' MB';
    fileInfo.style.display = 'flex';
    dropZone.style.display = 'none';
    updateDistributeBtn();
}

removeFileBtn.addEventListener('click', () => {
    state.selectedFile = null;
    fileInfo.style.display = 'none';
    dropZone.style.display = 'block';
    fileInput.value = '';
    updateDistributeBtn();
});

// ==================== 解析群号 ====================
function parseGroupIds(input) {
    return input.split(',')
        .map(s => s.trim())
        .filter(s => s.length > 0 && /^\d+$/.test(s));
}

// ==================== 分发 ====================
distributeBtn.addEventListener('click', async () => {
    if (state.isDistributing) return;

    const groupIds = parseGroupIds(groupIdsInput.value);
    if (groupIds.length === 0) {
        alert('请填写至少一个有效的群号（纯数字）。');
        return;
    }

    const formData = new FormData();
    formData.append('file', state.selectedFile);
    formData.append('target_groups', groupIds.join(','));
    
    if (autoClassify.checked) {
        formData.append('target_folder', '');
        formData.append('auto_classify', 'true');
    } else {
        formData.append('target_folder', folderInput.value.trim() || '');
        formData.append('auto_classify', 'false');
    }

    state.isDistributing = true;
    distributeBtn.disabled = true;
    distributeBtn.textContent = '分发中...';
    distributeBtn.classList.add('loading');
    resultArea.style.display = 'none';

    const url = getApiUrl('/upload');
    console.log('[FileMover] 发起分发请求:', url);

    try {
        const response = await fetch(url, {
            method: 'POST',
            body: formData,
            credentials: 'include'
        });

        console.log('[FileMover] 响应状态:', response.status);

        if (!response.ok) {
            const text = await response.text();
            throw new Error(`HTTP ${response.status}: ${text}`);
        }

        const result = await response.json();
        console.log('[FileMover] 分发结果:', result);
        showResults(result.data || result);
    } catch (err) {
        console.error('[FileMover] 分发失败:', err);
        alert(`分发失败: ${err.message}`);
        resultArea.style.display = 'block';
        totalCount.textContent = '0';
        successCount.textContent = '0';
        failedCount.textContent = '1';
        resultList.innerHTML = `
            <div class="result-item">
                <span>系统</span>
                <span class="status failed">❌ 请求失败: ${err.message}</span>
            </div>
        `;
    } finally {
        state.isDistributing = false;
        distributeBtn.disabled = false;
        distributeBtn.textContent = '分发文件';
        distributeBtn.classList.remove('loading');
        updateDistributeBtn();
    }
});

// ==================== 显示结果 ====================
function showResults(result) {
    resultArea.style.display = 'block';
    totalCount.textContent = result.total || 0;
    successCount.textContent = result.success_count || 0;
    failedCount.textContent = result.failed_count || 0;
    
    resultList.innerHTML = '';
    if (result.results && result.results.length > 0) {
        result.results.forEach(r => {
            const div = document.createElement('div');
            div.className = 'result-item';
            div.innerHTML = `
                <span>群 ${r.group_id}</span>
                <span class="status ${r.success ? 'success' : 'failed'}">
                    ${r.success ? '✅ 成功' : '❌ ' + (r.error || '失败')}
                </span>
            `;
            resultList.appendChild(div);
        });
    } else {
        resultList.innerHTML = '<div class="result-item">没有返回详细结果。</div>';
    }
}

// ==================== 启动 ====================
init();