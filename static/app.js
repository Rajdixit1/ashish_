const modalBackdrops = document.querySelectorAll('.modal-backdrop');

function toggleModal(name, isOpen) {
  const modal = document.querySelector(`[data-modal="${name}"]`);
  if (!modal) return;
  modal.hidden = !isOpen;
  document.body.style.overflow = isOpen ? 'hidden' : '';
  if (isOpen) modal.querySelector('input, button')?.focus();
}

function showFormMessage(form, text, isError = false) {
  const message = form.querySelector('.form-message');
  message.textContent = text;
  message.classList.toggle('error', isError);
}

document.querySelectorAll('[data-open-modal]').forEach((button) => {
  button.addEventListener('click', () => toggleModal(button.dataset.openModal, true));
});

document.querySelectorAll('[data-switch-modal]').forEach((button) => {
  button.addEventListener('click', () => {
    toggleModal(button.closest('.modal-backdrop').dataset.modal, false);
    toggleModal(button.dataset.switchModal, true);
  });
});

document.querySelectorAll('.modal-close, [data-close-modal]').forEach((button) => {
  button.addEventListener('click', () => toggleModal(button.closest('.modal-backdrop').dataset.modal, false));
});

modalBackdrops.forEach((backdrop) => {
  backdrop.addEventListener('click', (event) => {
    if (event.target === backdrop) toggleModal(backdrop.dataset.modal, false);
  });
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') modalBackdrops.forEach((backdrop) => toggleModal(backdrop.dataset.modal, false));
});

async function submitAuthForm(form, endpoint) {
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  button.textContent = endpoint === '/api/login' ? 'Logging in...' : 'Creating account...';
  try {
    const response = await fetch(endpoint, { method: 'POST', body: new FormData(form) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Something went wrong.');
    localStorage.setItem('hs_session', result.token);
    showFormMessage(form, result.message);
    setTimeout(() => {
      toggleModal(form.closest('.modal-backdrop').dataset.modal, false);
      if (result.role === 'admin') window.location.href = '/admin';
      if (result.role === 'client') window.location.href = '/dashboard';
    }, 450);
  } catch (error) {
    showFormMessage(form, error.message, true);
  } finally {
    button.disabled = false;
    button.innerHTML = endpoint === '/api/login' ? 'Log in <span aria-hidden="true">&#8594;</span>' : 'Sign up <span aria-hidden="true">&#8594;</span>';
  }
}

document.querySelector('#signup-form').addEventListener('submit', (event) => {
  event.preventDefault();
  submitAuthForm(event.currentTarget, '/api/signup');
});

document.querySelector('#login-form').addEventListener('submit', (event) => {
  event.preventDefault();
  submitAuthForm(event.currentTarget, '/api/login');
});
