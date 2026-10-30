// Interface da central. O Python chama window.lia.*; os cliques voltam por pywebview.api.
(function () {
  const $ = (id) => document.getElementById(id);
  const STATE_LABELS = { idle: "EM ESPERA", listening: "OUVINDO", thinking: "PENSANDO", speaking: "FALANDO" };
  const DAYS = ["DOM", "SEG", "TER", "QUA", "QUI", "SEX", "SÁB"];
  const MONTHS = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"];
  let pendingId = null;
  let shownAt = 0;
  // Teclas e cliques logo depois do cartão aparecer não contam: a pessoa pode estar digitando em outro lugar.
  const GUARD_MS = 1000;

  function tick() {
    const d = new Date();
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    $("clock").textContent = `${hh}:${mm} · ${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;
  }
  tick();
  setInterval(tick, 5000);

  function answer(approved) {
    if (!pendingId || Date.now() - shownAt < GUARD_MS) return;
    const id = pendingId;
    window.lia.hideConfirm(id);
    if (window.pywebview && window.pywebview.api) window.pywebview.api.confirm(id, approved);
  }

  $("btn-yes").addEventListener("click", () => answer(true));
  $("btn-no").addEventListener("click", () => answer(false));
  document.addEventListener("keydown", (e) => {
    if (!pendingId) {
      // Sem cartão aberto, Esc esconde a central (tela cheia); segurar Tab traz de volta.
      if (e.key === "Escape" && window.pywebview && window.pywebview.api) window.pywebview.api.hide();
      return;
    }
    if (e.key === "Enter") answer(true);
    if (e.key === "Escape") answer(false);
  });

  function setMeter(name, value) {
    $(name).textContent = value == null ? "–" : `${value}%`;
    $(`${name}-bar`).style.width = `${value || 0}%`;
  }

  function fillRows(name, items) {
    const rows = document.querySelector(`#panel-${name} .rows`);
    rows.innerHTML = "";
    if (!items || !items.length) {
      rows.innerHTML = `<div class="soon">${name === "lembretes" ? "NADA PENDENTE" : "NADA NOVO"}</div>`;
      return;
    }
    for (const item of items) {
      const div = document.createElement("div");
      if (item.kind) div.className = `reminder ${item.kind}`;
      if (item.tag) {
        const em = document.createElement("em");
        em.textContent = item.tag + " ";
        div.appendChild(em);
      }
      div.appendChild(document.createTextNode(item.text));
      rows.appendChild(div);
    }
  }

  // Aviso na hora do lembrete
  let reminderId = null;
  function answerReminder(done) {
    if (!reminderId) return;
    const id = reminderId;
    window.lia.hideReminder(id);
    if (window.pywebview && window.pywebview.api) {
      if (done) window.pywebview.api.reminder_done(id); else window.pywebview.api.reminder_snooze(id);
    }
  }
  $("btn-reminder-done").addEventListener("click", () => answerReminder(true));
  $("btn-reminder-snooze").addEventListener("click", () => answerReminder(false));

  // Legenda some alguns segundos depois que ele termina de falar (a espera cobre a pausa entre frases).
  const CAPTION_FADE_MS = 3000;
  let fadeTimer = null;
  function scheduleCaptionFade(ms) {
    clearTimeout(fadeTimer);
    const footer = document.querySelector(".caption");
    footer.classList.remove("faded");
    if (!ms) return;
    fadeTimer = setTimeout(() => {
      footer.classList.add("faded");
      fadeTimer = setTimeout(() => { $("caption").textContent = ""; $("you").textContent = ""; }, 900);
    }, ms);
  }

  // Tema de cor (ciano / vermelho): só troca as cores, o layout fica igual.
  const THEMES = ["cyan", "red"];
  $("theme-toggle").addEventListener("click", () => {
    const next = window.lia.theme === "red" ? "cyan" : "red";
    window.lia.setTheme(next);
    if (window.pywebview && window.pywebview.api) window.pywebview.api.set_theme(next);
  });

  // Se o rosto 3D não subir (sem WebGL ou erro), mostra o núcleo simples no lugar de uma tela vazia.
  setTimeout(() => { if (!window.liaFaceReady) document.body.classList.add("no-webgl"); }, 4000);

  window.lia = {
    state: "idle",
    theme: "cyan",
    setTheme(name) {
      if (!THEMES.includes(name)) return;
      this.theme = name;
      document.body.classList.toggle("theme-red", name === "red");
      if (window.liaSetFaceTheme) window.liaSetFaceTheme(name);
    },
    setState(state) {
      this.state = state;
      document.body.classList.remove("idle", "listening", "thinking", "speaking");
      document.body.classList.add(state);
      $("state-label").textContent = "· " + (STATE_LABELS[state] || state.toUpperCase());
      scheduleCaptionFade(state === "idle" && $("caption").textContent ? CAPTION_FADE_MS : 0);
    },
    // Volume da frase que começou a tocar agora (um valor 0..1 a cada frameMs): move a boca do rosto 3D.
    speak(envelope, frameMs) {
      this.envelope = { values: envelope, frameMs, start: performance.now() };
    },
    setCaption(text, who) {
      if (who === "user") {
        $("you").textContent = text ? `“${text}”` : "";
      } else {
        $("caption").textContent = text;
      }
      // Texto novo aparece; se nada for falado (só escrito), some depois de um tempo maior.
      scheduleCaptionFade(this.state === "idle" ? CAPTION_FADE_MS * 3 : 0);
    },
    showConfirm(id, title, detail) {
      pendingId = id;
      shownAt = Date.now();
      $("confirm-title").textContent = title;
      $("confirm-detail").textContent = detail;
      $("confirm").hidden = false;
    },
    hideConfirm(id) {
      if (id && id !== pendingId) return;
      pendingId = null;
      $("confirm").hidden = true;
    },
    showReminder(id, text) {
      reminderId = id;
      $("reminder-alert-text").textContent = text;
      $("reminder-alert").hidden = false;
    },
    hideReminder(id) {
      if (id && id !== reminderId) return;
      reminderId = null;
      $("reminder-alert").hidden = true;
    },
    updatePanel(name, data) {
      if (name === "sistema") {
        setMeter("cpu", data.cpu);
        setMeter("mem", data.mem);
        setMeter("uso", data.uso_plano);
        $("pedidos").textContent = data.pedidos_hoje;
        $("limite").hidden = !data.limite;
      } else {
        const h4 = document.querySelector(`#panel-${name} h4`);
        if (data.title) h4.textContent = data.title;
        fillRows(name, data.items);
      }
    },
  };
})();
