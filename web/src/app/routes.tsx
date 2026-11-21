/* oxlint-disable react/only-export-components -- route table; HMR on this file is not needed */
import { lazy, Suspense, type ComponentType } from 'react'
import { Navigate, useLocation, type RouteObject } from 'react-router'
import { Loading } from '../components/ui'
import { isHidden } from '../lib/hiddenPages'
import { Layout } from './Layout'
import { RouteError } from './RouteError'

// Each page is its own chunk (Build pulls in the evaluator and the 1.3 MB matrix only when visited).
const page = (load: () => Promise<{ default: ComponentType }>) => {
  const C = lazy(load)
  return (
    <Suspense fallback={<Loading what="page" />}>
      <C />
    </Suspense>
  )
}

// a hidden page answers like one that doesn't exist; `isHidden` says why
const hidable = (path: string, load: () => Promise<{ default: ComponentType }>) =>
  page(() => (isHidden(path) ? import('../pages/NotFound') : load()))

// the weekly page moved from /betting/week to /betting; keep ?tab= links working
function WeekRedirect() {
  const { search } = useLocation()
  return <Navigate to={{ pathname: '/betting', search }} replace />
}

export const routes: RouteObject[] = [
  {
    element: <Layout />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: page(() => import('../pages/Slate')) },
      { path: 'week/:season/:week', element: page(() => import('../pages/Slate')) },
      { path: 'game/:id', element: page(() => import('../pages/Game')) },
      { path: 'league', element: page(() => import('../pages/League')) },
      { path: 'team', element: page(() => import('../pages/Teams')) },
      { path: 'team/:code', element: page(() => import('../pages/Team')) },
      { path: 'tracker', element: page(() => import('../pages/Tracker')) },
      { path: 'hypotheses', element: page(() => import('../pages/Hypotheses')) },
      { path: 'coaches', element: hidable('/coaches', () => import('../pages/Coaches')) },
      { path: 'build', element: hidable('/build', () => import('../pages/Build')) },
      { path: 'betting', element: page(() => import('../pages/Betting')) },
      { path: 'betting/week', element: <WeekRedirect /> },
      { path: 'season/:year', element: page(() => import('../pages/Season')) },
      { path: 'method', element: page(() => import('../pages/Method')) },
      // the nav's labels as URLs, which visitors type (both personas, 2026-11-15 walk)
      { path: 'teams', element: <Navigate to="/team" replace /> },
      { path: 'history', element: <Navigate to="/hypotheses" replace /> },
      { path: '*', element: page(() => import('../pages/NotFound')) },
    ],
  },
]
