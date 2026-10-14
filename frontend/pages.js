import DashboardView from './views/DashboardView.vue'
import LandingView from './views/LandingView.vue'
import MyContractsView from './views/MyContractsView.vue'
import ProjectView from './views/ProjectView.vue'
import ProjectSectionView from './views/ProjectSectionView.vue'
import IndicatorsView from './views/IndicatorsView.vue'
import IndicatorFormView from './views/IndicatorFormView.vue'
import EventsView from './views/EventsView.vue'
import EventDetailView from './views/EventDetailView.vue'
import MembersView from './views/MembersView.vue'
import OperationsView from './views/OperationsView.vue'
import ApplicationsView from './views/ApplicationsView.vue'
import UsersView from './views/UsersView.vue'
import StaffPermissionsView from './views/StaffPermissionsView.vue'
import AuditView from './views/AuditView.vue'
import FormView from './views/FormView.vue'
import LoginView from './views/LoginView.vue'
import ConfirmationView from './views/ConfirmationView.vue'
import MessageView from './views/MessageView.vue'
import BudgetView from './views/BudgetView.vue'
import PaymentView from './views/PaymentView.vue'

export const pages = {
  landing: { component: LandingView, title: 'Projectus — пространство для ваших проектов' },
  dashboard: { component: DashboardView, title: 'Мои проекты' },
  my_contracts: { component: MyContractsView, title: 'Мои договоры' },
  project: { component: ProjectView, title: 'Проект' },
  project_indicators: { component: IndicatorsView, title: 'Показатели' },
  indicator_create: { component: IndicatorFormView, title: 'Новый показатель' },
  indicator_edit: { component: IndicatorFormView, title: 'Редактирование показателя' },
  project_events: { component: EventsView, title: 'Мероприятия' },
  event_create: { component: FormView, title: 'Новое мероприятие' },
  event_plan: { component: FormView, title: 'План мероприятия' },
  event_result: { component: FormView, title: 'Факт проведения мероприятия' },
  event_detail: { component: EventDetailView, title: 'Мероприятие' },
  event_confirm: { component: ConfirmationView, title: 'Подтверждение проведения' },
  project_budget: { component: BudgetView, title: 'Бюджет' },
  budget_revision: { component: BudgetView, title: 'Версия сметы' },
  payment_detail: { component: PaymentView, title: 'Платёж' },
  project_contracts: { component: ProjectSectionView, title: 'Договоры' },
  members: { component: MembersView, title: 'Команда и доступ' },
  operations: { component: OperationsView, title: 'Управление сервисом' },
  applications: { component: ApplicationsView, title: 'Заявки на проекты' },
  users: { component: UsersView, title: 'Пользователи' },
  staff_permissions: { component: StaffPermissionsView, title: 'Полномочия сотрудников' },
  audit: { component: AuditView, title: 'Журнал действий' },
  login: { component: LoginView, title: 'Вход в Projectus' },
  register: { component: FormView, title: 'Регистрация' },
  resend_verification: { component: FormView, title: 'Подтверждение email' },
  request_project: { component: FormView, title: 'Новый проект' },
  project_edit: { component: FormView, title: 'Сведения о проекте' },
  member_edit: { component: FormView, title: 'Права участника', showSubtitle: true },
  decide_application: { component: FormView, title: 'Решение по заявке', showSubtitle: true },
  password_change: { component: FormView, title: 'Смена пароля', button: 'Сохранить пароль' },
  password_reset: { component: FormView, title: 'Восстановление пароля', button: 'Отправить ссылку' },
  password_reset_confirm: { component: FormView, title: 'Новый пароль', button: 'Сохранить пароль' },
  verify_email: { component: ConfirmationView, title: 'Подтверждение email' },
  accept_invitation: { component: ConfirmationView, title: 'Приглашение' },
  password_reset_done: {
    component: MessageView,
    title: 'Проверьте почту',
    message: 'Если этот email зарегистрирован, мы отправили ссылку для восстановления пароля.',
    href: '/login/', link: 'Вернуться ко входу',
  },
  password_change_done: {
    component: MessageView, title: 'Пароль изменен',
    href: '/', link: 'Вернуться к проектам',
  },
  password_reset_complete: {
    component: MessageView, title: 'Пароль изменен',
    href: '/login/', link: 'Войти',
  },
}

for (const name of ['budget_clone', 'budget_template', 'budget_section_create', 'budget_section_edit',
  'budget_line_create', 'budget_line_edit', 'budget_publish', 'budget_submit', 'budget_approve',
  'budget_reject', 'budget_settings', 'receipt_create', 'payment_create', 'payment_edit',
  'payment_submit', 'payment_approve', 'payment_reject', 'payment_execute',
  'budget_section_remove', 'budget_line_remove']) {
  pages[name] = { component: FormView, title: 'Бюджет' }
}

const unavailable = {
  component: MessageView, title: 'Страница недоступна',
  href: '/', link: 'Мои проекты',
}

export function getPage(name) {
  return pages[name] || unavailable
}
