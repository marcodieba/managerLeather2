document.addEventListener('DOMContentLoaded', function () {
    document.body.addEventListener('click', function (e) {
        // Detecta clique em qualquer campo select2 de autocomplete
        const select2Container = e.target.closest('.select2-container--admin-autocomplete');

        if (select2Container) {
            // Aguarda a dropdown abrir e então foca no input interno
            const observer = new MutationObserver(function () {
                const input = document.querySelector('.select2-container--open .select2-search__field');
                if (input) {
                    input.focus();
                    observer.disconnect();
                }
            });

            observer.observe(document.body, { childList: true, subtree: true });
        }
    });
});

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