const dates = new Intl.DateTimeFormat('ru-RU')
const timestamps = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short' })

export const date = value => value ? dates.format(new Date(value)) : '—'
export const dateTime = value => value ? timestamps.format(new Date(value)) : '—'
export const permissionLabels = permissions => permissions.map(p => p.label).join(' · ')
