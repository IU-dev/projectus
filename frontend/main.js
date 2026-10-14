import { createApp } from 'vue'
import App from './App.vue'
import './styles/app.css'

createApp(App, { initial: JSON.parse(document.getElementById('projectus-bootstrap').textContent) }).mount('#app')
