let currentSlug = null;
let currentDraft = false;
let viewMode = 'email';
let contactCount = null;
let deploymentLive = false;

// Auth status
function refreshAuthStatus() {
  fetch('/api/auth-status').then(r => r.json()).then(d => {
    const dot = document.getElementById('auth-dot');
    const label = document.getElementById('auth-label');
    const connectBtn = document.getElementById('auth-btn');
    const disconnectBtn = document.getElementById('auth-disconnect');
    if (d.needs_credentials) {
      dot.className = 'auth-dot err';
      label.textContent = 'No credentials.json';
      connectBtn.style.display = 'none';
      disconnectBtn.style.display = 'none';
    } else if (d.connected) {
      dot.className = 'auth-dot ok';
      label.textContent = 'Gmail connected';
      connectBtn.style.display = 'none';
      disconnectBtn.style.display = '';
    } else {
      dot.className = 'auth-dot err';
      label.textContent = 'Not connected';
      connectBtn.style.display = '';
      disconnectBtn.style.display = 'none';
    }
  });
}

function disconnect() {
  fetch('/oauth/disconnect', { method: 'POST' }).then(() => refreshAuthStatus());
}

refreshAuthStatus();

// Dark mode
function applyTheme(dark) {
  document.body.classList.toggle('dark', dark);
  document.getElementById('btn-theme').textContent = dark ? '☀️' : '🌙';
}
function toggleTheme() {
  const dark = !document.body.classList.contains('dark');
  localStorage.setItem('theme', dark ? 'dark' : 'light');
  applyTheme(dark);
}
applyTheme(localStorage.getItem('theme') === 'dark');

// Load editions on startup
function renderEditionList(editions, selectSlug) {
  const list = document.getElementById('edition-list');
  if (!editions.length) {
    list.innerHTML = '<div style="padding:16px;color:#aaa;font-size:13px;">No editions found.</div>';
    return;
  }
  list.innerHTML = editions.map(e => `
    <div class="edition-item" id="item-${e.slug}" onclick="selectEdition(${JSON.stringify(e).replace(/"/g, '&quot;')})">
      <div class="edition-title">${e.title}</div>
      <div class="edition-meta">
        <span>${e.date}</span>
        <span class="badge ${e.draft ? 'badge-draft' : 'badge-live'}" id="badge-${e.slug}">
          ${e.draft ? 'Draft' : 'Live'}
        </span>
      </div>
    </div>
  `).join('');
  if (selectSlug) {
    const match = editions.find(e => e.slug === selectSlug);
    if (match) selectEdition(match);
  }
}

function loadEditions(selectSlug) {
  return fetch('/api/editions').then(r => r.json()).then(editions => {
    renderEditionList(editions, selectSlug);
    return editions;
  });
}

loadEditions().then(editions => {
  // Pre-fetch contact count once
  fetch('/api/contacts/count').then(r => r.json()).then(d => { contactCount = d.count; });

  // Restore state from URL hash
  const [hashSlug, hashView] = location.hash.slice(1).split('/');
  if (hashSlug) {
    const match = editions.find(e => e.slug === hashSlug);
    if (match) selectEdition(match, hashView || 'email');
  }
});

function updateHash() {
  const hash = viewMode === 'email' ? currentSlug : `${currentSlug}/web`;
  history.replaceState(null, '', `#${hash}`);
}

function selectEdition(e, view = 'email') {
  // Deselect previous
  if (currentSlug) {
    document.getElementById(`item-${currentSlug}`)?.classList.remove('active');
  }
  currentSlug = e.slug;
  currentDraft = e.draft;
  viewMode = view;

  document.getElementById(`item-${e.slug}`).classList.add('active');
  document.getElementById('toolbar-title').textContent = e.title;
  document.getElementById('toolbar-title').classList.remove('empty');

  // Show controls
  ['btn-email','btn-web','btn-draft'].forEach(id => {
    document.getElementById(id).style.display = '';
  });
  document.getElementById('btn-email').classList.toggle('active', view === 'email');
  document.getElementById('btn-web').classList.toggle('active', view === 'web');
  document.getElementById('empty-state').style.display = 'none';
  document.getElementById('preview-frame').style.display = '';
  document.getElementById('action-bar').style.display = '';

  // Draft toggle button label
  updateDraftButton();

  // Obsidian link
  document.getElementById('btn-obsidian').href = `obsidian://open?path=${encodeURIComponent(e.path)}`;

  updateHash();
  loadPreview();
  checkDeployment();
}

function setView(mode) {
  viewMode = mode;
  document.getElementById('btn-email').classList.toggle('active', mode === 'email');
  document.getElementById('btn-web').classList.toggle('active', mode === 'web');
  updateHash();
  loadPreview();
}

function loadPreview() {
  const frame = document.getElementById('preview-frame');
  frame.src = `/preview/${currentSlug}/${viewMode}`;
}

function updateDraftButton() {
  const btn = document.getElementById('btn-draft');
  btn.textContent = currentDraft ? 'Mark as Live' : 'Mark as Draft';
}

