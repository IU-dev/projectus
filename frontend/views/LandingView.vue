<script setup>
import { pageProps } from './props.js'
defineProps(pageProps)

const benefits = [
  { title: 'Проекты под рукой', text: 'Ваши проекты и заявки собраны в одном кабинете. Легко перейти к нужной команде и продолжить работу.' },
  { title: 'Команда рядом', text: 'Приглашайте зарегистрированных пользователей по email и управляйте составом команды проекта.' },
  { title: 'Доступ под контролем', text: 'Назначайте права каждому участнику отдельно. Вы решаете, кому доступен проект и кто может менять его сведения.' },
]
const steps = [
  { title: 'Создайте аккаунт', text: 'Зарегистрируйтесь и подтвердите email.' },
  { title: 'Предложите проект', text: 'Подайте заявку. После одобрения появится рабочее пространство проекта.' },
  { title: 'Пригласите команду', text: 'Добавьте участников и настройте их доступ.' },
]
</script>

<template>
  <div class="landing">
    <section class="landing-hero" aria-labelledby="landing-title">
      <div class="landing-intro">
        <p class="landing-label">PROJECTUS · ОТ ИДЕИ К РЕЗУЛЬТАТУ</p>
        <h1 id="landing-title">Ваш проект.<br><span>Команда рядом.</span></h1>
        <p class="landing-lead">
          Рабочее пространство для социальных инициатив и других командных проектов.
          Соберите людей вокруг своей идеи и начните работу вместе.
        </p>
        <div class="actions">
          <a class="button" href="/register/">Начать работу</a>
          <a class="button secondary" href="/login/">Войти в аккаунт</a>
        </div>
      </div>
      <aside class="panel landing-start" aria-label="Как начать">
        <h2>От идеи до команды — три шага</h2>
        <ol class="landing-steps">
          <li v-for="(step, index) in steps" :key="step.title">
            <span class="step-number" aria-hidden="true">{{ index + 1 }}</span>
            <div><h3>{{ step.title }}</h3><p>{{ step.text }}</p></div>
          </li>
        </ol>
      </aside>
    </section>
    <section aria-labelledby="benefits-title">
      <h2 id="benefits-title">Основа для совместной работы</h2>
      <div class="landing-benefits">
        <article v-for="benefit in benefits" :key="benefit.title" class="panel">
          <h3>{{ benefit.title }}</h3>
          <p class="muted">{{ benefit.text }}</p>
        </article>
      </div>
    </section>
    <section class="panel landing-roadmap" aria-labelledby="roadmap-title">
      <div>
        <span class="tag">В разработке</span>
        <h2 id="roadmap-title">Больше возможностей для вашего проекта</h2>
        <p class="muted">Показатели результатов, планирование мероприятий, бюджет и договоры — следующие этапы Projectus.</p>
      </div>
      <a href="/register/">Присоединиться →</a>
    </section>
  </div>
</template>

<style scoped>
.landing { padding: 12px 0; }
.landing-hero { display: grid; grid-template-columns: 1.2fr 1fr; align-items: center; gap: 48px; padding: 24px 0 40px; }
.landing-label { color: var(--green); font-size: 11px; font-weight: 650; letter-spacing: 1.3px; margin-bottom: 16px; }
.landing-intro h1 { font-size: clamp(32px, 4vw, 48px); line-height: 1.12; letter-spacing: -1.8px; margin-bottom: 20px; }
.landing-intro h1 span { color: var(--green); }
.landing-lead { max-width: 490px; font-size: 16px; line-height: 1.6; color: var(--muted); margin-bottom: 24px; }
.landing-start { padding: 24px; }
.landing-start h2 { margin-bottom: 20px; }
.landing-steps { list-style: none; padding: 0; margin: 0; display: grid; gap: 20px; }
.landing-steps li { display: flex; gap: 12px; }
.step-number { flex: 0 0 28px; height: 28px; display: grid; place-items: center; border-radius: 9px; color: var(--green); background: var(--mint); font-size: 12px; font-weight: 650; }
.landing h3 { font-size: 15px; line-height: 1.4; margin: 0 0 6px; }
.landing-steps p { color: var(--muted); font-size: 13px; margin: 0; }
.landing-benefits { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.landing-benefits .panel { padding: 20px; }
.landing-benefits p { margin: 0; font-size: 13px; }
.landing-roadmap { margin-top: 24px; padding: 20px; display: flex; align-items: center; justify-content: space-between; gap: 24px; }
.landing-roadmap h2 { margin: 10px 0 6px; }
.landing-roadmap p { margin: 0; font-size: 13px; }
.landing-roadmap a { flex-shrink: 0; }
@media (max-width: 800px) {
  .landing-hero { grid-template-columns: 1fr; gap: 24px; padding: 8px 0 28px; }
  .landing-lead { max-width: none; }
  .landing-benefits { grid-template-columns: 1fr; gap: 12px; }
  .landing-roadmap { flex-direction: column; align-items: flex-start; gap: 12px; }
}
</style>
