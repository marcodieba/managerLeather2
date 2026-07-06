/* static/pedido/simulador_logistica.js */
/* global interact, SIM_URLS */

(() => {
    "use strict";
  
    const SCALE = 60; // 1m = 60px
  
    let truckData = { l: 13.5, w: 2.4, cap: 32.4 };
    let grid = [];
    let romaneioAtual = "";
    let palletsCache = [];
  
    const URL_API_ROMANEIO = (window.SIM_URLS && window.SIM_URLS.API_ROMANEIO) || "";
    const URL_SALVAR_LAYOUT = (window.SIM_URLS && window.SIM_URLS.SALVAR_LAYOUT) || "";
  
    function showError(msg) {
      const el = document.getElementById("msg-err");
      const ok = document.getElementById("msg-ok");
      if (ok) ok.style.display = "none";
      if (el) { el.style.display = "block"; el.innerText = msg; }
    }
  
    function showOk(msg) {
      const el = document.getElementById("msg-ok");
      const err = document.getElementById("msg-err");
      if (err) err.style.display = "none";
      if (el) { el.style.display = "block"; el.innerText = msg; }
    }
  
    function isFocusable(el) {
      if (!el) return false;
      if (el.disabled) return false;
      const style = window.getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") return false;
      return true;
    }
  
    function setupEnterNavigation() {
      const ids = [
        "truck-select",
        "load-date",
        "p-l",
        "p-w",
        "p-h",
        "p-z",
        "cd-romaneio",
        "btn-buscar",
        "search-input",
        "btn-salvar",
      ];
  
      const base = ids.map(id => document.getElementById(id)).filter(Boolean);
  
      function getList() { return base.filter(isFocusable); }
  
      function focusNext(from, backwards) {
        const list = getList();
        const idx = list.indexOf(from);
        if (idx === -1) return;
  
        const nextIdx = backwards ? idx - 1 : idx + 1;
        if (nextIdx < 0 || nextIdx >= list.length) return;
  
        const next = list[nextIdx];
        next.focus();
        if (next.tagName === "INPUT") next.select?.();
      }
  
      base.forEach(el => {
        el.addEventListener("keydown", (e) => {
          if (e.key !== "Enter") return;
          if (el.tagName === "TEXTAREA") return;
  
          e.preventDefault();
  
          if (el.id === "cd-romaneio") { buscarRomaneio(); return; }
          if (el.tagName === "BUTTON") { el.click(); return; }
  
          focusNext(el, e.shiftKey);
        });
      });
    }
  
    function palletKeyFromItem(it) { return `${it.nr_pallet}||${it.pallet}`; }
    function palletJaNoCaminhao(key) { return !!document.querySelector(`.pallet[data-key="${CSS.escape(key)}"]`); }
  
    function marcarCardComoAdicionado(key) {
      const card = document.querySelector(`.order-card[data-key="${CSS.escape(key)}"]`);
      if (!card) return;
  
      card.setAttribute("data-added", "1");
      if (!card.querySelector(".badge-added")) {
        const h4 = card.querySelector("h4");
        if (h4) h4.insertAdjacentHTML("beforeend", ` <span class="badge-added">NO CAMINHÃO</span>`);
      }
      card.style.opacity = "0.58";
    }
  
    function liberarCard(key) {
      const card = document.querySelector(`.order-card[data-key="${CSS.escape(key)}"]`);
      if (!card) return;
  
      card.removeAttribute("data-added");
      card.style.opacity = "1";
      const badge = card.querySelector(".badge-added");
      if (badge) badge.remove();
    }
  
    function getSelectedOption() {
      const sel = document.getElementById("truck-select");
      if (!sel) return null;
      return sel.options[sel.selectedIndex] || null;
    }
  
    function getVeiculoIdSelecionadoOuNull() {
      const opt = getSelectedOption();
      if (!opt) return null;
      if (opt.dataset.mode !== "db") return null;
      const raw = opt.dataset.veiculoId;
      if (!raw) return null;
      const n = parseInt(raw, 10);
      return Number.isFinite(n) ? n : null;
    }
  
    function getTipoVeiculoIdPadraoOuNull() {
      const opt = getSelectedOption();
      if (!opt) return null;
      if (opt.dataset.mode !== "padrao") return null;
      const raw = opt.dataset.tipoVeiculoId;
      if (!raw) return null;
      const n = parseInt(raw, 10);
      return Number.isFinite(n) ? n : null;
    }
  
    function initTruck() {
      const sel = document.getElementById("truck-select");
      if (!sel) return;
      const opt = sel.options[sel.selectedIndex];
  
      if (!sel.value) {
        const t = document.getElementById("truck-name-display");
        if (t) t.innerText = "Selecione um caminhão";
        return;
      }
  
      const mode = opt.dataset.mode;
  
      if (mode === "padrao") {
        truckData.l = parseFloat(opt.dataset.l);
        truckData.w = parseFloat(opt.dataset.w);
        truckData.cap = parseFloat(opt.dataset.cap || (truckData.l * truckData.w));
        const t = document.getElementById("truck-name-display");
        if (t) t.innerText = opt.text;
      } else {
        const profundidade = parseFloat(opt.dataset.profundidade || "0");
        const largura = parseFloat(opt.dataset.largura || "0");
        const cap = parseFloat(opt.dataset.capacidade || "0");
  
        truckData.l = profundidade > 0 ? profundidade : 13.5;
        truckData.w = largura > 0 ? largura : 2.4;
        truckData.cap = cap > 0 ? cap : (truckData.l * truckData.w);
  
        const t = document.getElementById("truck-name-display");
        if (t) t.innerText = opt.text;
      }
  
      initTruckVisual();
    }
  
    function initTruckVisual() {
      const container = document.getElementById("truck-visual");
      if (!container) return;
  
      container.style.width = (truckData.l * SCALE) + "px";
      container.style.height = (truckData.w * SCALE) + "px";
  
      const statDim = document.getElementById("stat-dim");
      const statCap = document.getElementById("stat-cap");
      if (statDim) statDim.innerText = `${truckData.l.toFixed(2)}m x ${truckData.w.toFixed(2)}m`;
      if (statCap) statCap.innerText = `${truckData.cap.toFixed(2)}m²`;
  
      rebuildGridFromDOM();
      updateStats();
    }
  
    function rebuildGridFromDOM() {
      const gridL = Math.ceil(truckData.l * 10);
      const gridW = Math.ceil(truckData.w * 10);
      grid = Array(gridL).fill().map(() => Array(gridW).fill(0));
  
      const pallets = document.querySelectorAll(".pallet");
      pallets.forEach(p => {
        const z = parseInt(p.getAttribute("data-z") || "0", 10);
        if (z !== 0) return;
  
        const x_px = parseFloat(p.getAttribute("data-x") || "0");
        const y_px = parseFloat(p.getAttribute("data-y") || "0");
        const x_m = x_px / SCALE;
        const y_m = y_px / SCALE;
  
        const comp = parseFloat(p.getAttribute("data-comprimento") || "1.0");
        const larg = parseFloat(p.getAttribute("data-largura") || "1.2");
  
        const i0 = Math.max(0, Math.floor(x_m * 10));
        const j0 = Math.max(0, Math.floor(y_m * 10));
        const cellsL = Math.max(1, Math.ceil(comp * 10));
        const cellsW = Math.max(1, Math.ceil(larg * 10));
  
        for (let i = i0; i < i0 + cellsL && i < grid.length; i++) {
          for (let j = j0; j < j0 + cellsW && j < grid[0].length; j++) {
            grid[i][j] = 1;
          }
        }
      });
    }
  
    function isSpaceFree(x, y, wl, ww) {
      for (let i = x; i < x + wl; i++) {
        for (let j = y; j < y + ww; j++) {
          if (grid[i][j] !== 0) return false;
        }
      }
      return true;
    }
  
    function findSpotOnFloor(comp_m, larg_m) {
      rebuildGridFromDOM();
  
      const cellsL = Math.max(1, Math.ceil(comp_m * 10));
      const cellsW = Math.max(1, Math.ceil(larg_m * 10));
  
      for (let i = 0; i <= grid.length - cellsL; i++) {
        for (let j = 0; j <= grid[0].length - cellsW; j++) {
          if (isSpaceFree(i, j, cellsL, cellsW)) {
            return { x_m: i * 0.1, y_m: j * 0.1 };
          }
        }
      }
      return null;
    }
  
    function filterPallets() {
      const input = document.getElementById("search-input");
      const val = (input ? input.value : "").toLowerCase();
      document.querySelectorAll(".order-card").forEach(card => {
        card.style.display = card.innerText.toLowerCase().includes(val) ? "block" : "none";
      });
    }
  
    function limparLista() {
      palletsCache = [];
      const list = document.getElementById("orders-list");
      if (list) list.innerHTML = "";
      const s = document.getElementById("search-input");
      if (s) s.value = "";
      showOk("Lista limpa.");
    }
  
    async function buscarRomaneio() {
      const inp = document.getElementById("cd-romaneio");
      const cd = (inp ? inp.value : "").trim();
      if (!cd) { showError("Informe o Cd_Romaneo_Faturamento."); return; }
  
      romaneioAtual = cd;
      const rd = document.getElementById("romaneio-display");
      if (rd) rd.innerText = `Romaneio: ${romaneioAtual}`;
  
      try {
        showOk("Buscando pallets...");
        const url = URL_API_ROMANEIO + `?cd_romaneio=${encodeURIComponent(cd)}`;
        const res = await fetch(url, { credentials: "same-origin" });
        const data = await res.json();
  
        if (!res.ok || data.status !== "success") {
          showError(data.message || "Erro ao buscar romaneio.");
          return;
        }
  
        palletsCache = data.items || [];
        renderPalletList(palletsCache);
  
        const okCount = palletsCache.filter(x => x.ok).length;
        const errCount = palletsCache.filter(x => !x.ok).length;
        showOk(`Romaneio carregado. OK: ${okCount}, com erro: ${errCount}.`);
      } catch (e) {
        showError("Falha ao buscar romaneio: " + e);
      }
    }
  
    function renderPalletList(items) {
      const list = document.getElementById("orders-list");
      if (!list) return;
      list.innerHTML = "";
  
      items.forEach(it => {
        const div = document.createElement("div");
        div.className = "order-card";
  
        const key = (it.ok ? palletKeyFromItem(it) : `${it.nr_pallet || "-"}||${it.pallet || "-"}`);
        div.setAttribute("data-key", key);
  
        if (!it.ok) {
          div.innerHTML = `
            <h4>${it.nr_pallet || "-"} / ${it.pallet || "-"} <span class="badge-err">ERRO</span></h4>
            <p>${it.erro || "Erro ao resolver pedido"}</p>
            <p>Seq_Ped_Entrega: <b>${it.seq_ped_entrega || "-"}</b></p>
            <div class="card-actions">
              <button class="btn btn-secondary btn-mini" type="button" data-action="remover">Remover do caminhão</button>
            </div>
          `;
          div.querySelector('[data-action="remover"]').addEventListener("click", (ev) => {
            ev.stopPropagation();
            removerPalletPorKey(key);
          });
          list.appendChild(div);
          return;
        }
  
        const jaNo = palletJaNoCaminhao(key);
  
        div.innerHTML = `
          <h4>${it.nr_pallet} / ${it.pallet}
            <span class="badge-ok">OK</span>
            ${jaNo ? '<span class="badge-added">NO CAMINHÃO</span>' : ''}
          </h4>
          <p>${(it.cliente || "").toString().substring(0, 40)}</p>
          <p style="margin-top:6px;">
            <b>Seq:</b> ${it.seq_ped_entrega} |
            <b>m²:</b> ${Number(it.m2 || 0).toFixed(3)} |
            <b>Saldo:</b> ${Number(it.saldo_pedido_m2 || 0).toFixed(3)}m²
          </p>
          <div class="card-actions">
            <button class="btn btn-primary btn-mini" type="button" data-action="add">Adicionar</button>
            <button class="btn btn-danger btn-mini" type="button" data-action="remover">Remover</button>
          </div>
        `;
  
        div.querySelector('[data-action="add"]').addEventListener("click", (ev) => {
          ev.stopPropagation();
          adicionarDoCard(it);
        });
  
        div.querySelector('[data-action="remover"]').addEventListener("click", (ev) => {
          ev.stopPropagation();
          removerPalletPorKey(key);
        });
  
        div.addEventListener("click", () => adicionarDoCard(it));
  
        if (jaNo) marcarCardComoAdicionado(key);
  
        list.appendChild(div);
      });
    }
  
    function adicionarDoCard(it) {
      const sel = document.getElementById("truck-select");
      if (!sel || !sel.value) { alert("Selecione um caminhão antes."); return; }
  
      const key = palletKeyFromItem(it);
      if (palletJaNoCaminhao(key)) {
        alert("Este pallet já foi adicionado no caminhão.");
        marcarCardComoAdicionado(key);
        return;
      }
  
      const ok = autoPlacePalletFromRomaneio(it);
      if (ok) marcarCardComoAdicionado(key);
    }
  
    function removerPalletPorKey(key) {
      const el = document.querySelector(`.pallet[data-key="${CSS.escape(key)}"]`);
      if (!el) {
        alert("Este pallet não está no caminhão.");
        liberarCard(key);
        return;
      }
      el.remove();
      liberarCard(key);
      rebuildGridFromDOM();
      updateStats();
    }
  
    function autoPlacePalletFromRomaneio(it) {
      const pL = parseFloat(document.getElementById("p-l").value);
      const pW = parseFloat(document.getElementById("p-w").value);
      const pH = parseFloat(document.getElementById("p-h").value);
      const z = parseInt(document.getElementById("p-z").value, 10);
  
      if (z === 1) { addPallet(it, 0, 0, z, pL, pW, pH, false); return true; }
  
      let spot = findSpotOnFloor(pL, pW);
      if (spot) { addPallet(it, spot.x_m, spot.y_m, z, pL, pW, pH, false); return true; }
  
      if (Math.abs(pL - pW) > 1e-9) {
        spot = findSpotOnFloor(pW, pL);
        if (spot) { addPallet(it, spot.x_m, spot.y_m, z, pW, pL, pH, true); return true; }
      }
  
      alert("Caminhão sem espaço no piso! (Tente remonte ou remova/arraste pallets.)");
      return false;
    }
  
    function addPallet(it, x_m, y_m, z, comp_m, larg_m, alt_m, forcedRot) {
      const key = palletKeyFromItem(it);
  
      const pallet = document.createElement("div");
      pallet.className = `pallet z-level-${z}`;
  
      pallet.style.width = (comp_m * SCALE) + "px";
      pallet.style.height = (larg_m * SCALE) + "px";
      pallet.style.transform = `translate(${x_m * SCALE}px, ${y_m * SCALE}px)`;
  
      pallet.setAttribute("data-key", key);
      pallet.setAttribute("data-x", (x_m * SCALE).toString());
      pallet.setAttribute("data-y", (y_m * SCALE).toString());
      pallet.setAttribute("data-z", z.toString());
      pallet.setAttribute("data-area", (comp_m * larg_m).toFixed(4));
  
      pallet.setAttribute("data-seq", it.seq_ped_entrega);
      pallet.setAttribute("data-nr-pallet", it.nr_pallet);
      pallet.setAttribute("data-pallet", it.pallet);
      pallet.setAttribute("data-pes2", (it.pes2 ?? "").toString());
      pallet.setAttribute("data-peso-liquido", (it.peso_liquido ?? "").toString());
      pallet.setAttribute("data-pecas", (it.pecas ?? "").toString());
  
      pallet.setAttribute("data-comprimento", comp_m.toString());
      pallet.setAttribute("data-largura", larg_m.toString());
      pallet.setAttribute("data-altura", alt_m.toString());
      pallet.setAttribute("data-rotacionado", forcedRot ? "true" : "false");
  
      const clienteShort = (it.cliente || "").toString().substring(0, 10);
  
      pallet.innerHTML = `
        <div class="layer-badge">${z}</div>
        <button class="pallet-remove" type="button">Remover</button>
        <div class="pallet-info">
          ${it.nr_pallet}<br>
          <span style="font-size:7px">${clienteShort}</span><br>
          <span style="font-size:7px">m² ${Number(it.m2||0).toFixed(3)}</span>
        </div>
      `;
  
      const bed = document.getElementById("truck-bed");
      if (!bed) return;
      bed.appendChild(pallet);
  
      pallet.querySelector(".pallet-remove").addEventListener("click", (ev) => {
        ev.stopPropagation();
        removerPalletPorKey(key);
      });
  
      setupDraggable(pallet);
      rebuildGridFromDOM();
      updateStats();
    }
  
    function setupDraggable(el) {
      interact(el).draggable({
        modifiers: [
          interact.modifiers.restrictRect({ restriction: "parent" }),
          interact.modifiers.snap({ targets: [interact.snappers.grid({ x: 5, y: 5 })] })
        ],
        listeners: {
          move(event) {
            const target = event.target;
            const x = (parseFloat(target.getAttribute("data-x")) || 0) + event.dx;
            const y = (parseFloat(target.getAttribute("data-y")) || 0) + event.dy;
            target.style.transform = `translate(${x}px, ${y}px)`;
            target.setAttribute("data-x", x);
            target.setAttribute("data-y", y);
          },
          end() {
            rebuildGridFromDOM();
            updateStats();
          }
        }
      }).on("doubletap", function (event) {
        const target = event.currentTarget;
  
        const wpx = target.style.width;
        target.style.width = target.style.height;
        target.style.height = wpx;
  
        const largura = parseFloat(target.getAttribute("data-largura") || "0");
        const comp = parseFloat(target.getAttribute("data-comprimento") || "0");
        target.setAttribute("data-largura", comp.toString());
        target.setAttribute("data-comprimento", largura.toString());
  
        const rot = (target.getAttribute("data-rotacionado") || "false") === "true";
        target.setAttribute("data-rotacionado", (!rot).toString());
  
        const newArea = (parseFloat(target.getAttribute("data-largura")) * parseFloat(target.getAttribute("data-comprimento")));
        target.setAttribute("data-area", newArea.toFixed(4));
  
        rebuildGridFromDOM();
        updateStats();
      });
    }
  
    function updateStats() {
      const pallets = document.querySelectorAll(".pallet");
      let usedArea = 0;
  
      pallets.forEach(p => {
        if (p.getAttribute("data-z") === "0") usedArea += parseFloat(p.getAttribute("data-area") || "0");
      });
  
      const cap = truckData.cap > 0 ? truckData.cap : (truckData.l * truckData.w);
      const perc = cap > 0 ? (usedArea / cap) * 100 : 0;
  
      const su = document.getElementById("stat-used");
      const sp = document.getElementById("stat-perc");
      if (su) su.innerText = `${usedArea.toFixed(2)}m²`;
      if (sp) sp.innerText = `${perc.toFixed(1)}%`;
    }
  
    async function saveLayout() {
      const veiculoId = getVeiculoIdSelecionadoOuNull();
      const tipoVeiculoId = getTipoVeiculoIdPadraoOuNull();
  
      if (!romaneioAtual) { alert("Informe e busque um romaneio antes de salvar."); return; }
      if (!veiculoId && !tipoVeiculoId) { alert("Selecione um veículo cadastrado ou um padrão válido."); return; }
  
      const pallets = document.querySelectorAll(".pallet");
      if (!pallets.length) { alert("Nenhum pallet no caminhão."); return; }
  
      const itens = [];
      pallets.forEach(p => {
        const x_px = parseFloat(p.getAttribute("data-x") || "0");
        const y_px = parseFloat(p.getAttribute("data-y") || "0");
        const x_m = x_px / SCALE;
        const y_m = y_px / SCALE;
  
        itens.push({
          seq_ped_entrega: p.getAttribute("data-seq"),
          nr_pallet: p.getAttribute("data-nr-pallet"),
          pallet: p.getAttribute("data-pallet"),
          pes2: p.getAttribute("data-pes2") || null,
          peso_liquido: p.getAttribute("data-peso-liquido") || null,
          pecas: p.getAttribute("data-pecas") || null,
  
          pos_x: x_m,
          pos_y: y_m,
          pos_z: parseInt(p.getAttribute("data-z") || "0", 10),
  
          largura: parseFloat(p.getAttribute("data-largura") || "1.2"),
          comprimento: parseFloat(p.getAttribute("data-comprimento") || "1.0"),
          altura: parseFloat(p.getAttribute("data-altura") || "1.0"),
          rotacionado: (p.getAttribute("data-rotacionado") || "false") === "true",
        });
      });
  
      const payload = {
        cd_romaneio_faturamento: romaneioAtual,
        veiculo_id: veiculoId,         // null quando for padrão
        tipo_veiculo_id: tipoVeiculoId, // preenchido quando for padrão
        data_embarque: (document.getElementById("load-date") || {}).value || null,
        mapa_carga_json: { romaneio: romaneioAtual, itens: itens },
        itens: itens
      };
  
      const btn = document.getElementById("btn-salvar");
      if (btn) btn.disabled = true;
  
      try {
        const res = await fetch(URL_SALVAR_LAYOUT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify(payload)
        });
  
        const data = await res.json();
        if (!res.ok) {
          if (res.status === 409) alert(data.message || "Pallet duplicado (já embarcado).");
          else alert(data.message || "Erro ao salvar.");
          return;
        }
  
        alert(`Salvo! Embarque ID: ${data.embarque_id} | Itens: ${data.itens_criados}`);
      } catch (e) {
        alert("Falha ao salvar: " + e);
      } finally {
        if (btn) btn.disabled = false;
      }
    }
  
    function clearTruck() {
      if (!confirm("Deseja limpar todo o carregamento?")) return;
  
      const bed = document.getElementById("truck-bed");
      if (bed) bed.innerHTML = "";
  
      initTruckVisual();
  
      document.querySelectorAll(".order-card[data-key]").forEach(c => {
        const key = c.getAttribute("data-key");
        liberarCard(key);
      });
    }
  
    window.initTruck = initTruck;
    window.buscarRomaneio = buscarRomaneio;
    window.limparLista = limparLista;
    window.filterPallets = filterPallets;
    window.clearTruck = clearTruck;
    window.saveLayout = saveLayout;
  
    document.addEventListener("DOMContentLoaded", () => {
      setupEnterNavigation();
      initTruckVisual();
    });
  
  })();
  