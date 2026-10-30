// Interface da central. O Python chama window.lia.*; os cliques voltam por pywebview.api.
(function () {
  const $ = (id) => document.getElementById(id);
  const STATE_LABELS = { idle: "EM ESPERA", listening: "OUVINDO", thinking: "PENSANDO", speaking: "FALANDO" };
  const DAYS = ["DOM", "SEG", "TER", "QUA", "QUI", "SEX", "SÁB"];
  const MONTHS = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"];
  let pendingId = null;

  function tick() {
    const d = new Date();
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    $("clock").textContent = `${hh}:${mm} · ${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;
  }
  tick();
  setInterval(tick, 5000);

  function answer(approved) {
    if (!pendingId) return;
    const id = pendingId;
    window.lia.hideConfirm(id);
    if (window.pywebview && window.pywebview.api) window.pywebview.api.confirm(id, approved);
  }

  $("btn-yes").addEventListener("click", () => answer(true));
  $("btn-no").addEventListener("click", () => answer(false));
  document.addEventListener("keydown", (e) => {
    if (!pendingId) return;
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
      rows.innerHTML = '<div class="soon">NADA NOVO</div>';
      return;
    }
    for (const item of items) {
      const div = document.createElement("div");
      if (item.tag) {
        const em = document.createElement("em");
        em.textContent = item.tag + " ";
        div.appendChild(em);
      }
      div.appendChild(document.createTextNode(item.text));
      rows.appendChild(div);
    }
  }

  window.lia = {
    setState(state) {
      document.body.className = state;
      $("state-label").textContent = "· " + (STATE_LABELS[state] || state.toUpperCase());
    },
    setCaption(text, who) {
      if (who === "user") {
        $("you").textContent = text ? `“${text}”` : "";
      } else {
        $("caption").textContent = text;
      }
    },
    showConfirm(id, title, detail) {
      pendingId = id;
      $("confirm-title").textContent = title;
      $("confirm-detail").textContent = detail;
      $("confirm").hidden = false;
    },
    hideConfirm(id) {
      if (id && id !== pendingId) return;
      pendingId = null;
      $("confirm").hidden = true;
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
