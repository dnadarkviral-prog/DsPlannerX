(() => {
  const openModal = (id) => {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
    setTimeout(() => modal.querySelector('input, textarea, select')?.focus(), 80);
  };

  const closeModal = (modal) => {
    if (!modal) return;
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
    if (!document.querySelector('.modal.open')) document.body.classList.remove('modal-open');
  };

  document.querySelectorAll('[data-open-modal]').forEach((button) => {
    button.addEventListener('click', () => openModal(button.dataset.openModal));
  });
  document.querySelectorAll('[data-close-modal]').forEach((button) => {
    button.addEventListener('click', () => closeModal(button.closest('.modal')));
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') document.querySelectorAll('.modal.open').forEach(closeModal);
  });

  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirm || 'Confirmar esta ação?')) event.preventDefault();
    });
  });

  document.querySelectorAll('[data-status-select]').forEach((select) => {
    select.addEventListener('change', async () => {
      const prior = [...select.options].find((option) => option.defaultSelected)?.value || 'todo';
      select.disabled = true;
      try {
        const response = await fetch(`/api/videos/${select.dataset.videoId}/status`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: select.value }),
        });
        if (!response.ok) throw new Error('Não foi possível atualizar');
        select.className = `status-select ${select.value}`;
        setTimeout(() => window.location.reload(), 220);
      } catch (error) {
        select.value = prior;
        window.alert(error.message);
      } finally {
        select.disabled = false;
      }
    });
  });

  const fileInput = document.getElementById('files');
  const selectedFiles = document.querySelector('[data-selected-files]');
  if (fileInput && selectedFiles) {
    fileInput.addEventListener('change', () => {
      const files = [...fileInput.files];
      if (!files.length) {
        selectedFiles.textContent = 'Nenhum arquivo selecionado';
        return;
      }
      selectedFiles.textContent = files.length === 1 ? files[0].name : `${files.length} arquivos selecionados`;
    });
  }

  document.querySelectorAll('[data-image-preview-input]').forEach((input) => {
    const preview = document.getElementById(input.dataset.previewTarget || '');
    const image = preview?.querySelector('[data-preview-image]');
    const empty = preview?.querySelector('[data-preview-empty]');
    if (!preview || !image) return;

    input.addEventListener('change', () => {
      const file = input.files?.[0];
      if (!file) return;
      if (!file.type.startsWith('image/')) {
        window.alert('Selecione um arquivo de imagem para usar como capa.');
        input.value = '';
        return;
      }
      if (input.dataset.previewUrl) URL.revokeObjectURL(input.dataset.previewUrl);
      const url = URL.createObjectURL(file);
      input.dataset.previewUrl = url;
      image.src = url;
      preview.classList.add('has-preview');
      if (empty) empty.hidden = true;
    });
  });

  const parseLocalDate = (value) => {
    const parts = String(value || '').split('-').map(Number);
    if (parts.length !== 3 || parts.some((part) => !Number.isFinite(part))) return new Date();
    return new Date(parts[0], parts[1] - 1, parts[2]);
  };

  const formatShortDate = (value) => new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
  }).format(value);

  document.querySelectorAll('[data-frequency-config]').forEach((config) => {
    const form = config.closest('form');
    if (!form) return;
    const radios = [...form.querySelectorAll('input[name="frequency_mode"]')];
    const valueInput = form.querySelector('input[name="interval_days"]');
    const startInput = form.querySelector('input[name="start_date"]');
    const label = form.querySelector('[data-frequency-value-label]');
    const suffix = form.querySelector('[data-frequency-value-suffix]');
    const help = form.querySelector('[data-frequency-help]');
    if (!radios.length || !valueInput) return;

    const updateFrequencyPreview = () => {
      const mode = radios.find((radio) => radio.checked)?.value || 'interval';
      const rawValue = Number.parseInt(valueInput.value || '0', 10);
      const value = mode === 'days_off' ? Math.max(0, rawValue || 0) : Math.max(1, rawValue || 1);
      valueInput.min = mode === 'days_off' ? '0' : '1';
      if (mode === 'interval' && Number(valueInput.value) < 1) valueInput.value = '1';
      if (mode === 'days_off' && Number(valueInput.value) < 0) valueInput.value = '0';

      if (label) label.textContent = mode === 'days_off' ? 'Quantos dias completos sem postar?' : 'Publicar a cada quantos dias?';
      if (suffix) suffix.textContent = mode === 'days_off' ? 'dias sem postar' : 'dias entre postagens';

      const step = mode === 'days_off' ? value + 1 : value;
      const first = parseLocalDate(startInput?.value);
      const dates = [0, 1, 2].map((index) => {
        const item = new Date(first);
        item.setDate(item.getDate() + (step * index));
        return formatShortDate(item);
      });
      if (help) {
        if (mode === 'days_off') {
          help.textContent = value === 0
            ? `Sem dias de pausa: ${dates.join(', ')}...`
            : `${value} dia${value === 1 ? '' : 's'} completo${value === 1 ? '' : 's'} sem postar: ${dates.join(', ')}...`;
        } else {
          help.textContent = value === 1
            ? `Postagem diária: ${dates.join(', ')}...`
            : `Intervalo de ${value} dias entre as datas: ${dates.join(', ')}...`;
        }
      }
    };

    radios.forEach((radio) => radio.addEventListener('change', updateFrequencyPreview));
    valueInput.addEventListener('input', updateFrequencyPreview);
    startInput?.addEventListener('change', updateFrequencyPreview);
    updateFrequencyPreview();
  });

  const titleFields = document.querySelector('[data-title-fields]');
  if (titleFields) {
    const textareas = [...titleFields.querySelectorAll('textarea[name="titles"]')];
    const goal = Number(titleFields.dataset.titleGoal || textareas.length || 1);
    const filledCount = document.querySelector('[data-title-filled-count]');
    const remainingCount = document.querySelector('[data-title-remaining-count]');
    const titleProgress = document.querySelector('[data-title-progress]');

    const updateTitleCounter = () => {
      const filled = textareas.filter((field) => field.value.trim()).length;
      const remaining = Math.max(goal - filled, 0);
      if (filledCount) filledCount.textContent = String(filled);
      if (remainingCount) remainingCount.textContent = String(remaining);
      if (titleProgress) titleProgress.style.width = `${Math.min((filled / goal) * 100, 100)}%`;
    };

    textareas.forEach((field) => field.addEventListener('input', updateTitleCounter));
    titleFields.querySelectorAll('[data-clear-title]').forEach((button) => {
      button.addEventListener('click', () => {
        const field = button.closest('[data-title-row]')?.querySelector('textarea[name="titles"]');
        if (!field) return;
        field.value = '';
        field.focus();
        updateTitleCounter();
      });
    });
    updateTitleCounter();
  }

  const toasts = document.querySelectorAll('.toast');
  if (toasts.length) {
    window.setTimeout(() => {
      toasts.forEach((toast) => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-6px)';
        toast.style.transition = '.3s ease';
        window.setTimeout(() => toast.remove(), 320);
      });
    }, 4200);
  }
})();
