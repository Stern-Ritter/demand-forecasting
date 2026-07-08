/* =========================================================
   Demand Forecasting – Single Page App
   ========================================================= */

const API = window.APP_CONFIG?.API_URL ?? '/api/1.0';

// ------------------------------------------------------------------ state
let _token = localStorage.getItem('token') || null;
let _user  = JSON.parse(localStorage.getItem('user') || 'null');
let _currentJobId = null;
let _pollTimer = null;

// ------------------------------------------------------------------ http helpers
async function http(method, path, body, isForm = false) {
  const headers = {};
  if (_token) headers['Authorization'] = `Bearer ${_token}`;
  if (!isForm && body) headers['Content-Type'] = 'application/json';

  const res = await fetch(`${API}${path}`, {
    method,
    headers,
    body: isForm ? body : (body ? JSON.stringify(body) : undefined),
  });

  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.detail || res.statusText), { status: res.status, data });
  return data;
}

const get  = (path)               => http('GET', path);
const post = (path, body, isForm) => http('POST', path, body, isForm);

// ------------------------------------------------------------------ router
const PAGES = ['home', 'login', 'signup', 'dashboard', 'forecast', 'history'];

function showPage(name) {
  PAGES.forEach(p => {
    const el = document.getElementById(`page-${p}`);
    if (el) el.classList.toggle('hidden', p !== name);
  });
  updateNav();
}

function updateNav() {
  document.querySelectorAll('.auth-only') .forEach(el => el.classList.toggle('hidden', !_token));
  document.querySelectorAll('.guest-only').forEach(el => el.classList.toggle('hidden', !!_token));
}

function navigate(hash) {
  const page = (hash || '#/home').replace('#/', '');
  if (!_token && ['dashboard', 'forecast', 'history'].includes(page)) {
    showPage('login');
    return;
  }
  showPage(page);
  if (page === 'dashboard') loadDashboard();
  if (page === 'history')   loadHistory();
}

window.addEventListener('hashchange', () => navigate(location.hash));
window.addEventListener('DOMContentLoaded', () => {
  navigate(location.hash);
  document.getElementById('btnLogout')  .addEventListener('click', logout);
  document.getElementById('btnPoll')    .addEventListener('click', () => pollJob(_currentJobId));
  document.getElementById('btnProcess') .addEventListener('click', processJob);
  document.getElementById('btnDownload').addEventListener('click', downloadResult);
  setupLoginForm();
  setupSignupForm();
  setupDepositForm();
  setupUploadForm();
});

// ------------------------------------------------------------------ auth
function logout() {
  _token = null; _user = null;
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  clearInterval(_pollTimer);
  location.hash = '#/home';
}

function setupLoginForm() {
  document.getElementById('formLogin').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('loginError');
    try {
      const data = await post('/auth/signin', {
        login:    document.getElementById('loginLogin').value.trim(),
        password: document.getElementById('loginPassword').value,
      });
      _token = data.access_token;
      _user  = { id: data.user_id, login: data.login, display_name: data.display_name };
      localStorage.setItem('token', _token);
      localStorage.setItem('user', JSON.stringify(_user));
      errEl.classList.add('hidden');
      location.hash = '#/dashboard';
    } catch (err) {
      showMsg(errEl, err.message, 'error');
    }
  });
}

function setupSignupForm() {
  document.getElementById('formSignup').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('signupError');
    try {
      await post('/auth/signup', {
        login:        document.getElementById('signupLogin').value.trim(),
        email:        document.getElementById('signupEmail').value.trim(),
        display_name: document.getElementById('signupName').value.trim(),
        password:     document.getElementById('signupPassword').value,
      });
      errEl.classList.add('hidden');
      location.hash = '#/login';
    } catch (err) {
      showMsg(errEl, err.message, 'error');
    }
  });
}

// ------------------------------------------------------------------ dashboard
async function loadDashboard() {
  if (!_user) return;
  document.getElementById('dashName') .textContent = _user.display_name ?? '—';
  document.getElementById('dashLogin').textContent = _user.login ?? '—';
  try {
    const me  = await get('/auth/me');
    const bal = await get(`/balance/${me.id}`);
    document.getElementById('dashEmail')  .textContent = me.email;
    document.getElementById('dashBalance').textContent = bal.balance.toFixed(2);
  } catch {}
}

function setupDepositForm() {
  document.getElementById('formDeposit').addEventListener('submit', async (e) => {
    e.preventDefault();
    const msgEl  = document.getElementById('depositMsg');
    const amount = parseFloat(document.getElementById('depositAmount').value);
    try {
      const me = await get('/auth/me');
      await post('/balance/deposit', { user_id: me.id, amount });
      const bal = await get(`/balance/${me.id}`);
      document.getElementById('dashBalance').textContent = bal.balance.toFixed(2);
      showMsg(msgEl, `Пополнено. Баланс: ${bal.balance.toFixed(2)} кр.`, 'success');
    } catch (err) {
      showMsg(msgEl, err.message, 'error');
    }
  });
}

