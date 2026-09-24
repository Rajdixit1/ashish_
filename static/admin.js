const token = localStorage.getItem('hs_session');
const rows = document.querySelector('#client-rows');
const message = document.querySelector('#admin-message');
const withdrawalRows = document.querySelector('#withdrawal-rows');
const withdrawalMessage = document.querySelector('#withdrawal-admin-message');

function formatDate(value) {
  return new Date(value).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
}

async function loadClients() {
  if (!token) {
    window.location.href = '/';
    return;
  }
  message.textContent = 'Loading client records...';
  const response = await fetch('/api/admin/clients', { headers: { Authorization: `Bearer ${token}` } });
  if (response.status === 401) {
    localStorage.removeItem('hs_session');
    window.location.href = '/';
    return;
  }
  const result = await response.json();
  rows.innerHTML = result.clients.map((client) => `<tr><td><strong>${client.name}</strong><small>HS-${String(client.id).padStart(4, '0')}</small></td><td>${client.mobile}</td><td><span class="status status-${client.status.toLowerCase()}">${client.status}</span></td><td>Rs ${client.balance}</td><td>${client.tasks_completed}</td><td>${formatDate(client.joined_at)}</td></tr>`).join('');
  document.querySelector('#total-clients').textContent = result.clients.length;
  document.querySelector('#active-clients').textContent = result.clients.filter((client) => client.status === 'Active').length;
  document.querySelector('#pending-clients').textContent = result.clients.filter((client) => client.status === 'Pending').length;
  document.querySelector('#last-updated').textContent = `Updated ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
  message.textContent = result.clients.length ? '' : 'No client registrations yet.';
  await loadWithdrawals();
}

async function loadWithdrawals() {
  const response = await fetch('/api/admin/withdrawals', { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) return;
  const result = await response.json();
  withdrawalRows.innerHTML = result.withdrawals.length ? result.withdrawals.map((item) => `<tr><td><strong>${item.client_name}</strong><small>${item.client_mobile}</small></td><td>Rs ${item.amount}</td><td>${item.bank_details}</td><td><span class="status status-${item.status.toLowerCase()}">${item.status}</span></td><td>${item.status === 'Pending' ? `<button class="table-action" data-withdrawal-id="${item.id}">Mark paid</button>` : '<span class="completed-label">Paid</span>'}</td></tr>`).join('') : '<tr><td colspan="5">No withdrawal tasks yet.</td></tr>';
  document.querySelectorAll('[data-withdrawal-id]').forEach((button) => button.addEventListener('click', async () => {
    button.disabled = true;
    const complete = await fetch(`/api/admin/withdrawals/${button.dataset.withdrawalId}/complete`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } });
    if (!complete.ok) withdrawalMessage.textContent = (await complete.json()).detail || 'Could not update payment.';
    else withdrawalMessage.textContent = 'Payment marked completed.';
    await loadClients();
  }));
}

document.querySelector('#task-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const response = await fetch('/api/admin/tasks', { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: new FormData(event.currentTarget) });
  const result = await response.json();
  document.querySelector('#task-message').textContent = response.ok ? result.message : result.detail;
  if (response.ok) event.currentTarget.reset();
});

document.querySelector('#refresh-clients').addEventListener('click', loadClients);
loadClients().catch(() => { message.textContent = 'Could not load client records.'; });
