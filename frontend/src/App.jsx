import { useEffect, useState } from 'react'
import { getMeta, getRecommendations } from './api.js'
import Landing from './components/Landing.jsx'
import ProfileForm from './components/ProfileForm.jsx'
import Dashboard from './components/Dashboard.jsx'

const EMPTY_PROFILE = {
  technical_skills: [],
  soft_skills: [],
  interests: [],
  education_level: 'bachelor',
  years_experience: 0,
  bio: '',
}

// The profile and latest results are remembered in this browser, so a returning visitor
// does not have to build the profile again.
const PROFILE_KEY = 'waypoint.profile.v1'
const RESULTS_KEY = 'waypoint.results.v2'
const VIEWS = ['profile', 'results']

// Browser storage can be unavailable (private windows, blocked site data); never let it break the app.
function readStored(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key)
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback
  } catch {
    return fallback
  }
}

function writeStored(key, value) {
  try {
    if (value === null) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Ignore: persistence is a convenience only.
  }
}

// Views live in the URL hash (#/profile, #/results) so the browser's back button works.
const viewFromHash = () => {
  const name = window.location.hash.replace(/^#\/?/, '')
  return VIEWS.includes(name) ? name : 'home'
}

const formatWhen = (value) => {
  try {
    return new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
  } catch {
    return ''
  }
}

function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden="true">
        <rect width="32" height="32" rx="9" fill="#2F6BFF" />
        <path d="M9 22 16 8l7 14-7-4z" fill="#fff" />
      </svg>
      <span className="font-display text-xl font-extrabold tracking-tight">Waypoint</span>
    </span>
  )
}

export default function App() {
  const [profile, setProfile] = useState(() => readStored(PROFILE_KEY, EMPTY_PROFILE))
  const [results, setResults] = useState(() => readStored(RESULTS_KEY, null))
  const [view, setView] = useState(viewFromHash)
  const [meta, setMeta] = useState(null)
  const [metaError, setMetaError] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const onHashChange = () => setView(viewFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => {
    let cancelled = false
    getMeta()
      .then((data) => !cancelled && setMeta(data))
      .catch((err) => !cancelled && setMetaError(err.message))
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => writeStored(PROFILE_KEY, profile), [profile])
  useEffect(() => writeStored(RESULTS_KEY, results), [results])

  function go(next) {
    window.location.hash = next === 'home' ? '/' : `/${next}`
    setView(next)
    window.scrollTo({ top: 0 })
  }

  function goToSection(id) {
    const scroll = () => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    if (view !== 'home') {
      go('home')
      setTimeout(scroll, 60)
    } else {
      scroll()
    }
  }

  async function findCareers() {
    setLoading(true)
    setError('')
    try {
      const data = await getRecommendations({ ...profile, years_experience: Number(profile.years_experience) || 0 })
      setResults(data)
      go('results')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function startOver() {
    setProfile(EMPTY_PROFILE)
    setResults(null)
    setError('')
    go('profile')
  }

  const showResults = view === 'results' && results
  const navLinks = [
    ['features', 'Features'],
    ['how', 'How it works'],
    ['careers', 'Careers'],
    ['faq', 'FAQ'],
  ]

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-edge/70 bg-night/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <button type="button" onClick={() => go('home')} aria-label="Waypoint home" className="rounded-lg">
            <Logo />
          </button>

          <nav aria-label="Sections" className="hidden items-center gap-1 md:flex">
            {navLinks.map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => goToSection(id)}
                className="rounded-full px-3.5 py-2 text-sm font-medium text-fog/70 hover:bg-white/5 hover:text-fog"
              >
                {label}
              </button>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            {showResults ? (
              <>
                <button type="button" className="btn-quiet" onClick={() => go('profile')}>
                  Edit profile
                </button>
                <button type="button" className="btn-quiet hidden sm:inline-flex" onClick={startOver}>
                  Start over
                </button>
              </>
            ) : (
              <>
                {results && (
                  <button type="button" className="btn-quiet hidden sm:inline-flex" onClick={() => go('results')}>
                    My results
                  </button>
                )}
                {view === 'home' && (
                  <button type="button" className="btn-primary" onClick={() => go('profile')}>
                    Build my profile
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </header>

      {metaError && (
        <div role="alert" className="border-b border-amber/30 bg-amber/10 px-4 py-2.5 text-center text-sm text-amber">
          {metaError}
        </div>
      )}

      {view === 'home' && (
        <Landing
          meta={meta}
          returning={Boolean(results)}
          onStart={() => go(results ? 'results' : 'profile')}
          onSection={goToSection}
        />
      )}

      {view !== 'home' && (
        <main className="relative">
          <div className="glow-top pointer-events-none absolute inset-x-0 top-0 h-72" aria-hidden="true" />
          <div className="relative mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
            {showResults ? (
              <>
                {results.generated_at && (
                  <p className="mb-6 text-sm text-fog/55">
                    Results from {formatWhen(results.generated_at)}. Your profile and these results are saved in this
                    browser.
                  </p>
                )}
                <Dashboard key={results.generated_at} results={results} salaryNote={meta?.salary_note} />
              </>
            ) : (
              <ProfileForm
                profile={profile}
                onChange={setProfile}
                meta={meta}
                onSubmit={findCareers}
                loading={loading}
                error={error}
              />
            )}
          </div>
        </main>
      )}

      <footer className="border-t border-edge">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr]">
          <div>
            <Logo />
            <p className="mt-3 max-w-sm text-sm leading-relaxed text-fog/55">
              Career recommendations from your skills, interests and experience, with the gap to close for each
              role.
            </p>
          </div>
          <div>
            <h2 className="text-sm font-semibold text-fog/80">Explore</h2>
            <ul className="mt-3 space-y-2 text-sm text-fog/60">
              {navLinks.map(([id, label]) => (
                <li key={id}>
                  <button type="button" onClick={() => goToSection(id)} className="rounded hover:text-fog">
                    {label}
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h2 className="text-sm font-semibold text-fog/80">About the data</h2>
            <p className="mt-3 text-sm leading-relaxed text-fog/55">
              Salary and growth figures come from a demo dataset and are illustrative estimates, not live
              labour-market data.
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}
