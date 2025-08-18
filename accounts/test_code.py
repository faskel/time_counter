from datetime import datetime, timedelta, date
#
# from python313.traceback import print_tb
#
# order = 1
# total_duration = timedelta()
# enter = [datetime(2025, 8, 1, 10, 0), #0
#          datetime(2025, 8, 1, 13, 30)]#1
#
# exit = [datetime(2025, 8, 1, 13, 0), #0
#         datetime(2025, 8, 1, 14, 30)]#1
# probe = datetime(2025, 8, 1, 0, 30)
# total_duration += (exit[0]-enter[0])
# total_duration += (exit[1]-enter[1])
# # print(total_duration)
# if order>0:
#     for i in range(order):
#         A=enter[i+1]-exit[i]
#
# print(A)
# new_time = total_duration - probe

six_day_target = timedelta(hours=6)
short_day_target = timedelta(hours=7)
normal_day_target = timedelta(hours=8)
unpaid_mini_break_threshold = timedelta(minutes=30)

six_day_target -= unpaid_mini_break_threshold

{#<script>#}
{#    function getCookie(name) {#}
{#        let cookieValue = null;#}
{#        if (document.cookie && document.cookie !== '') {#}
{#            const cookies = document.cookie.split(';');#}
{#            for (let i = 0; i < cookies.length; i++) {#}
{#                const cookie = cookies[i].trim();#}
{#                if (cookie.substring(0, name.length + 1) === (name + '=')) {#}
{#                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));#}
{#                    break;#}
{#                }#}
{#            }#}
{#        }#}
{#        return cookieValue;#}
{#    }#}
{##}
{#    document.addEventListener('DOMContentLoaded', function () {#}
{#        const csrftoken = getCookie('csrftoken');#}
{##}
{#        // --- Навигация по месяцам ---#}
{#        document.getElementById('prev-month').addEventListener('click', function () {#}
{#            const currentDate = new Date('{{ selected_date }}T00:00:00');#}
{#            currentDate.setMonth(currentDate.getMonth() - 1);#}
{#            window.location.search = `?date=${currentDate.toISOString().split('T')[0]}`;#}
{#        });#}
{##}
{#        document.getElementById('next-month').addEventListener('click', function () {#}
{#            const currentDate = new Date('{{ selected_date }}T00:00:00');#}
{#            currentDate.setMonth(currentDate.getMonth() + 1);#}
{#            window.location.search = `?date=${currentDate.toISOString().split('T')[0]}`;#}
{#        });#}
{##}
{#        // --- Обновленная функция для получения всех элементов, относящихся к дню ---#}
{#        // Ищет элементы в пределах всей страницы, т.к. они теперь разбросаны по разным таблицам#}
{#        function getDayElements(dayId) {#}
{#            const elements = {};#}
{##}
{#            elements.dayTypeDisplay = document.querySelector(`.day-type-display[data-day-id="${dayId}"]`);#}
{#            elements.dayTypeSelect = document.querySelector(`.day-type-select[data-day-id="${dayId}"]`);#}
{##}
{#            // Найти все time-pair-group для конкретного dayId#}
{#            elements.timePairGroups = document.querySelectorAll(`.time-pair-group[data-day-id="${dayId}"]`);#}
{##}
{#            elements.totalTimeDisplay = document.getElementById(`total-time-${dayId}`);#}
{#            elements.dayBalanceDisplay = document.getElementById(`day-balance-${dayId}`);#}
{##}
{#            // Найти кнопки для конкретного dayId#}
{#            const actionButtonContainer = document.querySelector(`button.edit-btn[data-day-id="${dayId}"]`).closest('.action-buttons');#}
{#            elements.editBtn = actionButtonContainer.querySelector('.edit-btn');#}
{#            elements.saveBtn = actionButtonContainer.querySelector('.save-btn');#}
{#            elements.addNewPairBtn = actionButtonContainer.querySelector('.add-new-pair-btn');#}
{#            elements.removePairBtn = actionButtonContainer.querySelector('.remove-pair-btn');#}
{##}
{#            return elements;#}
{#        }#}
{##}
{##}
{#        // --- Обработка кнопки "Изменить" ---#}
{#        document.querySelectorAll('.edit-btn').forEach(btn => {#}
{#            btn.addEventListener('click', function () {#}
{#                const dayId = this.getAttribute('data-day-id');#}
{#                const elements = getDayElements(dayId);#}
{##}
{#                elements.timePairGroups.forEach(pairGroup => {#}
{#                    pairGroup.querySelectorAll('.time-input').forEach(input => {#}
{#                        input.style.display = 'block';#}
{#                        // Если поле времени пустое, подставить текущее время#}
{#                        if (!input.value) {#}
{#                            input.value = new Date().toTimeString().slice(0, 5);#}
{#                        }#}
{#                    });#}
{#                    pairGroup.querySelectorAll('.time-display').forEach(span => {#}
{#                        span.style.display = 'none';#}
{#                    });#}
{#                    pairGroup.querySelectorAll('.time-label').forEach(label => {#}
{#                        label.style.display = 'inline';#}
{#                    });#}
{#                });#}
{##}
{#                if (elements.dayTypeSelect) elements.dayTypeSelect.style.display = 'block';#}
{#                if (elements.dayTypeDisplay) elements.dayTypeDisplay.style.display = 'none';#}
{##}
{#                if (elements.saveBtn) elements.saveBtn.style.display = 'block';#}
{#                if (elements.addNewPairBtn) elements.addNewPairBtn.style.display = 'block';#}
{#                if (elements.removePairBtn) elements.removePairBtn.style.display = 'block';#}
{#                if (elements.editBtn) elements.editBtn.style.display = 'none';#}
{#            });#}
{#        });#}
{##}
{#        // --- Обработка кнопки "Сохранить" ---#}
{#        document.querySelectorAll('.save-btn').forEach(btn => {#}
{#            btn.addEventListener('click', function () {#}
{#                const dayId = this.getAttribute('data-day-id');#}
{#                const elements = getDayElements(dayId);#}
{##}
{#                const timeData = {#}
{#                    day_type: elements.dayTypeSelect ? elements.dayTypeSelect.value : '',#}
{#                    time_entries: [],#}
{#                    dayId: dayId#}
{#                };#}
{##}
{#                elements.timePairGroups.forEach((pairGroup) => {#}
{#                    const entryInput = pairGroup.querySelector('.entry-input');#}
{#                    const exitInput = pairGroup.querySelector('.exit-input');#}
{##}
{#                    if (entryInput && entryInput.value) {#}
{#                        timeData.time_entries.push({#}
{#                            type: 'EG',#}
{#                            time: entryInput.value,#}
{#                            order: parseInt(pairGroup.dataset.order)#}
{#                        });#}
{#                    }#}
{##}
{#                    if (exitInput && exitInput.value) {#}
{#                        timeData.time_entries.push({#}
{#                            type: 'OG',#}
{#                            time: exitInput.value,#}
{#                            order: parseInt(pairGroup.dataset.order)#}
{#                        });#}
{#                    }#}
{#                });#}
{##}
{#                fetch('{% url "update_work_times" %}', {#}
{#                    method: 'POST',#}
{#                    headers: {#}
{#                        'Content-Type': 'application/json',#}
{#                        'X-CSRFToken': csrftoken,#}
{#                    },#}
{#                    body: JSON.stringify(timeData)#}
{#                })#}
{#                    .then(response => response.json())#}
{#                    .then(data => {#}
{#                        if (data.success) {#}
{#                            alert('Данные успешно сохранены!');#}
{##}
{#                            elements.timePairGroups.forEach(pairGroup => {#}
{#                                pairGroup.querySelectorAll('.time-input').forEach(input => {#}
{#                                    input.style.display = 'none';#}
{#                                });#}
{#                                pairGroup.querySelectorAll('.time-display').forEach(span => {#}
{#                                    const input = span.parentNode.querySelector('.time-input');#}
{#                                    span.textContent = input ? (input.value || '-') : '-';#}
{#                                    span.style.display = 'inline';#}
{#                                });#}
{#                                pairGroup.querySelectorAll('.time-label').forEach(label => {#}
{#                                    label.style.display = 'none';#}
{#                                });#}
{#                            });#}
{##}
{#                            // Обновляем тип дня#}
{#                            if (elements.dayTypeSelect) {#}
{#                                const selectedOption = elements.dayTypeSelect.options[elements.dayTypeSelect.selectedIndex];#}
{#                                elements.dayTypeDisplay.textContent = selectedOption.textContent;#}
{#                                elements.dayTypeDisplay.className = `day-type-display ${selectedOption.value}`;#}
{#                                elements.dayTypeDisplay.style.display = 'inline';#}
{#                                elements.dayTypeSelect.style.display = 'none';#}
{#                            }#}
{##}
{#                            // Обновляем Итого за день#}
{#                            if (elements.totalTimeDisplay) {#}
{#                                elements.totalTimeDisplay.textContent = data.new_total_time || '-';#}
{#                            }#}
{##}
{#                            // Обновляем Баланс за день#}
{#                            if (elements.dayBalanceDisplay) {#}
{#                                elements.dayBalanceDisplay.textContent = data.new_day_balance || '-';#}
{#                                if (data.is_negative_day_balance) {#}
{#                                    elements.dayBalanceDisplay.classList.add('negative');#}
{#                                } else {#}
{#                                    elements.dayBalanceDisplay.classList.remove('negative');#}
{#                                }#}
{#                            }#}
{##}
{#                            // Обновляем Баланс за месяц#}
{#                            const monthBalanceTotalSpan = document.getElementById('month-balance-total');#}
{#                            if (monthBalanceTotalSpan) {#}
{#                                monthBalanceTotalSpan.textContent = data.total_month_balance || '-';#}
{#                                if (data.is_month_balance_negative) {#}
{#                                    monthBalanceTotalSpan.classList.add('negative');#}
{#                                    monthBalanceTotalSpan.classList.remove('positive');#}
{#                                } else {#}
{#                                    monthBalanceTotalSpan.classList.remove('negative');#}
{#                                    monthBalanceTotalSpan.classList.add('positive');#}
{#                                }#}
{#                            }#}
{##}
{#                            // Возвращаем кнопки в исходное состояние#}
{#                            if (elements.editBtn) elements.editBtn.style.display = 'block';#}
{#                            if (elements.saveBtn) elements.saveBtn.style.display = 'none';#}
{#                            if (elements.addNewPairBtn) elements.addNewPairBtn.style.display = 'none';#}
{#                            if (elements.removePairBtn) elements.removePairBtn.style.display = 'none';#}
{##}
{#                            // Перезагружаем страницу, чтобы убедиться, что все action.id корректны#}
{#                            // (это важно для кнопок удаления/добавления пар, т.к. они зависят от актуальных order)#}
{#                            location.reload();#}
{##}
{#                        } else {#}
{#                            alert('Ошибка при сохранении: ' + data.message);#}
{#                        }#}
{#                    })#}
{#                    .catch(error => {#}
{#                        console.error('Ошибка при отправке запроса:', error);#}
{#                        alert('Произошла ошибка при сохранении');#}
{#                    });#}
{#            });#}
{#        });#}
{##}
{#        // --- Обработка кнопки "+ Вход/Выход" ---#}
{#        document.querySelectorAll('.add-new-pair-btn').forEach(btn => {#}
{#            btn.addEventListener('click', function () {#}
{#                const dayId = this.getAttribute('data-day-id');#}
{#                const elements = getDayElements(dayId);#}
{##}
{#                // Найти все time-pair-group для конкретного dayId#}
{#                const allTimesForDay = elements.timePairGroups;#}
{##}
{#                let newPairOrder = 0;#}
{#                // Находим максимальный существующий order#}
{#                if (allTimesForDay.length > 0) {#}
{#                    const maxExistingOrder = Array.from(allTimesForDay).reduce((max, pair) => {#}
{#                        const order = parseInt(pair.dataset.order);#}
{#                        return isNaN(order) ? max : Math.max(max, order);#}
{#                    }, -1);#}
{#                    newPairOrder = maxExistingOrder + 1;#}
{#                }#}
{##}
{#                const newPairGroup = document.createElement('div');#}
{#                newPairGroup.className = 'time-pair-group';#}
{#                newPairGroup.dataset.order = newPairOrder;#}
{#                newPairGroup.dataset.dayId = dayId;#}
{#                newPairGroup.innerHTML = `#}
{#                    <div class="time-entry-row">#}
{#                        <span class="time-label entry-label">Вход:</span>#}
{#                        <span class="time-display entry-display" style="display: none;">-</span>#}
{#                        <input type="time" class="time-input entry-input"#}
{#                            value="${new Date().toTimeString().slice(0, 5)}" data-status-gate="EG" data-order="${newPairOrder}" style="display: block;">#}
{#                    </div>#}
{#                    <div class="time-entry-row">#}
{#                        <span class="time-label exit-label">Выход:</span>#}
{#                        <span class="time-display exit-display" style="display: none;">-</span>#}
{#                        <input type="time" class="time-input exit-input"#}
{#                            value="" data-status-gate="OG" data-order="${newPairOrder}" style="display: block;">#}
{#                    </div>#}
{#                `;#}
{##}
{#                // Найти ячейку, куда нужно добавить новую пару (это будет та же ячейка, где находятся существующие пары)#}
{#                if (allTimesForDay.length > 0) {#}
{#                    allTimesForDay[0].closest('td').appendChild(newPairGroup);#}
{#                } else {#}
{#                    // Если пар еще нет, найти соответствующую ячейку по data-day-id#}
{#                    // (Предполагаем, что есть пустая ячейка для дня в row-key 'times')#}
{#                    const timeCellForDay = document.querySelector(`tr[data-row-key="times"] td button.edit-btn[data-day-id="${dayId}"]`).closest('td');#}
{#                    if (timeCellForDay) {#}
{#                        timeCellForDay.appendChild(newPairGroup);#}
{#                    } else {#}
{#                        console.error("Не удалось найти ячейку для добавления новой пары времени.");#}
{#                    }#}
{#                }#}
{#            });#}
{#        });#}
{##}
{#        // --- Обработка кнопки "- Удалить пару" ---#}
{#        document.querySelectorAll('.remove-pair-btn').forEach(btn => {#}
{#            btn.addEventListener('click', function () {#}
{#                const dayId = this.getAttribute('data-day-id');#}
{#                const elements = getDayElements(dayId);#}
{##}
{#                const allPairGroups = elements.timePairGroups;#}
{##}
{#                if (allPairGroups.length > 1) {#}
{#                    allPairGroups[allPairGroups.length - 1].remove();#}
{#                } else if (allPairGroups.length === 1) {#}
{#                    // Если осталась одна пара, просто очищаем её#}
{#                    const lastPairGroup = allPairGroups[0];#}
{#                    lastPairGroup.querySelector('.entry-input').value = '';#}
{#                    lastPairGroup.querySelector('.entry-display').textContent = '-';#}
{#                    lastPairGroup.querySelector('.exit-input').value = '';#}
{#                    lastPairGroup.querySelector('.exit-display').textContent = '-';#}
{#                }#}
{#            });#}
{#        });#}
{#    });#}
{#</script>#}