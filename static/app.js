(() => {
  const form = document.getElementById('article-form');
  const pasteBox = document.getElementById('paste-image');
  const fileInput = document.getElementById('image-file');
  const imageUrl = document.getElementById('image-url');
  const slugInput = document.getElementById('slug');
  const status = document.getElementById('upload-status');
  const submitLabel = document.getElementById('submit-label');
  const modeInputs = [...document.querySelectorAll('input[name="mode"]')];
  const manualOnly = [...document.querySelectorAll('.manual-only')];

  function currentMode() {
    return modeInputs.find(x => x.checked)?.value || 'generate';
  }

  function updateMode() {
    const manual = currentMode() === 'paste';
    manualOnly.forEach(el => el.style.display = manual ? '' : 'none');
    if (submitLabel) submitLabel.textContent = manual ? 'Validate & Review →' : 'Generate & Review →';
  }

  async function uploadPastedFile(file) {
    if (!file || !file.type.startsWith('image/')) return;
    status.textContent = 'Uploading pasted image…';
    pasteBox?.classList.add('busy');

    const data = new FormData();
    const ext = (file.type.split('/')[1] || 'png').replace('jpeg', 'jpg');
    const safeName = file.name && file.name !== 'image.png' ? file.name : `pasted-image.${ext}`;
    data.append('image', file, safeName);
    data.append('slug', slugInput?.value || 'guide');

    try {
      const res = await fetch('/upload-image', { method: 'POST', body: data });
      const payload = await res.json();
      if (!res.ok || !payload.ok) throw new Error(payload.error || 'Upload failed');
      imageUrl.value = payload.url;
      status.textContent = `Attached: ${payload.url}`;
      pasteBox?.classList.add('has-image');
    } catch (err) {
      status.textContent = `Image upload failed: ${err.message}`;
      pasteBox?.classList.remove('has-image');
    } finally {
      pasteBox?.classList.remove('busy');
    }
  }

  function pastedImageFromClipboard(event) {
    const items = [...(event.clipboardData?.items || [])];
    const image = items.find(item => item.type.startsWith('image/'));
    return image?.getAsFile() || null;
  }

  document.addEventListener('paste', event => {
    const file = pastedImageFromClipboard(event);
    if (file) {
      event.preventDefault();
      uploadPastedFile(file);
    }
  });

  pasteBox?.addEventListener('dragover', event => {
    event.preventDefault();
    pasteBox.classList.add('dragging');
  });

  pasteBox?.addEventListener('dragleave', () => pasteBox.classList.remove('dragging'));

  pasteBox?.addEventListener('drop', event => {
    event.preventDefault();
    pasteBox.classList.remove('dragging');
    const file = [...event.dataTransfer.files].find(f => f.type.startsWith('image/'));
    if (file) uploadPastedFile(file);
  });

  pasteBox?.addEventListener('click', () => fileInput?.click());

  fileInput?.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    if (file) status.textContent = `Selected: ${file.name} — it will upload when you review.`;
  });

  modeInputs.forEach(input => input.addEventListener('change', updateMode));
  updateMode();
})();
