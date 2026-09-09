(() => {
  const form = document.getElementById('article-form');
  const pasteBox = document.getElementById('paste-image');
  const fileInput = document.getElementById('image-file');
  const imageUrl = document.getElementById('image-url');
  const slugInput = document.getElementById('slug');
  const titleInput = document.getElementById('title');
  const trendContext = document.getElementById('trend-context');
  const status = document.getElementById('upload-status');
  const submitLabel = document.getElementById('submit-label');
  const flowNote = document.getElementById('flow-note');
  const modeInputs = [...document.querySelectorAll('input[name="mode"]')];
  const manualOnly = [...document.querySelectorAll('.manual-only')];
  const generateOnly = [...document.querySelectorAll('.generate-only')];

  function currentMode() {
    return modeInputs.find(x => x.checked)?.value || 'generate';
  }

  function updateMode() {
    const manual = currentMode() === 'paste';
    manualOnly.forEach(el => el.style.display = manual ? '' : 'none');
    generateOnly.forEach(el => el.style.display = manual ? 'none' : '');
    if (submitLabel) submitLabel.textContent = manual ? 'Validate & Review →' : 'Generate & Review →';
    if (flowNote) {
      flowNote.textContent = manual
        ? 'Your article is checked first. Nothing publishes until you review it.'
        : 'Gemini writes first. Nothing publishes until you review it.';
    }
  }

  function cleanTopicText(value) {
    return (value || '')
      .replace(/^\*\*|\*\*$/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function splitTopicAndExplanation() {
    if (currentMode() !== 'generate' || !titleInput) return;

    const raw = cleanTopicText(titleInput.value);
    if (!raw) return;

    const colon = raw.indexOf(':');
    if (colon < 0) return;

    const left = cleanTopicText(raw.slice(0, colon));
    const right = cleanTopicText(raw.slice(colon + 1));
    const leftWords = left.split(/\s+/).filter(Boolean).length;

    // Only auto-split when the user has clearly pasted a topic + explanatory sentence,
    // not a normal short SEO title containing a colon.
    const looksLikeTopicBrief =
      right.length >= 55 &&
      left.length >= 8 &&
      left.length <= 90 &&
      leftWords <= 14;

    if (!looksLikeTopicBrief) return;

    titleInput.value = left.replace(/[.:;,-]+$/, '').trim();
    if (trendContext) {
      const existing = trendContext.value.trim();
      trendContext.value = existing ? `${existing}\n${right}` : right;
    }
  }

  async function uploadPastedFile(file) {
    if (!file || !file.type.startsWith('image/')) return;
    status.textContent = 'Uploading pasted image…';
    pasteBox?.classList.add('busy');

    const data = new FormData();
    const ext = (file.type.split('/')[1] || 'png').replace('jpeg', 'jpg');
    const safeName = file.name && file.name !== 'image.png' ? file.name : `pasted-image.${ext}`;
    data.append('image', file, safeName);
    data.append('slug', slugInput?.value || titleInput?.value || 'guide');

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

  form?.addEventListener('submit', () => {
    splitTopicAndExplanation();
  });

  modeInputs.forEach(input => input.addEventListener('change', updateMode));
  updateMode();
})();