function toggleDraft() {
  fetch(`/api/toggle-draft/${currentSlug}`, { method: 'POST' })
    .then(r => r.json())
    .then(d => {
      currentDraft = d.draft;
      updateDraftButton();
      // Update badge in sidebar
      const badge = document.getElementById(`badge-${currentSlug}`);
      badge.textContent = d.draft ? 'Draft' : 'Live';
      badge.className = `badge ${d.draft ? 'badge-draft' : 'badge-live'}`;
      updateSendButtons();
    });
}

function checkDeployment() {
  const statusEl = document.getElementById('deploy-status');
  statusEl.style.display = '';
  statusEl.className = 'status-msg info';
  statusEl.textContent = 'Checking deployment…';
  updateSendButtons();

  fetch(`/api/check-deployment/${currentSlug}`)
    .then(r => r.json())
    .then(d => {
      deploymentLive = d.live;
      if (d.live) {
        statusEl.className = 'status-msg ok';
        statusEl.textContent = 'Live ✓';
      } else {
        statusEl.className = 'status-msg warn';
        statusEl.textContent = d.reason ? `Not live: ${d.reason}` : 'Not deployed yet';
      }
      updateSendButtons();
    });
}

function updateSendButtons() {
  const canSend = !currentDraft && deploymentLive;
  document.getElementById('btn-publish').disabled = currentDraft;
  document.getElementById('btn-test').disabled = false;
  document.getElementById('btn-send').disabled = !canSend;
}

function doPublish() {
  const btn = document.getElementById('btn-publish');
  btn.disabled = true;
  btn.textContent = 'Publishing…';
  fetch(`/api/publish/${currentSlug}`, { method: 'POST' })
    .then(r => r.json())
    .then(d => {
      btn.textContent = 'Publish';
      updateSendButtons();
      const statusEl = document.getElementById('deploy-status');
      statusEl.style.display = '';
      if (d.ok) {
        statusEl.className = 'status-msg ok';
        statusEl.textContent = 'Published ✓';
      } else {
        statusEl.className = 'status-msg err';
        statusEl.textContent = `Publish failed: ${d.error}`;
      }
    });
}

function testSend() {
  const listEl = document.getElementById('test-contact-list');
  listEl.innerHTML = '<span style="color:var(--text-secondary)">Loading…</span>';
  document.getElementById('test-modal').classList.add('visible');
  fetch('/api/contacts').then(r => r.json()).then(d => {
    if (d.error) { listEl.innerHTML = `<span style="color:#f08080">${d.error}</span>`; return; }
    const contacts = d.contacts;
    listEl.innerHTML = '';
    const updateCount = () => {
      const n = listEl.querySelectorAll('input[type=checkbox]:checked').length;
      document.getElementById('test-selection-count').textContent = `(${n} selected)`;
    };
    const addRow = (html, checked) => {
      const label = document.createElement('label');
      label.style.cssText = 'display:flex;align-items:center;gap:8px;cursor:pointer';
      label.innerHTML = html;
      label.querySelector('input').checked = checked;
      label.querySelector('input').addEventListener('change', updateCount);
      listEl.appendChild(label);
    };
    // "myself" option always first
    addRow('<input type="checkbox" data-self="1"> <span>Myself</span>', true);
    contacts.forEach(c => {
      addRow(`<input type="checkbox" data-name="${c.name}" data-email="${c.email}"> <span>${c.name || c.email} <span style="color:var(--text-secondary);font-size:11px">${c.name ? '&lt;' + c.email + '&gt;' : ''}</span></span>`, false);
    });
    updateCount();
  });
}

function closeTestModal() {
  document.getElementById('test-modal').classList.remove('visible');
}

function doTestSend() {
  const checkboxes = document.querySelectorAll('#test-contact-list input[type=checkbox]:checked');
  const recipients = [];
  checkboxes.forEach(cb => {
    if (cb.dataset.self) return;
    recipients.push({ name: cb.dataset.name, email: cb.dataset.email });
  });
  // Check if "myself" is checked
  const selfCb = document.querySelector('#test-contact-list input[data-self]');
  if (selfCb && selfCb.checked) recipients.unshift({ name: 'You', email: '__self__' });

  closeTestModal();
  const btn = document.getElementById('btn-test');
  btn.disabled = true;
  btn.textContent = 'Sending…';
  fetch(`/api/test-send/${currentSlug}`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ recipients })
  }).then(r => r.json()).then(d => {
    btn.textContent = 'Test Send';
    updateSendButtons();
    const statusEl = document.getElementById('deploy-status');
    statusEl.style.display = '';
    if (d.ok) {
      statusEl.className = 'status-msg ok';
      statusEl.textContent = `Test sent to ${d.sent} recipient${d.sent !== 1 ? 's' : ''} ✓`;
    } else {
      statusEl.className = 'status-msg err';
      statusEl.textContent = `Error: ${d.error}`;
    }
  });
}

