import { Link } from 'react-router'
import { Page } from '../components/ui'

export default function NotFoundPage() {
  return (
    <Page title="Not found">
      <p>
        That page doesn't exist. <Link to="/">Back to this week's games</Link>.
      </p>
    </Page>
  )
}
