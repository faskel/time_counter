(function () {
    'use strict';

    function ensureToastContainer() {
        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        return container;
    }

    function toast(options) {
        const message = typeof options === 'string' ? options : options.html;
        const classes = typeof options === 'string' ? '' : (options.classes || '');
        const container = ensureToastContainer();
        const el = document.createElement('div');
        el.className = `app-toast ${classes}`.trim();
        el.innerHTML = message;
        container.appendChild(el);
        setTimeout(() => {
            el.style.opacity = '0';
            el.style.transition = 'opacity 0.2s ease';
            setTimeout(() => el.remove(), 220);
        }, 3200);
    }

    const modalInstances = new WeakMap();

    function createModalInstance(modalEl) {
        const instance = {
            open() {
                modalEl.classList.add('is-open');
                document.body.classList.add('modal-open');
            },
            close() {
                modalEl.classList.remove('is-open');
                if (!document.querySelector('.modal.is-open')) {
                    document.body.classList.remove('modal-open');
                }
            },
        };
        modalInstances.set(modalEl, instance);

        modalEl.addEventListener('click', (event) => {
            if (event.target === modalEl) {
                instance.close();
            }
        });

        modalEl.querySelectorAll('.modal-close').forEach((btn) => {
            btn.addEventListener('click', (event) => {
                event.preventDefault();
                instance.close();
            });
        });

        return instance;
    }

    const Modal = {
        init(elements) {
            const list = elements instanceof NodeList ? Array.from(elements) : [].concat(elements || []);
            return list.map((el) => {
                if (!modalInstances.has(el)) {
                    createModalInstance(el);
                }
                return modalInstances.get(el);
            });
        },
        getInstance(el) {
            if (!modalInstances.has(el)) {
                createModalInstance(el);
            }
            return modalInstances.get(el);
        },
    };

    function initModalTriggers() {
        document.querySelectorAll('.modal-trigger').forEach((trigger) => {
            trigger.addEventListener('click', (event) => {
                event.preventDefault();
                const target = trigger.getAttribute('href');
                if (!target || target === '#') {
                    return;
                }
                const modalEl = document.querySelector(target);
                if (modalEl) {
                    Modal.getInstance(modalEl).open();
                }
            });
        });
    }

    function initDropdowns() {
        document.querySelectorAll('.dropdown-trigger').forEach((trigger) => {
            const targetId = trigger.dataset.target;
            const menu = targetId ? document.getElementById(targetId) : null;
            if (!menu) {
                return;
            }

            const wrapper = trigger.closest('.dropdown-wrapper');
            if (wrapper && menu.parentElement !== wrapper) {
                wrapper.appendChild(menu);
            }

            trigger.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
                const isOpen = menu.classList.contains('is-open');
                document.querySelectorAll('.dropdown-content.is-open').forEach((item) => {
                    item.classList.remove('is-open');
                });
                if (!isOpen) {
                    menu.classList.add('is-open');
                }
            });
        });

        document.addEventListener('click', (event) => {
            if (!event.target.closest('.dropdown-wrapper')) {
                document.querySelectorAll('.dropdown-content.is-open').forEach((item) => {
                    item.classList.remove('is-open');
                });
            }
        });
    }

    let tooltipEl = null;

    function ensureTooltipElement() {
        if (!tooltipEl) {
            tooltipEl = document.createElement('div');
            tooltipEl.className = 'tooltip-bubble';
            document.body.appendChild(tooltipEl);
        }
        return tooltipEl;
    }

    function initTooltips() {
        if (document.body.dataset.tooltipsBound === '1') {
            return;
        }
        document.body.dataset.tooltipsBound = '1';
        const bubble = ensureTooltipElement();

        document.addEventListener('mouseover', (event) => {
            const el = event.target.closest('.tooltipped[data-tooltip]');
            if (!el) {
                return;
            }
            const text = el.getAttribute('data-tooltip');
            if (!text) {
                return;
            }
            bubble.textContent = text;
            bubble.classList.add('is-visible');
            const rect = el.getBoundingClientRect();
            bubble.style.top = `${Math.max(8, rect.top - bubble.offsetHeight - 8)}px`;
            bubble.style.left = `${Math.min(
                window.innerWidth - bubble.offsetWidth - 8,
                Math.max(8, rect.left + rect.width / 2 - bubble.offsetWidth / 2)
            )}px`;
        });

        document.addEventListener('mouseout', (event) => {
            const el = event.target.closest('.tooltipped[data-tooltip]');
            if (el && !el.contains(event.relatedTarget)) {
                bubble.classList.remove('is-visible');
            }
        });
    }

    const Collapsible = {
        init() {
            return [];
        },
    };

    const Dropdown = {
        init() {
            initDropdowns();
            return [];
        },
    };

    const Tooltip = {
        init() {
            initTooltips();
            return [];
        },
    };

    window.M = {
        toast,
        Modal,
        Dropdown,
        Tooltip,
        Collapsible,
    };

    function initAppUi() {
        Modal.init(document.querySelectorAll('.modal'));
        initModalTriggers();
        initDropdowns();
        initTooltips();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAppUi);
    } else {
        initAppUi();
    }
})();
