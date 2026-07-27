import { upload } from 'https://esm.sh/@vercel/blob@2.3.2/client';

const allowedExtensions = new Set([
  'mp4', 'mov', 'mkv', 'avi', 'webm', 'm4v',
  'mp3', 'wav', 'm4a', 'aac', 'ogg', 'flac',
  'png', 'jpg', 'jpeg', 'webp', 'gif', 'svg',
  'txt', 'md', 'srt', 'pdf',
]);

const sanitizeName = (name) => {
  const cleaned = String(name || 'arquivo')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return cleaned || 'arquivo';
};

const fileExtension = (name) => {
  const value = String(name || '');
  const position = value.lastIndexOf('.');
  return position >= 0 ? value.slice(position + 1).toLowerCase() : '';
};

const addHidden = (form, name, value) => {
  const existing = form.querySelector(`input[type="hidden"][name="${name}"]`);
  if (existing) {
    existing.value = String(value ?? '');
    return existing;
  }
  const input = document.createElement('input');
  input.type = 'hidden';
  input.name = name;
  input.value = String(value ?? '');
  form.appendChild(input);
  return input;
};

const getProgressBox = (form) => {
  let box = form.querySelector('[data-cloud-upload-progress]');
  if (box) return box;
  box = document.createElement('div');
  box.className = 'cloud-upload-progress';
  box.dataset.cloudUploadProgress = 'true';
  box.innerHTML = `
    <div class="cloud-upload-progress-head">
      <strong>☁️ Enviando para a nuvem</strong>
      <span data-cloud-progress-label>Preparando arquivos...</span>
    </div>
    <div class="cloud-upload-progress-track"><i data-cloud-progress-bar></i></div>
  `;
  form.appendChild(box);
  return box;
};

const setProgress = (box, percentage, label) => {
  const value = Math.max(0, Math.min(100, Number(percentage) || 0));
  const bar = box.querySelector('[data-cloud-progress-bar]');
  const text = box.querySelector('[data-cloud-progress-label]');
  if (bar) bar.style.width = `${value}%`;
  if (text) text.textContent = label || `${Math.round(value)}%`;
};

let cachedAuth = null;
const getUploadAuth = async () => {
  if (cachedAuth && cachedAuth.expiresAt > Date.now() + 30_000) return cachedAuth.token;
  const response = await fetch('/api/blob-upload-auth', {
    method: 'GET',
    headers: { Accept: 'application/json' },
    credentials: 'same-origin',
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.token) {
    throw new Error(result.message || 'Não foi possível autorizar o envio dos arquivos.');
  }
  cachedAuth = {
    token: result.token,
    expiresAt: Date.now() + (Number(result.expires_in || 600) * 1000),
  };
  return cachedAuth.token;
};

const nativeSubmit = (form) => HTMLFormElement.prototype.submit.call(form);

const uploadOne = async ({ file, authToken, onProgress }) => {
  const extension = fileExtension(file.name);
  if (!allowedExtensions.has(extension)) {
    throw new Error(`Formato não permitido: ${file.name}`);
  }
  if (!file.size) {
    throw new Error(`O arquivo ${file.name} está vazio.`);
  }

  const randomId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const pathname = `plannerx/${new Date().toISOString().slice(0, 10)}/${randomId}-${sanitizeName(file.name)}`;
  const contentType = file.type || 'application/octet-stream';

  const blob = await upload(pathname, file, {
    access: 'public',
    handleUploadUrl: '/api/blob-upload',
    clientPayload: JSON.stringify({ auth: authToken, contentType }),
    multipart: file.size > 4_000_000,
    onUploadProgress(progress) {
      const percentage = Number(progress?.percentage ?? 0);
      onProgress(percentage);
    },
  });

  return {
    original_name: file.name,
    stored_name: blob.url,
    mime_type: contentType,
    size_bytes: file.size,
  };
};

const prepareCloudUploads = async (form) => {
  const fileInputs = [...form.querySelectorAll('input[type="file"]')]
    .filter((input) => input.files && input.files.length > 0 && !input.disabled);
  if (!fileInputs.length) return false;

  const selected = fileInputs.flatMap((input) => [...input.files].map((file) => ({ input, file })));
  const totalBytes = selected.reduce((sum, item) => sum + Math.max(1, item.file.size), 0);
  let completedBytes = 0;
  const progressBox = getProgressBox(form);
  progressBox.hidden = false;
  setProgress(progressBox, 1, `Preparando ${selected.length} arquivo(s)...`);

  const submitButtons = [...form.querySelectorAll('button[type="submit"], input[type="submit"]')];
  submitButtons.forEach((button) => { button.disabled = true; });
  form.classList.add('is-cloud-uploading');

  try {
    const authToken = await getUploadAuth();
    const grouped = new Map();

    for (let index = 0; index < selected.length; index += 1) {
      const { input, file } = selected[index];
      const itemStart = completedBytes;
      setProgress(progressBox, (completedBytes / totalBytes) * 100, `Enviando ${index + 1}/${selected.length}: ${file.name}`);

      const uploaded = await uploadOne({
        file,
        authToken,
        onProgress(filePercent) {
          const currentBytes = file.size * (filePercent / 100);
          const overall = ((itemStart + currentBytes) / totalBytes) * 100;
          setProgress(progressBox, overall, `Enviando ${index + 1}/${selected.length}: ${Math.round(filePercent)}%`);
        },
      });
      completedBytes += Math.max(1, file.size);
      if (!grouped.has(input)) grouped.set(input, []);
      grouped.get(input).push(uploaded);
    }

    for (const [input, uploads] of grouped.entries()) {
      if (input.name === 'files') {
        addHidden(form, 'cloud_files_json', JSON.stringify(uploads));
      } else if (input.name === 'image') {
        const item = uploads[0];
        addHidden(form, 'image_cloud_url', item.stored_name);
        addHidden(form, 'image_cloud_name', item.original_name);
        addHidden(form, 'image_cloud_mime', item.mime_type);
        addHidden(form, 'image_cloud_size', item.size_bytes);
      } else if (input.name === 'cover_image') {
        const item = uploads[0];
        addHidden(form, 'cover_cloud_url', item.stored_name);
        addHidden(form, 'cover_cloud_name', item.original_name);
        addHidden(form, 'cover_cloud_mime', item.mime_type);
        addHidden(form, 'cover_cloud_size', item.size_bytes);
      }
      input.disabled = true;
    }

    setProgress(progressBox, 100, 'Upload concluído. Salvando no PlannerX...');
    return true;
  } catch (error) {
    setProgress(progressBox, 0, 'Falha no upload');
    window.alert(error?.message || 'Não foi possível enviar os arquivos para a nuvem.');
    submitButtons.forEach((button) => { button.disabled = false; });
    form.classList.remove('is-cloud-uploading');
    return null;
  }
};

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('form[data-cloud-upload-form]').forEach((form) => {
    form.addEventListener('submit', async (event) => {
      if (form.dataset.cloudUploadComplete === 'true') return;
      const hasFiles = [...form.querySelectorAll('input[type="file"]')]
        .some((input) => input.files && input.files.length > 0 && !input.disabled);
      if (!hasFiles) return;

      event.preventDefault();
      if (form.dataset.cloudUploading === 'true') return;
      form.dataset.cloudUploading = 'true';
      const result = await prepareCloudUploads(form);
      if (result === true) {
        form.dataset.cloudUploadComplete = 'true';
        nativeSubmit(form);
      } else {
        form.dataset.cloudUploading = 'false';
      }
    });
  });
});
