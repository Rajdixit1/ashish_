const token = localStorage.getItem('hs_session');
const headers = { Authorization: `Bearer ${token}` };
const taskList = document.querySelector('#task-list');
const withdrawalList = document.querySelector('#withdrawal-list');
const withdrawalMessage = document.querySelector('#withdrawal-message');

function money(value) { return `Rs ${Number(value).toLocaleString('en-IN')}`; }

function renderTasks(tasks) {
  taskList.innerHTML = tasks.map((task) => `<article class="dashboard-task task-${task.progress.toLowerCase()}"><span class="task-order">${String(task.sort_order).padStart(2, '0')}</span><div><h3>${task.title}</h3><p>${task.description}</p><span class="task-state">${task.progress}</span></div><strong>${money(task.reward)}</strong>${task.progress === 'Current' ? `<button class="button button-primary task-action" data-task-id="${task.id}">Complete</button>` : ''}</article>`).join('');
  document.querySelectorAll('.task-action').forEach((button) => button.addEventListener('click', async () => {
    button.disabled = true;
    const response = await fetch(`/api/tasks/${button.dataset.taskId}/complete`, { method: 'POST', headers });
    const result = await response.json();
    if (!response.ok) alert(result.detail || 'Task could not be completed.');
    await loadDashboard();
  }));
}

function renderWithdrawals(withdrawals) {
  withdrawalList.innerHTML = withdrawals.length ? withdrawals.map((item) => `<article class="withdrawal-item"><span class="withdrawal-icon">&#8593;</span><div><strong>Withdrawal task #${item.id}</strong><small>${item.bank_details}</small><small>${new Date(item.created_at).toLocaleString()}</small></div><span class="withdrawal-amount">${money(item.amount)}<em class="status status-${item.status.toLowerCase()}">${item.status}</em></span></article>`).join('') : '<p class="empty-state">No withdrawal tasks yet.</p>';
}

async function loadDashboard() {
  if (!token) { window.location.href = '/'; return; }
  const response = await fetch('/api/dashboard', { headers });
  if (response.status === 401) { localStorage.removeItem('hs_session'); window.location.href = '/'; return; }
  const data = await response.json();
  document.querySelector('#client-name').textContent = data.client.name;
  document.querySelector('#balance').textContent = Number(data.client.balance).toLocaleString('en-IN');
  document.querySelector('#admin-contact').textContent = `${data.admin_name} | ${data.admin_mobile}`;
  renderTasks(data.tasks);
  renderWithdrawals(data.withdrawals);
}

document.querySelector('#withdrawal-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const response = await fetch('/api/withdrawals', { method: 'POST', headers, body: new FormData(form) });
  const result = await response.json();
  withdrawalMessage.textContent = response.ok ? result.message : result.detail;
  withdrawalMessage.classList.toggle('error', !response.ok);
  if (response.ok) { form.reset(); await loadDashboard(); }
});

document.querySelector('#logout').addEventListener('click', () => { localStorage.removeItem('hs_session'); window.location.href = '/'; });
loadDashboard().catch(() => { withdrawalMessage.textContent = 'Dashboard could not load.'; });
