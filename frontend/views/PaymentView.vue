<script setup>
import { computed } from 'vue'
import PageForm from '../components/PageForm.vue'
import { pageProps } from './props.js'
const props = defineProps(pageProps)
defineEmits(['navigate'])
const payment = computed(() => props.data.payment)
const budgetBase = computed(() => `/projects/${props.data.project.id}/budget/`)
const base = computed(() => `${budgetBase.value}payments/${payment.value.id}/`)
</script>
<template>
  <section>
    <a :href="budgetBase + '?tab=payments'">← Платежи проекта</a>
    <div class="section-heading"><h1>Заявка №{{ payment.number }} · {{ payment.amount }} ₽</h1><span class="tag">{{ payment.status_label }}</span></div>
    <section class="panel"><h2>{{ payment.recipient_name }}</h2><p>{{ payment.section_path }} / {{ payment.line_name }}</p><p class="budget-text">{{ payment.description }}</p><p class="muted">Автор: {{ payment.author }} · {{ payment.created_at }}</p>
      <dl class="payment-details"><template v-for="[label, key] in [['Тип получателя', 'recipient_type'], ['ИНН', 'inn'], ['КПП', 'kpp'], ['Расчётный счёт', 'account'], ['Банк', 'bank_name'], ['БИК', 'bik'], ['Корреспондентский счёт', 'correspondent_account']]" :key="key"><dt>{{ label }}</dt><dd>{{ payment[key] || '—' }}</dd></template></dl>
      <p class="muted">Банковские реквизиты {{ payment.bank_details_required ? 'обязательны' : 'необязательны' }} для этой заявки.</p>
      <div class="budget-actions"><template v-if="payment.can_edit"><a :href="base + 'edit/'" class="button secondary small">Редактировать</a><a :href="base + 'submit/'" class="button small">Отправить на согласование</a><button class="quiet danger" :disabled="busy" @click="$emit('navigate', base + 'remove/', {})">Удалить черновик</button></template><template v-if="payment.can_vote"><a :href="base + 'approve/'" class="button small">Одобрить</a><a :href="base + 'reject/'">Отклонить</a></template><a v-if="payment.can_execute" :href="base + 'execute/'" class="button small">Исполнить платёж</a></div>
      <template v-if="payment.status === 'executed'"><h3>Исполнение</h3><p>Дата платежного документа: {{ payment.payment_document_date }} · Номер: {{ payment.payment_document_number }}</p><p class="budget-text">Назначение платежа: {{ payment.payment_purpose }}</p><p class="muted">{{ payment.executor }} · {{ payment.executed_at }}</p></template>
    </section>
    <section class="panel"><h2>Связанные мероприятия</h2><p v-for="event in payment.events" :key="event.id">{{ event.title }}</p><p v-if="!payment.events.length" class="muted">Не выбраны.</p><h2>Согласования</h2><p>Согласовано {{ payment.approved_count }} из {{ payment.approver_count }} конкретных согласующих</p><div class="table-wrap"><table><thead><tr><th>Согласующий</th><th>Решение</th><th>Комментарий</th><th>Дата</th></tr></thead><tbody><tr v-for="vote in payment.approvals" :key="vote.id"><td>{{ vote.name }}</td><td>{{ vote.status_label }}</td><td>{{ vote.comment }}</td><td>{{ vote.decided_at || '—' }}</td></tr></tbody></table></div></section>
    <section class="panel"><h2>Подтверждающие файлы</h2><div v-for="file in payment.attachments" :key="file.id" class="budget-actions"><a :href="base + `attachments/${file.id}/download/`" download>{{ file.name }}</a><small class="muted">{{ file.size }} байт · {{ file.author }}</small><button v-if="file.can_remove" class="quiet danger" :disabled="busy" @click="$emit('navigate', base + `attachments/${file.id}/remove/`, {})">Удалить файл</button></div><p v-if="!payment.attachments.length" class="muted">Файлы пока не прикреплены.</p><div v-if="data.form" class="payment-upload"><PageForm :schema="data.form" :busy="busy" button="Прикрепить файл" @submit="$emit('navigate', base + 'attachments/', $event)" /></div></section>
  </section>
</template>
