'use strict';
lucide.createIcons();

const errorBox = document.getElementById('error-box');
const errorText = document.getElementById('error-text');
const codeGroup = document.getElementById('code-group');
const codeInput = document.getElementById('code');

document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  errorBox.style.display = 'none';
  try {
    const body = { password: document.getElementById('password').value };
    if (!codeGroup.hidden) body.code = codeInput.value.trim();
    const res = await fetch('api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (res.ok) {
      window.location.href = './';
      return;
    }
    const err = await res.json().catch(() => ({}));
    if (err.mfa && codeGroup.hidden) {
      // the password was right; two-factor sign-in is on, so ask for the code next
      codeGroup.hidden = false;
      codeInput.required = true;
      codeInput.focus();
      return;
    }
    if (err.mfa) {
      codeInput.value = '';
      codeInput.focus();
    }
    errorText.textContent = err.error || 'Login failed';
  } catch (err) {
    errorText.textContent = 'Network error. Please try again.';
  }
  errorBox.style.display = 'flex';
});