function confirmSend() {
  const count = contactCount !== null ? contactCount : '?';
  document.getElementById('modal-body').textContent =
    `This will send "${document.getElementById('toolbar-title').textContent}" to ${count} recipient${count !== 1 ? 's' : ''}. This cannot be undone.`;
  document.getElementById('modal').classList.add('visible');
}

function closeModal() {
  document.getElementById('modal').classList.remove('visible');
}

function doSend() {
  closeModal();
  const btn = document.getElementById('btn-send');
  btn.disabled = true;
  btn.textContent = 'Sending…';
  fetch(`/api/send/${currentSlug}`, { method: 'POST' })
    .then(r => r.json())
    .then(d => {
      btn.textContent = 'Send All';
      updateSendButtons();
      const statusEl = document.getElementById('deploy-status');
      statusEl.style.display = '';
      if (d.ok) {
        statusEl.className = d.failed && d.failed.length ? 'status-msg warn' : 'status-msg ok';
        let msg = `Sent to ${d.sent} recipient${d.sent !== 1 ? 's' : ''} ✓`;
        if (d.skipped) msg += `, ${d.skipped} already sent`;
        if (d.failed && d.failed.length) msg += `, ${d.failed.length} failed`;
        statusEl.textContent = msg;
      } else {
        statusEl.className = 'status-msg err';
        statusEl.textContent = `Error: ${d.error}`;
      }
    });
}

// Close modal on overlay click
document.getElementById('modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeModal();
});
document.getElementById('test-modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeTestModal();
});

// Settings
function openSettings() {
  fetch('/api/settings').then(r => r.json()).then(d => {
    document.getElementById('settings-name').value = d.newsletter_name || '';
    document.getElementById('settings-sheet').value = d.has_sheet_id ? '(saved)' : '';
    document.getElementById('settings-modal').classList.add('visible');
  });
}
function closeSettings() {
  document.getElementById('settings-modal').classList.remove('visible');
}
function checkSentLog() {
  const el = document.getElementById('sent-log-result');
  el.style.display = 'block';
  el.textContent = 'Loading…';
  fetch('/api/sent-log').then(r => r.json()).then(d => {
    if (d.error) { el.textContent = `Error: ${d.error}`; return; }
    if (!d.rows || d.rows.length <= 1) { el.textContent = '(no entries yet)'; return; }
    const [header, ...rows] = d.rows;
    el.textContent = [header.join(' | '), ...rows.slice(-10).map(r => r.join(' | '))].join('\n');
    if (rows.length > 10) el.textContent = `(showing last 10 of ${rows.length})\n` + el.textContent;
  });
}
function testContacts() {
  const el = document.getElementById('contacts-test-result');
  el.textContent = 'Checking…';
  fetch('/api/contacts/count').then(r => r.json()).then(d => {
    el.textContent = d.error ? `Error: ${d.error}` : `✓ ${d.count} contact${d.count !== 1 ? 's' : ''} with Send=y`;
  });
}
function saveSettings() {
  const name = document.getElementById('settings-name').value.trim();
  const sheet = document.getElementById('settings-sheet').value.trim();
  const payload = {};
  if (name) payload.newsletter_name = name;
  if (sheet && sheet !== '(saved)') payload.sheet_id = sheet;
  fetch('/api/settings', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) })
    .then(r => r.json()).then(() => closeSettings());
}
document.getElementById('settings-modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeSettings();
});

if (document.body.dataset.unconfigured) openSettings();

// New edition
function openNewEdition() {
  document.getElementById('new-edition-title').value = '';
  document.getElementById('new-edition-error').style.display = 'none';
  document.getElementById('new-edition-modal').classList.add('visible');
  setTimeout(() => document.getElementById('new-edition-title').focus(), 50);
}
function closeNewEdition() {
  document.getElementById('new-edition-modal').classList.remove('visible');
}
function doNewEdition() {
  const title = document.getElementById('new-edition-title').value.trim();
  if (!title) return;
  const errEl = document.getElementById('new-edition-error');
  errEl.style.display = 'none';
  fetch('/api/new-edition', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ title }),
  }).then(r => r.json()).then(d => {
    if (d.error) {
      errEl.textContent = d.error;
      errEl.style.display = '';
      return;
    }
    closeNewEdition();
    loadEditions(d.slug);
  });
}
document.getElementById('new-edition-modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeNewEdition();
});
document.getElementById('new-edition-title').addEventListener('keydown', e => {
  if (e.key === 'Enter') doNewEdition();
  if (e.key === 'Escape') closeNewEdition();
});

// Expose functions used by inline HTML event handlers
Object.assign(window, {
  selectEdition,
  setView,
  toggleDraft,
  toggleTheme,
  disconnect,
  openSettings,
  closeSettings,
  saveSettings,
  testContacts,
  checkSentLog,
  testSend,
  closeTestModal,
  doTestSend,
  confirmSend,
  closeModal,
  doSend,
  doPublish,
  openNewEdition,
  closeNewEdition,
  doNewEdition,
});
