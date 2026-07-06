document.addEventListener('DOMContentLoaded', function () {
    const actionContainer = document.querySelector('.object-tools');

    if (actionContainer) {
        const menu = document.createElement('div');
        menu.className = 'custom-action-dropdown';
        menu.innerHTML = `
            <button type="button" id="customActionBtn">📋 Ações Rápidas ▼</button>
            <div id="customActionMenu" style="display:none; position:absolute; background:white; border:1px solid #ccc; padding:5px;">
                <button type="button" onclick="submitAction('update_requisicao')">🔄 Atualizar Requisição</button><br>
                <button type="button" onclick="submitAction('requisicao_sea')">📊 Gerar SEA</button><br>
                <button type="button" onclick="submitAction('imprimir_fluxo_detalhado')">🖨️ Fluxo Detalhado</button><br>
                <!-- Adicione mais ações aqui -->
            </div>
        `;
        actionContainer.appendChild(menu);

        document.getElementById('customActionBtn').addEventListener('click', function () {
            const dropdown = document.getElementById('customActionMenu');
            dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
        });
    }
});

function submitAction(actionName) {
    const form = document.getElementById('changelist-form');
    const actionSelect = form.querySelector('select[name="action"]');
    actionSelect.value = actionName;
    form.submit();
}


// =========================
// 🔥 AUTO ORDEM (INLINE)
// =========================
function getMaxOrdem() {
    let max = 0;

    document.querySelectorAll('input[name$="-ordem"]').forEach(input => {
        let val = parseInt(input.value);
        if (!isNaN(val) && val > max) {
            max = val;
        }
    });

    return max;
}

function preencherOrdemAutomatica() {
    let max = getMaxOrdem();

    document.querySelectorAll('input[name$="-ordem"]').forEach(input => {
        if (!input.value) {
            max += 1;
            input.value = max;
        }
    });
}

// roda ao carregar a página
document.addEventListener('DOMContentLoaded', function () {
    setTimeout(preencherOrdemAutomatica, 200);
});

// roda quando adiciona novo inline
document.body.addEventListener('click', function (e) {
    if (e.target.closest('.add-row')) {
        setTimeout(preencherOrdemAutomatica, 200);
    }
});