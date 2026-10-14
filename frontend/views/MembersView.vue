<script setup>
import { computed } from 'vue'
import PageForm from '../components/PageForm.vue'
import { pageProps } from './props.js'
import { dateTime, permissionLabels } from '../lib/format.js'
const props = defineProps(pageProps)
defineEmits(['submit', 'navigate'])
const projectPath = computed(() => `/projects/${props.data.project.id}/`)
</script>

<template>
  <section>
    <a class="back" :href="projectPath">← {{ data.project.title }}</a>
    <h1>Команда и доступ</h1>
    <div class="detail-grid">
      <section class="panel">
        <h2>Участники</h2>
        <div class="member-row">
          <strong>{{ data.project.owner.email }}</strong><span class="tag">Владелец</span>
        </div>
        <div v-for="member in data.members" :key="member.id" class="member-row">
          <div>
            <strong>{{ member.email }}</strong>
            <p class="muted">{{ permissionLabels(member.permissions) || 'Просмотр карточки' }}</p>
            <a :href="projectPath + `members/${member.id}/`">Настроить права</a>
          </div>
          <button
            class="quiet danger"
            :disabled="busy"
            @click="$emit('navigate', projectPath + `members/${member.id}/remove/`, {})"
          >Отозвать доступ</button>
        </div>
        <p v-if="!data.members.length" class="muted">Нет участников.</p>
      </section>
      <section class="panel">
        <h2>Пригласить участника</h2>
        <p class="muted">Срок приглашения — 7 дней.</p>
        <PageForm :schema="data.form" :busy="busy" button="Отправить приглашение" @submit="$emit('submit', $event)" />
      </section>
    </div>
    <h2>Приглашения</h2>
    <div v-for="invitation in data.invitations" :key="invitation.id" class="panel invitation">
      <div>
        <strong>{{ invitation.email }}</strong>
        <p class="muted">До {{ dateTime(invitation.expires_at) }}</p>
        <input :value="invitation.link" readonly :aria-label="`Ссылка приглашения ${invitation.email}`">
      </div>
      <button
        class="quiet danger"
        :disabled="busy"
        @click="$emit('navigate', projectPath + `invitations/${invitation.id}/revoke/`, {})"
      >Отозвать</button>
    </div>
    <p v-if="!data.invitations.length" class="muted">Нет активных приглашений.</p>
  </section>
</template>
