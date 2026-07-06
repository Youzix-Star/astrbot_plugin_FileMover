const bridge = window.AstrBotPluginPage;

// ==================== 状态管理 ====================
const state = {
    selectedFile: null,
    groups: [],
    folders: [],
    selectedGroups: [],
    selectedFolder: '',
    autoClassify: false,
    isDistributing: false,
    isLoadingGroups: false,
    isLoadingFolders: false
};

// ==================== DOM 引用 ====================
const $ = id => document.getElementById(id);
const dropZone = $('dropZone');
const fileInput = $('fileInput');
const fileInfo = $('fileInfo');
const fileName = $('fileName');
const fileSize = $('fileSize');
const removeFileBtn = $('removeFile');
const groupSelect = $('groupSelect');
const folderSelect = $('folderSelect');
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
        console.log('Plugin context:', context);
        
        // 加载群列表（带转圈）
        await loadGroups();
        
        // 监听主题切换
        bridge.onContext(() => {
            const isDark = bridge.getContext()?.isDark || false;
            document.getElementById('app').setAttribute('data-theme', isDark ? 'dark' : 'light');
        });
    } catch (err) {
        console.error('初始化失败:', err);
        groupSelect.innerHTML = `
            <div class="loading-state error-msg">
                <span>❌ 插件初始化失败: ${err.message}</span>
                <button class="retry-btn" onclick="window._retryInit()">重试</button>
            </div>
        `;
    }
}

// ==================== 构造请求 URL ====================
function getApiUrl(path) {
    return `/api/v1/plugins/extensions/${pluginName}${path}`;
}

// ==================== 加载群列表（带转圈 + 重试） ====================
async function loadGroups() {
    if (state.isLoadingGroups) return;
    state.isLoadingGroups = true;

    // 显示转圈加载
    groupSelect.innerHTML = `
        <div class="loading-state">
            <span class="spinner"></span>
            加载群列表中...
        </div>
    `;

    try {
        const response = await fetch(getApiUrl('/groups'), {
            credentials: 'include'
        });
        const result = await response.json();
        console.log('Groups response:', result);
        
        state.groups = result.data?.groups || result.groups || [];
        renderGroupSelect();
        
        // 加载第一个群的文件夹
        if (state.groups.length > 0) {
            await loadFolders(state.groups[0].group_id);
        }
    } catch (err) {
        console.error('加载群列表失败:', err);
        groupSelect.innerHTML = `
            <div class="loading-state error-msg">
                <span>❌ 加载失败: ${err.message}</span>
                <button class="retry-btn" id="retryGroupsBtn">重试</button>
            </div>
        `;
        const retryBtn = document.getElementById('retryGroupsBtn');
        if (retryBtn) {
            retryBtn.addEventListener('click', () => loadGroups());
        }
    } finally {
        state.isLoadingGroups = false;
    }
}

// ==================== 加载文件夹列表（带转圈） ====================
async function loadFolders(groupId) {
    if (!groupId) return;
    if (state.isLoadingFolders) return;
    state.isLoadingFolders = true;

    // 显示加载状态
    folderSelect.innerHTML = `
        <option value="" disabled class="folder-loading-select">⏳ 加载文件夹...</option>
    `;
    folderSelect.disabled = true;

    try {
        const response = await fetch(getApiUrl(`/folders?group_id=${groupId}`), {
            credentials: 'include'
        });
        const result = await response.json();
        state.folders = result.data?.folders || result.folders || [];
        renderFolderSelect();
    } catch (err) {
        console.error('加载文件夹列表失败:', err);
        folderSelect.innerHTML = `
            <option value="">❌ 加载失败，请重试</option>
        `;
        folderSelect.disabled = false;
    } finally {
        state.isLoadingFolders = false;
    }
}

// ==================== 渲染群列表 ====================
function renderGroupSelect() {
    if (state.groups.length === 0) {
        groupSelect.innerHTML = `
            <div class="loading-state" style="color: var(--text-secondary);">
                <span>⚠️ 未加入任何群聊</span>
                <button class="retry-btn" id="retryGroupsBtn">刷新</button>
            </div>
        `;
        const retryBtn = document.getElementById('retryGroupsBtn');
        if (retryBtn) {
            retryBtn.addEventListener('click', () => loadGroups());
        }
        return;
    }
    
    const select = document.createElement('select');
    select.multiple = true;
    select.size = Math.min(state.groups.length, 6);
    select.id = 'groupSelectInner';
    
    state.groups.forEach(g => {
        const opt = document.createElement('option');
        opt.value = g.group_id;
        const name = g.group_name || g.group_id;
        opt.textContent = `${name} (${g.group_id})`;
        select.appendChild(opt);
    });
    
    select.addEventListener('change', () => {
        state.selectedGroups = Array.from(select.selectedOptions).map(o => o.value);
        updateDistributeBtn();
        // 单选时加载文件夹
        if (state.selectedGroups.length === 1) {
            loadFolders(parseInt(state.selectedGroups[0]));
        } else {
            folderSelect.innerHTML = '<option value="">（多群选择，文件夹将自动创建）</option>';
            folderSelect.disabled = false;
        }
    });
    
    groupSelect.innerHTML = '';
    groupSelect.appendChild(select);
    updateDistributeBtn();
}

// ==================== 渲染文件夹列表 ====================
function renderFolderSelect() {
    folderSelect.innerHTML = '<option value="">（根目录）</option>';
    state.folders.forEach(f => {
        const opt = document.createElement('option');
        opt.value = f.folder_name;
        opt.textContent = f.folder_name;
        folderSelect.appendChild(opt);
    });
    folderSelect.value = state.selectedFolder;
    folderSelect.disabled = false;
}

// ==================== 更新分发按钮状态 ====================
function updateDistributeBtn() {
    distributeBtn.disabled = !state.selectedFile || state.selectedGroups.length === 0 || state.isDistributing;
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

// ==================== 分发 ====================
autoClassify.addEventListener('change', () => {
    state.autoClassify = autoClassify.checked;
});

distributeBtn.addEventListener('click', async () => {
    if (state.isDistributing) return;
    
    const formData = new FormData();
    formData.append('file', state.selectedFile);
    formData.append('target_groups', state.selectedGroups.join(','));
    formData.append('target_folder', state.selectedFolder || '');
    formData.append('auto_classify', state.autoClassify ? 'true' : 'false');
    
    state.isDistributing = true;
    distributeBtn.disabled = true;
    distributeBtn.textContent = '分发中...';
    distributeBtn.classList.add('loading');
    resultArea.style.display = 'none';
    
    try {
        const response = await fetch(getApiUrl('/upload'), {
            method: 'POST',
            body: formData,
            credentials: 'include'
        });
        const result = await response.json();
        showResults(result.data || result);
    } catch (err) {
        console.error('分发失败:', err);
        alert(`分发失败: ${err.message}`);
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
    (result.results || []).forEach(r => {
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
}

// ==================== 暴露给全局（用于重试） ====================
window._retryLoadGroups = loadGroups;
window._retryInit = init;

// ==================== 启动 ====================
init();