<script setup>
import { computed } from 'vue'
import { pageProps } from './props.js'
const props = defineProps(pageProps)
defineEmits(['navigate'])
const budget = computed(() => props.data.budget)
const base = computed(() => `/projects/${props.data.project.id}/budget/`)
const revisionBase = computed(() => `${base.value}revisions/${budget.value.revision.id}/`)
const columns = [['total_amount', 'Общая стоимость'], ['cofinancing_amount', 'Софинансирование'], ['requested_amount', 'Запрашивается'], ['reserved', 'Согласовано'], ['executed', 'Исполнено'], ['remaining', 'Остаток']]
const metrics = computed(() => [
  ['Общая стоимость', budget.value.totals.total_amount], ['Запрашивается', budget.value.totals.requested_amount],
  ['Софинансирование', budget.value.totals.cofinancing_amount], ['Поступило', budget.value.balances.received],
  ['Зарезервировано', budget.value.balances.reserved], ['Исполнено', budget.value.balances.executed], ['Доступно', budget.value.balances.available],
])
const money = value => String(value ?? '0.00').replace('.', ',').replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
</script>

<template>
  <section v-if="budget">
    <div class="section-heading"><h1>Бюджет</h1><a v-if="budget.permissions.edit_budget" :href="base + 'settings/'">Настройки</a></div>
    <div class="budget-metrics panel"><span v-for="[label, value] in metrics" :key="label"><small>{{ label }}</small><strong>{{ money(value) }} ₽</strong></span></div>
    <p class="muted">Остаток на счёте: {{ money(budget.balances.account_balance) }} ₽</p>
    <nav class="budget-tabs" aria-label="Бюджет проекта"><a v-for="[tab, label] in [['estimate', 'Смета'], ['payments', 'Платежи'], ['receipts', 'Поступления'], ['history', 'История сметы']]" :key="tab" :href="base + '?tab=' + tab" :aria-current="data.tab === tab ? 'page' : undefined">{{ label }}</a></nav>
    <section v-if="data.tab === 'estimate'" class="panel">
      <div class="section-heading"><h2>Версия №{{ budget.revision.number }} · {{ budget.revision.kind_label }}</h2><span class="tag">{{ budget.revision.status_label }}</span></div>
      <p v-if="budget.revision.reason">{{ budget.revision.reason }}</p>
      <div class="budget-actions">
        <template v-if="budget.editable"><a :href="revisionBase + 'sections/new/'" class="button secondary small">Добавить статью</a><a :href="revisionBase + 'lines/new/'" class="button secondary small">Добавить строку</a>
          <template v-if="budget.revision.kind === 'initial'"><a v-if="!budget.rows.length" :href="revisionBase + 'template/'">Применить шаблон</a><a :href="revisionBase + 'publish/'" class="button small">Опубликовать</a></template>
          <a v-else :href="revisionBase + 'submit/'" class="button small">Отправить на согласование</a>
        </template>
        <a v-if="budget.can_clone" :href="base + 'revisions/new/'" class="button secondary small">Создать изменение / перенос</a>
        <template v-if="budget.revision.status === 'pending' && budget.permissions.approve_budget_changes"><a :href="revisionBase + 'approve/'" class="button small">Согласовать изменение</a><a :href="revisionBase + 'reject/'">Отклонить</a></template>
      </div>
      <div class="table-wrap"><table class="budget-table"><thead><tr><th>Статья / расход</th><th v-for="[, label] in columns" :key="label">{{ label }}</th><th>Действия</th></tr></thead><tbody>
        <tr v-for="row in budget.rows" :key="row.type + row.id" :class="{ 'budget-section': row.type === 'section' }">
          <td :style="{ paddingLeft: `${12 + row.depth * 16}px` }"><strong v-if="row.type === 'section'">{{ row.name }}</strong><span v-else>{{ row.name }}</span><small v-if="row.quantity" class="muted budget-note">{{ money(row.unit_price) }} ₽ × {{ row.quantity }} {{ row.unit_name }}</small><details v-if="row.comment || row.explanation"><summary>Комментарий</summary><p>{{ row.comment || row.explanation }}</p></details></td>
          <td v-for="[key] in columns" :key="key" class="budget-money">{{ money(row[key]) }}</td>
          <td><div v-if="budget.editable" class="budget-row-actions"><a :href="revisionBase + (row.type === 'line' ? 'lines/' : 'sections/') + row.id + '/edit/'">Изменить</a><button v-if="row.can_remove" class="quiet danger" :disabled="busy" @click="$emit('navigate', revisionBase + (row.type === 'line' ? 'lines/' : 'sections/') + row.id + '/remove/', {})">{{ row.type === 'line' ? 'Удалить' : 'Удалить статью со строками' }}</button></div></td>
        </tr><tr v-if="!budget.rows.length"><td colspan="8" class="muted">Добавьте статьи и строки сметы вручную или примените шаблон.</td></tr>
      </tbody><tfoot><tr><th>Всего</th><th v-for="[key] in columns" :key="key" class="budget-money">{{ money(budget.totals[key]) }}</th><th></th></tr></tfoot></table></div>
    </section>
    <section v-else-if="data.tab === 'payments'" class="panel">
      <div class="section-heading"><h2>Платежи</h2><a v-if="budget.permissions.prepare_payments" :href="base + 'payments/new/'" class="button small">Новая заявка</a></div>
      <div class="table-wrap"><table><thead><tr><th>Заявка</th><th>Получатель / основание</th><th>Строка сметы</th><th>Сумма</th><th>Статус / согласования</th><th>Действия</th></tr></thead><tbody>
        <tr v-for="payment in budget.payments" :key="payment.id"><td><a :href="base + `payments/${payment.id}/`">№{{ payment.number }}</a></td><td>{{ payment.recipient_name }}<small class="budget-note">{{ payment.payment_purpose || payment.description }}</small></td><td>{{ payment.section_path }}<small class="budget-note">{{ payment.line_name }}</small></td><td class="budget-money">{{ money(payment.amount) }} ₽</td><td><span class="tag">{{ payment.status_label }}</span><small class="budget-note">Согласовано {{ payment.approved_count }} из {{ payment.approver_count }} конкретных согласующих</small></td><td><div class="budget-row-actions"><a :href="base + `payments/${payment.id}/`">Открыть</a><a v-if="payment.can_edit" :href="base + `payments/${payment.id}/edit/`">Изменить</a><a v-if="payment.can_vote" :href="base + `payments/${payment.id}/approve/`">Одобрить</a><a v-if="payment.can_execute" :href="base + `payments/${payment.id}/execute/`">Исполнить</a></div></td></tr>
        <tr v-if="!budget.payments.length"><td colspan="6" class="muted">Заявок пока нет.</td></tr>
      </tbody></table></div>
    </section>
    <section v-else-if="data.tab === 'receipts'" class="panel"><div class="section-heading"><h2>Поступления</h2><a v-if="budget.permissions.record_receipts" :href="base + 'receipts/new/'" class="button small">Добавить поступление</a></div><p class="muted">Сохранённые поступления нельзя изменить или удалить.</p><div class="table-wrap"><table><thead><tr><th>Дата</th><th>Сумма</th><th>Назначение</th><th>Автор</th></tr></thead><tbody><tr v-for="receipt in budget.receipts" :key="receipt.id"><td>{{ receipt.date }}</td><td class="budget-money">{{ money(receipt.amount) }} ₽</td><td>{{ receipt.comment }}</td><td>{{ receipt.author }}</td></tr><tr v-if="!budget.receipts.length"><td colspan="4">Поступлений пока нет.</td></tr></tbody></table></div></section>
    <section v-else class="panel"><h2>История сметы</h2><div class="table-wrap"><table><thead><tr><th>Версия</th><th>Вид / статус</th><th>Причина</th><th>Автор</th><th>Решение</th></tr></thead><tbody><tr v-for="revision in budget.history" :key="revision.id"><td><a :href="base + `revisions/${revision.id}/`">№{{ revision.number }}</a></td><td>{{ revision.kind_label }}<small class="budget-note">{{ revision.status_label }}</small></td><td>{{ revision.reason }}</td><td>{{ revision.author }}<small class="budget-note">{{ revision.created_at }}</small></td><td>{{ revision.decider }}<small class="budget-note">{{ revision.decided_at }}</small></td></tr></tbody></table></div></section>
  </section>
</template>
