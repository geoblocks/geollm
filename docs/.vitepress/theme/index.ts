import DefaultTheme from 'vitepress/theme'
import { useRouter } from 'vitepress'
import { onMounted } from 'vue'
import './custom.css'

export default {
  extends: DefaultTheme,
  setup() {
    const router = useRouter()
    // VitePress's client-side router intercepts all <a> clicks, including links
    // to /api/ (pdoc static HTML). Force a full browser navigation for those so
    // the plain HTML files are loaded directly instead of hitting the router.
    router.onBeforeRouteChange = (to: string) => {
      if (to.includes('/api/')) {
        window.location.href = to
        return false
      }
    }
  },
}

