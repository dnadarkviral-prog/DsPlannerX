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

  const closeCelebration = (root, reloadAfter = false) => {
    root?.classList.remove('open');
    setTimeout(() => root?.remove(), 220);
    if (reloadAfter) window.location.reload();
  };

  const showCelebration = (payload, reloadAfter = false) => {
    if (!payload) return false;
    document.querySelector('[data-goal-celebration]')?.remove();
    const root = document.createElement('div');
    root.className = 'goal-celebration open';
    root.dataset.goalCelebration = '';
    root.innerHTML = `<div class="goal-celebration-backdrop"></div><div class="goal-celebration-card"><button type="button" class="goal-celebration-close">✕</button><div class="goal-trophy">${payload.emoji || '🏆'}</div><span>${payload.title || 'META ALCANÇADA'}</span><h2>${payload.message || 'Parabéns! Meta alcançada.'}</h2><button type="button" class="btn btn-primary">Continuar produzindo 🚀</button></div>`;
    document.body.appendChild(root);
    root.querySelectorAll('button, .goal-celebration-backdrop').forEach((item) => item.addEventListener('click', () => closeCelebration(root, reloadAfter)));
    return true;
  };

  document.querySelectorAll('[data-close-celebration]').forEach((button) => {
    button.addEventListener('click', () => closeCelebration(button.closest('[data-goal-celebration]')));
  });

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
      const prior = [...select.options].find((option) => option.defaultSelected)?.value || 'production';
      select.disabled = true;
      try {
        const response = await fetch(`/api/videos/${select.dataset.videoId}/status`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: select.value }),
        });
        if (!response.ok) throw new Error('Não foi possível atualizar');
        const result = await response.json();
        select.className = `status-select ${select.value}`;
        if (!showCelebration(result.celebration, true)) setTimeout(() => window.location.reload(), 220);
      } catch (error) {
        select.value = prior;
        window.alert(error.message);
      } finally {
        select.disabled = false;
      }
    });
  });

  document.querySelectorAll('[data-script-ready]').forEach((button) => {
    button.addEventListener('click', async () => {
      const current = button.dataset.ready === 'true';
      button.disabled = true;
      try {
        const response = await fetch(`/api/videos/${button.dataset.videoId}/script-ready`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ready: !current }),
        });
        if (!response.ok) throw new Error('Não foi possível atualizar o roteiro');
        const result = await response.json();
        button.dataset.ready = result.ready ? 'true' : 'false';
        button.classList.toggle('ready', result.ready);
        const icon = button.querySelector('span');
        const label = button.querySelector('b');
        if (icon) icon.textContent = result.ready ? '✅' : '📜';
        if (label) label.textContent = result.ready
          ? 'Roteiro pronto'
          : (button.classList.contains('detail-toggle') ? 'Marcar roteiro pronto' : 'Marcar roteiro');
        if (!showCelebration(result.celebration, true)) setTimeout(() => window.location.reload(), 180);
      } catch (error) {
        window.alert(error.message);
      } finally {
        button.disabled = false;
      }
    });
  });

  document.querySelectorAll('[data-published-toggle]').forEach((button) => {
    button.addEventListener('click', async () => {
      const current = button.dataset.published === 'true';
      button.disabled = true;
      try {
        const response = await fetch(`/api/videos/${button.dataset.videoId}/published`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ published: !current }),
        });
        if (!response.ok) throw new Error('Não foi possível atualizar a publicação');
        const result = await response.json();
        button.dataset.published = result.published ? 'true' : 'false';
        button.classList.toggle('published', result.published);
        const icon = button.querySelector('span');
        const label = button.querySelector('b');
        if (icon) icon.textContent = result.published ? '🟢' : '📡';
        if (label) label.textContent = result.published ? 'Publicado' : 'Marcar publicado';
        setTimeout(() => window.location.reload(), 160);
      } catch (error) {
        window.alert(error.message);
      } finally {
        button.disabled = false;
      }
    });
  });

  document.querySelectorAll('[data-password-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      const input = document.getElementById(button.dataset.passwordToggle || '');
      if (!input) return;
      const showing = input.type === 'text';
      input.type = showing ? 'password' : 'text';
      button.textContent = showing ? '👁' : '🙈';
      button.setAttribute('aria-label', showing ? 'Mostrar senha' : 'Ocultar senha');
      input.focus();
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
    if (parts.length !== 3 || parts.some((part) => !Number.isFinite(part))) {
      const now = new Date();
      return new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12);
    }
    return new Date(parts[0], parts[1] - 1, parts[2], 12);
  };

  const formatShortDate = (value) => new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
  }).format(value);

  const formatFullDate = (value) => new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(value);

  const monthValueFromDate = (value) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}`;

  const endOfSelectedMonth = (monthValue, fallbackDate) => {
    const match = String(monthValue || '').match(/^(\d{4})-(\d{2})$/);
    if (!match) return new Date(fallbackDate.getFullYear(), fallbackDate.getMonth() + 1, 0, 12);
    return new Date(Number(match[1]), Number(match[2]), 0, 12);
  };

  const addDays = (value, days) => {
    const result = new Date(value);
    result.setDate(result.getDate() + days);
    return result;
  };

  const addCalendarMonths = (value, months) => {
    const targetIndex = value.getMonth() + months;
    const year = value.getFullYear() + Math.floor(targetIndex / 12);
    const month = ((targetIndex % 12) + 12) % 12;
    const lastDay = new Date(year, month + 1, 0, 12).getDate();
    return new Date(year, month, Math.min(value.getDate(), lastDay), 12);
  };

  const calendarDayDiff = (start, end) => {
    const startUtc = Date.UTC(start.getFullYear(), start.getMonth(), start.getDate());
    const endUtc = Date.UTC(end.getFullYear(), end.getMonth(), end.getDate());
    return Math.round((endUtc - startUtc) / 86400000);
  };

  document.querySelectorAll('[data-schedule-mode-config]').forEach((config) => {
    const form = config.closest('form');
    if (!form) return;
    const modal = config.closest('.modal');
    const radios = [...form.querySelectorAll('input[name="schedule_mode"]')];
    const standardFields = form.querySelector('[data-standard-schedule-fields]');
    const hint = form.querySelector('[data-custom-mode-hint]');
    const customPlanner = modal?.querySelector('[data-custom-planner-settings]');
    const update = () => {
      const custom = radios.find((radio) => radio.checked)?.value === 'custom';
      if (standardFields) standardFields.hidden = custom;
      if (hint) hint.hidden = !custom;
      if (customPlanner) customPlanner.hidden = !custom;
    };
    radios.forEach((radio) => radio.addEventListener('change', update));
    update();
  });

  document.querySelectorAll('[data-frequency-config]').forEach((config) => {
    const form = config.closest('form');
    if (!form) return;

    const frequencyRadios = [...form.querySelectorAll('input[name="frequency_mode"]')];
    const frequencyValueInput = form.querySelector('input[name="interval_days"]');
    const startInput = form.querySelector('input[name="start_date"]');
    const frequencyLabel = form.querySelector('[data-frequency-value-label]');
    const frequencySuffix = form.querySelector('[data-frequency-value-suffix]');
    const frequencyHelp = form.querySelector('[data-frequency-help]');

    const periodRadios = [...form.querySelectorAll('input[name="period_mode"]')];
    const periodValueField = form.querySelector('[data-period-value-field]');
    const periodValueInput = form.querySelector('[data-period-value]');
    const periodValueLabel = form.querySelector('[data-period-value-label]');
    const periodValueSuffix = form.querySelector('[data-period-value-suffix]');
    const periodValueHelp = form.querySelector('[data-period-value-help]');
    const planningMonthField = form.querySelector('[data-planning-month-field]');
    const planningMonthInput = form.querySelector('[data-planning-month]');
    const periodHelp = form.querySelector('[data-period-help]');

    if (!frequencyRadios.length || !frequencyValueInput || !startInput) return;

    const resolvePeriod = () => {
      const first = parseLocalDate(startInput.value);
      const mode = periodRadios.find((radio) => radio.checked)?.value || 'months';
      let rawValue = Number.parseInt(periodValueInput?.value || '1', 10) || 1;
      rawValue = Math.max(1, rawValue);
      let end;
      let summary;

      if (mode === 'days') {
        rawValue = Math.min(rawValue, 7300);
        end = addDays(first, rawValue - 1);
        summary = `${rawValue} dias exatos`;
      } else if (mode === 'month_end') {
        end = endOfSelectedMonth(planningMonthInput?.value, first);
        if (end < first) {
          if (planningMonthInput) planningMonthInput.value = monthValueFromDate(first);
          end = endOfSelectedMonth(planningMonthInput?.value, first);
        }
        summary = `até o fim de ${new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' }).format(end)}`;
      } else {
        rawValue = Math.min(rawValue, 120);
        end = addCalendarMonths(first, rawValue);
        summary = `${rawValue} mês${rawValue === 1 ? '' : 'es'} completo${rawValue === 1 ? '' : 's'}`;
      }

      return {
        first,
        end,
        mode,
        value: rawValue,
        summary,
        periodDays: Math.max(1, calendarDayDiff(first, end) + 1),
      };
    };

    const updatePreview = () => {
      const frequencyMode = frequencyRadios.find((radio) => radio.checked)?.value || 'interval';
      const rawFrequencyValue = Number.parseInt(frequencyValueInput.value || '0', 10);
      const frequencyValue = frequencyMode === 'days_off'
        ? Math.max(0, rawFrequencyValue || 0)
        : Math.max(1, rawFrequencyValue || 1);

      frequencyValueInput.min = frequencyMode === 'days_off' ? '0' : '1';
      if (frequencyMode === 'interval' && Number(frequencyValueInput.value) < 1) frequencyValueInput.value = '1';
      if (frequencyMode === 'days_off' && Number(frequencyValueInput.value) < 0) frequencyValueInput.value = '0';

      if (frequencyLabel) frequencyLabel.textContent = frequencyMode === 'days_off' ? 'Quantos dias completos sem postar?' : 'Publicar a cada quantos dias?';
      if (frequencySuffix) frequencySuffix.textContent = frequencyMode === 'days_off' ? 'dias sem postar' : 'dias entre postagens';

      const periodMode = periodRadios.find((radio) => radio.checked)?.value || 'months';
      const showPeriodValue = periodMode !== 'month_end';
      if (periodValueField) periodValueField.hidden = !showPeriodValue;
      if (periodValueInput) {
        periodValueInput.disabled = !showPeriodValue;
        periodValueInput.required = showPeriodValue;
        periodValueInput.min = '1';
        periodValueInput.max = periodMode === 'days' ? '7300' : '120';
      }
      if (planningMonthField) planningMonthField.hidden = periodMode !== 'month_end';
      if (planningMonthInput) {
        planningMonthInput.disabled = periodMode !== 'month_end';
        planningMonthInput.required = periodMode === 'month_end';
      }
      if (periodValueLabel) periodValueLabel.textContent = periodMode === 'days' ? 'Quantidade exata de dias' : 'Quantidade de meses completos';
      if (periodValueSuffix) {
        const value = Math.max(1, Number.parseInt(periodValueInput?.value || '1', 10) || 1);
        periodValueSuffix.textContent = periodMode === 'days' ? 'dias' : (value === 1 ? 'mês' : 'meses');
      }

      const period = resolvePeriod();
      const step = frequencyMode === 'days_off' ? frequencyValue + 1 : frequencyValue;
      const totalPosts = Math.floor((period.periodDays - 1) / Math.max(1, step)) + 1;
      const sampleDates = [];
      for (let index = 0; index < Math.min(totalPosts, 3); index += 1) {
        sampleDates.push(formatShortDate(addDays(period.first, step * index)));
      }

      if (frequencyHelp) {
        if (frequencyMode === 'days_off') {
          frequencyHelp.textContent = frequencyValue === 0
            ? `Postagem diária: ${sampleDates.join(', ')}...`
            : `${frequencyValue} dia${frequencyValue === 1 ? '' : 's'} inteiro${frequencyValue === 1 ? '' : 's'} sem postar: ${sampleDates.join(', ')}... O ciclo tem ${step} dias.`;
        } else {
          frequencyHelp.textContent = frequencyValue === 1
            ? `Postagem diária: ${sampleDates.join(', ')}...`
            : `A cada ${frequencyValue} dias: ${sampleDates.join(', ')}...`;
        }
      }

      if (periodValueHelp) {
        periodValueHelp.textContent = periodMode === 'months'
          ? `Um mês respeita o calendário: ${formatFullDate(period.first)} até ${formatFullDate(period.end)}.`
          : periodMode === 'days'
            ? `A data inicial já conta como o primeiro dia do período.`
            : '';
      }

      if (periodHelp) {
        const formula = frequencyMode === 'days_off'
          ? `${period.periodDays} dias · ciclo de ${step} dias (1 postagem + ${frequencyValue} sem postar)`
          : `${period.periodDays} dias · intervalo de ${step} dia${step === 1 ? '' : 's'}`;
        periodHelp.textContent = `${period.summary}: ${formatFullDate(period.first)} até ${formatFullDate(period.end)} · ${formula} = ${totalPosts} vídeo${totalPosts === 1 ? '' : 's'}.`;
      }
    };

    frequencyRadios.forEach((radio) => radio.addEventListener('change', updatePreview));
    periodRadios.forEach((radio) => radio.addEventListener('change', updatePreview));
    frequencyValueInput.addEventListener('input', updatePreview);
    periodValueInput?.addEventListener('input', updatePreview);
    startInput.addEventListener('change', updatePreview);
    planningMonthInput?.addEventListener('change', updatePreview);
    updatePreview();
  });

  document.querySelectorAll('[data-frequency-rule-form]').forEach((form) => {
    const start = form.querySelector('input[name="start_date"]');
    const end = form.querySelector('input[name="end_date"]');
    const mode = form.querySelector('[data-rule-frequency-mode]');
    const value = form.querySelector('[data-rule-frequency-value]');
    const label = form.querySelector('[data-rule-frequency-label]');
    const suffix = form.querySelector('[data-rule-frequency-suffix]');
    const preview = form.querySelector('[data-rule-preview]');
    const update = () => {
      const isDaysOff = mode?.value === 'days_off';
      const raw = Number.parseInt(value?.value || (isDaysOff ? '0' : '1'), 10);
      const normalized = isDaysOff ? Math.max(0, raw || 0) : Math.max(1, raw || 1);
      if (value) {
        value.min = isDaysOff ? '0' : '1';
        value.value = String(normalized);
      }
      if (label) label.textContent = isDaysOff ? 'Quantos dias completos sem postar?' : 'Publicar a cada quantos dias?';
      if (suffix) suffix.textContent = isDaysOff ? 'dias sem postar' : 'dias entre postagens';
      if (!start?.value || !end?.value || !preview) return;
      const first = parseLocalDate(start.value);
      const last = parseLocalDate(end.value);
      const days = Math.max(1, calendarDayDiff(first, last) + 1);
      const step = isDaysOff ? normalized + 1 : normalized;
      const count = Math.floor((days - 1) / Math.max(1, step)) + 1;
      const sample = [];
      for (let i = 0; i < Math.min(4, count); i += 1) sample.push(formatShortDate(addDays(first, i * step)));
      preview.textContent = `${days} dias no período · ${count} vídeo${count === 1 ? '' : 's'} · datas: ${sample.join(', ')}${count > 4 ? '...' : ''}`;
    };
    [start, end, mode, value].forEach((input) => input?.addEventListener('input', update));
    mode?.addEventListener('change', update);
    update();
  });

  const customPlansNode = document.getElementById('customPlansData');
  let customPlans = [];
  if (customPlansNode) {
    try { customPlans = JSON.parse(customPlansNode.textContent || '[]'); } catch (_error) { customPlans = []; }
  }

  const monthBounds = (monthValue) => {
    const match = String(monthValue || '').match(/^(\d{4})-(\d{2})$/);
    const now = new Date();
    const year = match ? Number(match[1]) : now.getFullYear();
    const monthIndex = match ? Number(match[2]) - 1 : now.getMonth();
    return {
      first: new Date(year, monthIndex, 1, 12),
      last: new Date(year, monthIndex + 1, 0, 12),
    };
  };

  const isoLocalDate = (value) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;

  document.querySelectorAll('[data-custom-plan-builder]').forEach((builder) => {
    const monthInput = builder.querySelector('[data-custom-plan-month]');
    const notesInput = builder.querySelector('[data-custom-plan-notes]');
    const rulesList = builder.querySelector('[data-custom-rules-list]');
    const ruleTemplate = builder.querySelector('[data-custom-rule-template]');
    const addRuleButton = builder.querySelector('[data-add-custom-rule]');
    const generateWeeksButton = builder.querySelector('[data-generate-month-weeks]');
    const countNode = builder.querySelector('[data-custom-plan-count]');
    const datesNode = builder.querySelector('[data-custom-plan-dates]');
    const deleteSlot = builder.querySelector('[data-custom-plan-delete-slot]');
    const channelId = builder.dataset.channelId;
    const planMap = new Map(customPlans.map((plan) => [plan.year_month, plan]));
    if (!monthInput || !rulesList || !ruleTemplate) return;

    const normalizeRuleControls = (row) => {
      const mode = row.querySelector('select[name="rule_frequency_modes"]');
      const value = row.querySelector('input[name="rule_interval_days"]');
      const suffix = row.querySelector('[data-custom-rule-suffix]');
      const isDaysOff = mode?.value === 'days_off';
      const raw = Number.parseInt(value?.value || (isDaysOff ? '0' : '1'), 10);
      const normalized = isDaysOff ? Math.max(0, raw || 0) : Math.max(1, raw || 1);
      if (value) {
        value.min = isDaysOff ? '0' : '1';
        value.value = String(normalized);
      }
      if (suffix) suffix.textContent = isDaysOff ? 'dias sem postar' : 'dias entre postagens';
      return { mode: isDaysOff ? 'days_off' : 'interval', value: normalized, step: isDaysOff ? normalized + 1 : normalized };
    };

    const renumberRules = () => {
      [...rulesList.querySelectorAll('[data-custom-rule-row]')].forEach((row, index) => {
        const number = row.querySelector('[data-custom-rule-index]');
        if (number) number.textContent = String(index + 1).padStart(2, '0');
      });
    };

    const updateDeleteSlot = () => {
      if (!deleteSlot) return;
      deleteSlot.innerHTML = '';
      const selected = monthInput.value;
      if (!planMap.has(selected)) return;
      const form = document.createElement('form');
      form.method = 'post';
      form.action = `/channels/${channelId}/custom-plans/${selected}/delete`;
      form.innerHTML = '<button class="btn btn-danger" type="submit">🗑️ Remover planejamento deste mês</button>';
      form.addEventListener('submit', (event) => {
        if (!window.confirm('Remover o planejamento deste mês? Os cards de vídeo serão mantidos.')) event.preventDefault();
      });
      deleteSlot.appendChild(form);
    };

    const updateCustomSummary = () => {
      const allDates = new Set();
      [...rulesList.querySelectorAll('[data-custom-rule-row]')].forEach((row) => {
        const startInput = row.querySelector('input[name="rule_start_dates"]');
        const endInput = row.querySelector('input[name="rule_end_dates"]');
        const preview = row.querySelector('[data-custom-rule-preview]');
        const normalized = normalizeRuleControls(row);
        if (!startInput?.value || !endInput?.value) {
          if (preview) preview.textContent = 'Escolha o início e o fim deste período.';
          return;
        }
        const first = parseLocalDate(startInput.value);
        const last = parseLocalDate(endInput.value);
        if (last < first) {
          if (preview) preview.textContent = 'A data final precisa vir depois da inicial.';
          return;
        }
        let current = new Date(first);
        let count = 0;
        const samples = [];
        while (current <= last && count < 400) {
          const key = isoLocalDate(current);
          allDates.add(key);
          if (samples.length < 5) samples.push(formatShortDate(current));
          current = addDays(current, Math.max(1, normalized.step));
          count += 1;
        }
        if (preview) {
          const rhythm = normalized.mode === 'days_off'
            ? `${normalized.value} dia${normalized.value === 1 ? '' : 's'} completo${normalized.value === 1 ? '' : 's'} sem postar`
            : (normalized.value === 1 ? 'postagem diária' : `a cada ${normalized.value} dias`);
          preview.textContent = `${count} vídeo${count === 1 ? '' : 's'} · ${rhythm} · ${samples.join(', ')}${count > samples.length ? '...' : ''}`;
        }
      });
      const dates = [...allDates].sort();
      if (countNode) countNode.textContent = String(dates.length);
      if (datesNode) {
        datesNode.innerHTML = dates.length
          ? dates.map((item) => `<span>${formatShortDate(parseLocalDate(item))}</span>`).join('')
          : 'Adicione um período de postagem para calcular.';
      }
      updateDeleteSlot();
    };

    const addRule = (data = {}) => {
      const fragment = ruleTemplate.content.cloneNode(true);
      const row = fragment.querySelector('[data-custom-rule-row]');
      const bounds = monthBounds(monthInput.value);
      const start = row.querySelector('input[name="rule_start_dates"]');
      const end = row.querySelector('input[name="rule_end_dates"]');
      const mode = row.querySelector('select[name="rule_frequency_modes"]');
      const value = row.querySelector('input[name="rule_interval_days"]');
      if (start) {
        start.min = isoLocalDate(bounds.first);
        start.max = isoLocalDate(bounds.last);
        start.value = data.start_date || isoLocalDate(bounds.first);
      }
      if (end) {
        end.min = isoLocalDate(bounds.first);
        end.max = isoLocalDate(bounds.last);
        end.value = data.end_date || isoLocalDate(bounds.last);
      }
      if (mode) mode.value = data.frequency_mode === 'days_off' ? 'days_off' : 'interval';
      if (value) value.value = String(data.interval_days ?? 1);
      row.querySelector('[data-remove-custom-rule]')?.addEventListener('click', () => {
        row.remove();
        renumberRules();
        updateCustomSummary();
      });
      row.querySelectorAll('input, select').forEach((input) => {
        input.addEventListener('input', updateCustomSummary);
        input.addEventListener('change', updateCustomSummary);
      });
      rulesList.appendChild(fragment);
      renumberRules();
      updateCustomSummary();
    };

    const generateWeeks = () => {
      rulesList.innerHTML = '';
      const bounds = monthBounds(monthInput.value);
      const lastDay = bounds.last.getDate();
      let startDay = 1;
      let week = 1;
      while (startDay <= lastDay) {
        const endDay = Math.min(startDay + 6, lastDay);
        const start = new Date(bounds.first.getFullYear(), bounds.first.getMonth(), startDay, 12);
        const end = new Date(bounds.first.getFullYear(), bounds.first.getMonth(), endDay, 12);
        addRule({
          start_date: isoLocalDate(start),
          end_date: isoLocalDate(end),
          frequency_mode: 'interval',
          interval_days: 1,
        });
        startDay = endDay + 1;
        week += 1;
      }
      updateCustomSummary();
    };

    const loadPlan = (monthValue, createFresh = false) => {
      const normalizedMonth = monthValue || builder.dataset.defaultMonth || monthValueFromDate(new Date());
      monthInput.value = normalizedMonth;
      rulesList.innerHTML = '';
      const plan = createFresh ? null : planMap.get(normalizedMonth);
      if (notesInput) notesInput.value = plan?.notes || '';
      if (plan?.rules?.length) plan.rules.forEach((rule) => addRule(rule));
      else generateWeeks();
      updateDeleteSlot();
      updateCustomSummary();
    };

    addRuleButton?.addEventListener('click', () => addRule({}));
    generateWeeksButton?.addEventListener('click', generateWeeks);
    monthInput.addEventListener('change', () => loadPlan(monthInput.value, false));
    builder.addEventListener('submit', (event) => {
      if (!rulesList.querySelector('[data-custom-rule-row]')) {
        event.preventDefault();
        window.alert('Adicione pelo menos um período de postagem antes de salvar.');
      }
    });
    builder._loadCustomPlan = loadPlan;
    const selected = builder.dataset.selectedPlanMonth || monthInput.value || builder.dataset.defaultMonth;
    loadPlan(selected, false);
  });

  document.querySelectorAll('[data-new-custom-plan]').forEach((button) => {
    button.addEventListener('click', () => {
      const modal = document.getElementById('settingsModal');
      const customRadio = modal?.querySelector('input[name="schedule_mode"][value="custom"]');
      if (customRadio) {
        customRadio.checked = true;
        customRadio.dispatchEvent(new Event('change', { bubbles: true }));
      }
      const builder = modal?.querySelector('[data-custom-plan-builder]');
      if (builder?._loadCustomPlan) builder._loadCustomPlan(builder.dataset.defaultMonth, true);
    });
  });

  const autoOpenModal = document.querySelector('[data-auto-open-modal]');
  if (autoOpenModal?.dataset.autoOpenModal) setTimeout(() => openModal(autoOpenModal.dataset.autoOpenModal), 80);

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

    const titleStatusLabels = {
      ready: 'Para uso',
      progress: 'Em andamento',
      completed: 'Concluído',
    };

    titleFields.querySelectorAll('[data-title-status-box]').forEach((statusBox) => {
      const row = statusBox.closest('[data-title-row]');
      const input = statusBox.querySelector('[data-title-status-input]');
      const label = statusBox.querySelector('[data-title-status-label]');
      const options = [...statusBox.querySelectorAll('[data-title-status-option]')];
      if (!row || !input || !options.length) return;

      const applyStatus = (status) => {
        const normalized = Object.prototype.hasOwnProperty.call(titleStatusLabels, status) ? status : 'ready';
        input.value = normalized;
        row.dataset.titleStatus = normalized;
        row.classList.remove('title-status-ready', 'title-status-progress', 'title-status-completed');
        row.classList.add(`title-status-${normalized}`);
        if (label) label.textContent = titleStatusLabels[normalized];
        options.forEach((option) => {
          const selected = option.dataset.titleStatusOption === normalized;
          option.classList.toggle('active', selected);
          option.setAttribute('aria-pressed', selected ? 'true' : 'false');
        });
      };

      options.forEach((option) => {
        option.addEventListener('click', () => applyStatus(option.dataset.titleStatusOption || 'ready'));
      });
      applyStatus(input.value);
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
