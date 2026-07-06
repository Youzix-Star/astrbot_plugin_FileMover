const bridge = window.AstrBotPluginPage;

const state = {
    selectedFile: null,
    groups: [],
    folders: [],
    selectedGroups: [],
    selectedFolder: '',
    autoClassify: false,
    isDistributing: false
};

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

// ========== 获取插件名 ==========
let pluginName = '';

async function init() {
    try {
        const context = await bridge.ready();
        pluginName = context.pluginName;
        console.log('Plugin context:', context);
        
        await loadGroups();
        if (state.groups.length > 0) {
            await loadFolders(state.groups[0].group_id);
        }
        
        bridge.onContext(() => {
            const isDark = bridge.getContext()?.isDark || false;
            document.getElementById('app').setAttribute('data-theme', isDark ? 'dark' : 'light');
        });
    } catch (err) {
        console.error('初始化失败:', err);
    }
}

// ========== 构造请求 URL ==========
function getApiUrl(path) {
    return `/api/v1/plugins/extensions/${pluginName}${path}`;
}

// ========== 加载数据 ==========
async function loadGroups() {
    try {
        const response = await fetch(getApiUrl('/groups'), {
            credentials: 'include'
        });
        const result = await response.json();
        console.log('Groups response:', result);
        state.groups = result.data?.groups || result.groups || [];
        renderGroupSelect();
    } catch (err) {
        console.error('加载群列表失败:', err);
        groupSelect.innerHTML = `<div class="loading">❌ 加载失败: ${err.message}</div>`;
    }
}

async function loadFolders(groupId) {
    if (!groupId) return;
    try {
        const response = await fetch(getApiUrl(`/folders?group_id=${groupId}`), {
            credentials: 'include'
        });
        const result = await response.json();
        state.folders = result.data?.folders || result.folders || [];
        renderFolderSelect();
    } catch (err) {
        console.error('加载文件夹列表失败:', err);
    }
}

// ========== 渲染 ==========
function renderGroupSelect() {
    if (state.groups.length === 0) {
        groupSelect.innerHTML = '<div class="loading">⚠️ 未加入任何群聊</div>';
        return;
    }
    
    const select = document.createElement('select');
    select.multiple = true;
    select.size = Math.min(state.groups.length, 6);
    select.id = 'groupSelectInner';
    
    state.groups.forEach(g => {
        const opt = document.createElement('option');
        opt.value = g.group_id;
        opt.textContent = `${g.group_name || g.group_id} (${g.group_id})`;
        select.appendChild(opt);
    });
    
    select.addEventListener('change', () => {
        state.selectedGroups = Array.from(select.selectedOptions).map(o => o.value);
        updateDistributeBtn();
        if (state.selectedGroups.length === 1) {
            loadFolders(parseInt(state.selectedGroups[0]));
        } else {
            folderSelect.innerHTML = '<option value="">（多群选择，文件夹将自动创建）</option>';
        }
    });
    
    groupSelect.innerHTML = '';
    groupSelect.appendChild(select);
}

function renderFolderSelect() {
    folderSelect.innerHTML = '<option value="">（根目录）</option>';
    state.folders.forEach(f => {
        const opt = document.createElement('option');
        opt.value = f.folder_name;
        opt.textContent = f.folder_name;
        folderSelect.appendChild(opt);
    });
    folderSelect.value = state.selectedFolder;
}

function updateDistributeBtn() {
    distributeBtn.disabled = !state.selectedFile || state.selectedGroups.length === 0 || state.isDistributing;
}

// ========== 文件上传 ==========
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

// ========== 分发 ==========
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

init();