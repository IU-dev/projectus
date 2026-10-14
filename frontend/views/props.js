export const pageProps = {
  data: { type: Object, required: true },
  user: Object,
  busy: Boolean,
  options: { type: Object, default: () => ({}) },
}