// ------------------------------------------------------------------ forecast
function setupUploadForm() {
  document.getElementById('formUpload').addEventListener('submit', async (e) => {
    e.preventDefault();
    const msgEl     = document.getElementById('uploadMsg');
    const fileInput = document.getElementById('csvFile');
    const horizon   = parseInt(document.getElementById('horizon').value, 10);

    if (!fileInput.files.length) { showMsg(msgEl, 'Выберите CSV-файл', 'error'); return; }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
      showMsg(msgEl, 'Загрузка...', 'info');
      const data = await post(`/forecast/upload?horizon=${horizon}`, formData, true);
      _currentJobId = data.job_id;
      showJobCard(data);
      showMsg(msgEl, `Задача создана (ID: ${data.job_id})`, 'success');
    } catch (err) {
      showMsg(msgEl, err.message, 'error');
    }
  });
}

function showJobCard(job) {
  const card = document.getElementById('jobCard');
  card.classList.remove('hidden');
  document.getElementById('jobId')     .textContent = job.job_id;
  document.getElementById('jobStatus') .textContent = job.status;
  document.getElementById('jobStatus') .className   = `badge badge--${job.status}`;
  document.getElementById('jobHorizon').textContent = job.horizon;
  document.getElementById('jobResultSection').classList.add('hidden');
  document.getElementById('btnProcess') .classList.toggle('hidden', job.status !== 'pending');
  document.getElementById('btnDownload').classList.toggle('hidden', job.status !== 'completed');
}

async function processJob() {
  if (!_currentJobId) return;
  const msgEl = document.getElementById('jobMsg');
  try {
    await post(`/forecast/job/${_currentJobId}/process`);
    showMsg(msgEl, 'Задача отправлена в обработку. Обновление каждые 3 сек...', 'info');
    document.getElementById('btnProcess').classList.add('hidden');
    startPolling(_currentJobId);
  } catch (err) {
    showMsg(msgEl, err.message, 'error');
  }
}

function startPolling(jobId) {
  clearInterval(_pollTimer);
  _pollTimer = setInterval(() => pollJob(jobId), 3000);
}

async function pollJob(jobId) {
  if (!jobId) return;
  try {
    const job = await get(`/forecast/job/${jobId}`);
    document.getElementById('jobStatus').textContent = job.status;
    document.getElementById('jobStatus').className   = `badge badge--${job.status}`;

    if (job.status === 'completed') {
      clearInterval(_pollTimer);
      document.getElementById('btnDownload').classList.remove('hidden');
      if (job.result) {
        document.getElementById('jobResultSection').classList.remove('hidden');
        document.getElementById('jobSeries').textContent = job.result.n_series ?? '—';
      }
      showMsg(document.getElementById('jobMsg'), 'Прогноз готов! Скачайте результат.', 'success');
    } else if (job.status === 'failed') {
      clearInterval(_pollTimer);
      showMsg(document.getElementById('jobMsg'), 'Задача завершилась с ошибкой.', 'error');
    }
  } catch {}
}

async function downloadResult() {
  if (!_currentJobId) return;
  const msgEl = document.getElementById('jobMsg');
  try {
    const res  = await fetch(`${API}/forecast/job/${_currentJobId}/download`, {
      headers: { Authorization: `Bearer ${_token}` },
    });
    if (!res.ok) { showMsg(msgEl, 'Ошибка скачивания', 'error'); return; }
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = Object.assign(document.createElement('a'), {
      href:     url,
      download: `forecast_${_currentJobId}.csv`,
    });
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
  } catch (err) {
    showMsg(msgEl, err.message, 'error');
  }
}

// ------------------------------------------------------------------ history
async function loadHistory() {
  const tbody = document.getElementById('historyBody');
  tbody.innerHTML = '<tr><td colspan="8" class="muted">Загрузка...</td></tr>';
  try {
    const jobs = await get('/forecast/jobs');
    if (!jobs.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="muted">Задач ещё нет</td></tr>';
      return;
    }
    tbody.innerHTML = jobs.map(j => {
      const actions = j.status === 'completed'
        ? `<button class="btn btn--sm" onclick="downloadJobResult('${j.job_id}')">Скачать</button>`
        : j.status === 'pending'
        ? `<button class="btn btn--sm btn--primary" onclick="processJobById('${j.job_id}')">Запустить</button>`
        : '—';
      return `<tr>
        <td>${j.job_id}</td>
        <td><span class="badge badge--${j.status}">${j.status}</span></td>
        <td>${j.horizon}</td>
        <td>${(j.cost ?? 0).toFixed(2)}</td>
        <td>${new Date(j.created_at).toLocaleString('ru')}</td>
        <td>${actions}</td>
      </tr>`;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="alert alert--error">${err.message}</td></tr>`;
  }
}

window.downloadJobResult = async function(jobId) {
  const res  = await fetch(`${API}/forecast/job/${jobId}/download`, {
    headers: { Authorization: `Bearer ${_token}` },
  });
  if (!res.ok) { alert('Ошибка скачивания'); return; }
  const blob = await res.blob();
  const url  = URL.createObjectURL(blob);
  const a    = Object.assign(document.createElement('a'), { href: url, download: `forecast_${jobId}.csv` });
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
};

window.processJobById = async function(jobId) {
  try {
    await post(`/forecast/job/${jobId}/process`);
    loadHistory();
  } catch (err) { alert(err.message); }
};

// ------------------------------------------------------------------ utils
function showMsg(el, text, type = 'info') {
  el.textContent = text;
  el.className   = `alert alert--${type}`;
  el.classList.remove('hidden');
}
