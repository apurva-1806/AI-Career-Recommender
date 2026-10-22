import { useEffect, useMemo, useState } from 'react'
import { getCareers, getRecommendations } from '../api.js'
import { formatSalary } from './CareerCard.jsx'

const SAMPLE_PROFILE = {
  technical_skills: ['Python', 'SQL', 'Statistics', 'Data Visualization'],
  soft_skills: ['Curiosity'],
  interests: ['AI Research'],
  education_level: 'bachelor',
  years_experience: 2,
  bio: '',
  save_profile: false,
}

const Accent = ({ children }) => <span className="text-brand-light">{children}</span>

function Icon({ name }) {
  const paths = {
    vector: 'M4 18 10 6l4 8 2-4 4 8M4 18h16',
    gap: 'M4 7h9M4 12h16M4 17h6M17 7h3M14 17h6',
    route: 'M6 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm12-10a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM8 17h5a3 3 0 0 0 3-3v-1a3 3 0 0 0-3-3h-2a3 3 0 0 1-3-3v0',
  }
  return (
    <span className="grid h-11 w-11 place-items-center rounded-xl border border-brand/40 bg-brand/15 text-brand-light">
      <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d={paths[name]} />
      </svg>
    </span>
  )
}

/** Runs a fixed sample profile through the real API so the hero shows actual engine output. */
function LiveExample() {
  const [state, setState] = useState({ status: 'loading', items: [] })

  useEffect(() => {
    let cancelled = false
    getRecommendations(SAMPLE_PROFILE, 3)
      .then((data) => !cancelled && setState({ status: 'ready', items: data.recommendations }))
      .catch(() => !cancelled && setState({ status: 'offline', items: [] }))
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="card relative p-5 shadow-glow sm:p-6">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-bold">Example profile</h2>
        {state.status === 'ready' && (
          <span className="flex items-center gap-1.5 text-sm text-mint">
            <span className="h-1.5 w-1.5 rounded-full bg-mint" aria-hidden="true" />
            Live result
          </span>
        )}
      </div>
      <ul className="mt-3 flex flex-wrap gap-1.5">
        {[...SAMPLE_PROFILE.technical_skills, ...SAMPLE_PROFILE.interests].map((skill) => (
          <li key={skill} className="chip-have">{skill}</li>
        ))}
      </ul>

      <div className="mt-5 border-t border-edge pt-4">
        {state.status === 'loading' && <p className="py-6 text-sm text-fog/55">Matching against the career set</p>}

        {state.status === 'offline' && (
          <ul className="space-y-3 text-[15px] text-fog/75">
            {['Top five careers with a match score', 'Skills you have and skills to build', 'Learning links, salary range and outlook'].map((line) => (
              <li key={line} className="flex gap-3">
                <svg viewBox="0 0 20 20" className="mt-0.5 h-5 w-5 shrink-0 text-brand-light" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <path d="m5 10 3.5 3.5L15 7" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {line}
              </li>
            ))}
          </ul>
        )}

        {state.status === 'ready' && (
          <ol className="space-y-4">
            {state.items.map((item) => (
              <li key={item.career.id}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-[15px] font-semibold">{item.career.title}</span>
                  <span className="font-display text-lg font-bold tabular-nums">{Math.round(item.match_score)}%</span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/10">
                  <div className="h-full rounded-full bg-gradient-to-r from-brand to-brand-light" style={{ width: `${item.match_score}%` }} />
                </div>
                <p className="mt-1.5 text-sm text-fog/55">
                  {item.matched_skills.length} of {item.matched_skills.length + item.missing_skills.length} core skills.
                  {item.missing_skills.length > 0 && ` Next: ${item.missing_skills.slice(0, 2).join(', ')}.`}
                </p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  )
}

function CareerExplorer({ onStart }) {
  const [careers, setCareers] = useState(null)
  const [failed, setFailed] = useState(false)
  const [industry, setIndustry] = useState('All')
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    let cancelled = false
    getCareers()
      .then((data) => !cancelled && setCareers(data))
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
    }
  }, [])

  const industries = useMemo(() => {
    const counts = {}
    ;(careers || []).forEach((c) => {
      counts[c.industry] = (counts[c.industry] || 0) + 1
    })
    return Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([name]) => name)
  }, [careers])

  const filtered = (careers || []).filter((c) => industry === 'All' || c.industry === industry)
  const visible = expanded ? filtered : filtered.slice(0, 6)

  return (
    <section id="careers" className="scroll-mt-20 border-t border-edge/60 py-16 sm:py-24">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="mx-auto max-w-2xl text-center">
          <span className="section-tag">Career library</span>
          <h2 className="section-title">
            Every path you are <Accent>measured against</Accent>
          </h2>
          <p className="section-lead">
            {careers ? `${careers.length} roles across ${industries.length} fields.` : 'Roles across technology, data, design, business and more.'}{' '}
            Each one lists the skills it needs, what it pays and where demand is heading.
          </p>
        </div>

        {failed && (
          <p className="mx-auto mt-8 max-w-md rounded-xl border border-edge bg-panel px-4 py-3 text-center text-sm text-fog/70">
            The career library loads from the API. Start the backend on port 8000 to browse it.
          </p>
        )}

        {careers && (
          <>
            <div className="mt-8 flex flex-wrap justify-center gap-2" role="group" aria-label="Filter by field">
              {['All', ...industries].map((name) => (
                <button
                  key={name}
                  type="button"
                  aria-pressed={industry === name}
                  onClick={() => {
                    setIndustry(name)
                    setExpanded(false)
                  }}
                  className={`rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors ${
                    industry === name
                      ? 'border-brand bg-brand text-white'
                      : 'border-edge bg-white/5 text-fog/70 hover:border-brand-light/60 hover:text-fog'
                  }`}
                >
                  {name}
                </button>
              ))}
            </div>

            <ul className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {visible.map((career) => (
                <li key={career.id} className="card flex flex-col p-5">
                  <p className="text-sm font-medium text-brand-light">{career.industry}</p>
                  <h3 className="mt-1 text-lg font-bold">{career.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-fog/60">{career.description}</p>
                  <ul className="mt-4 flex flex-wrap gap-1.5">
                    {career.required_skills.slice(0, 4).map((skill) => (
                      <li key={skill} className="chip-plain">{skill}</li>
                    ))}
                    {career.required_skills.length > 4 && (
                      <li className="chip text-fog/50">and {career.required_skills.length - 4} more</li>
                    )}
                  </ul>
                  <div className="mt-auto pt-5">
                  <dl className="grid grid-cols-2 gap-3 border-t border-edge pt-4 text-sm">
                    <div>
                      <dt className="text-fog/50">Salary</dt>
                      <dd className="font-semibold">
                        {formatSalary(career.salary_min, career.currency)} to {formatSalary(career.salary_max, career.currency)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-fog/50">Ten-year growth</dt>
                      <dd className="font-semibold text-mint">+{career.growth_pct}%</dd>
                    </div>
                  </dl>
                  </div>
                </li>
              ))}
            </ul>

            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              {filtered.length > 6 && (
                <button type="button" className="btn-quiet" onClick={() => setExpanded(!expanded)}>
                  {expanded ? 'Show fewer' : `Show all ${filtered.length}`}
                </button>
              )}
              <button type="button" className="btn-primary" onClick={onStart}>
                See which ones fit me
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  )
}

const FEATURES = [
  {
    icon: 'vector',
    title: 'Matches on your whole profile',
    body: 'Your skills, interests and bio are turned into a vector and compared with every career description, and a trained classifier adds its own prediction, so related experience counts even when the job title is new to you.',
  },
  {
    icon: 'gap',
    title: 'Shows the exact skill gap',
    body: 'For each role you see the core skills you already have beside the ones still to build, and how much each part of your profile contributed to the score.',
  },
  {
    icon: 'route',
    title: 'Gives you a route to get there',
    body: 'Every missing skill comes with learning links, plus certifications worth considering, the salary range and the growth outlook for the role.',
  },
]

const STEPS = [
  ['List your technical skills', 'Tools, languages and methods. Suggestions appear as you type and anything else is accepted.'],
  ['Add strengths and interests', 'Soft skills and the kinds of work you want more of.'],
  ['Set education and experience', 'Used to judge how ready you are for roles with a higher bar.'],
  ['Paste or upload a resume', 'Optional. The text is scanned for skills you forgot to list.'],
]

const FAQS = [
  ['How is the match score calculated?',
    'Four signals are combined: how closely your profile text resembles the career profile (40%), the share of the role\'s skills you already cover (30%), how strongly a trained machine learning classifier predicts that career for your profile (20%), and your experience and education against the typical requirement (10%). Each result shows this breakdown.'],
  ['What machine learning does it use?',
    'Two kinds. Your profile and every career are turned into vectors (sentence embeddings, or TF-IDF as a fallback) and compared with cosine similarity. A supervised classifier, chosen automatically from Logistic Regression, Random Forest and Naive Bayes, is trained on thousands of example profiles generated from the career dataset and predicts which careers your skills point to.'],
  ['Is the score a prediction of getting hired?',
    'No. It measures how similar your profile is to a description of the role. Treat it as a way to shortlist directions and see gaps, not as a forecast.'],
  ['Where do the salary and growth figures come from?',
    'From the demo dataset bundled with this project. Salaries are illustrative India-market estimates in rupees per year, not live labour-market data.'],
  ['What happens to my resume?',
    'An uploaded file is read once to extract its text and is not kept as a file. Your profile and latest results are remembered in your own browser, so they are still there next time you open the site on this device. Use Start over to clear them.'],
  ['Which resume formats can I upload?',
    'PDF, DOCX, TXT and MD files up to 5 MB. Scanned PDFs that contain only images cannot be read, so paste the text instead.'],
  ['What if my skill is not in the suggestions?',
    'Type it anyway. Unlisted skills still shape the text comparison, and common abbreviations such as JS or K8s are recognised.'],
]

export default function Landing({ meta, onStart, onSection, returning = false }) {
  const [openFaq, setOpenFaq] = useState(0)
  const careerCount = meta?.engine?.careers_indexed
  const stats = meta
    ? [
        [meta.engine.careers_indexed, 'career paths'],
        [meta.industries.length, 'fields'],
        [meta.technical_skills.length + meta.soft_skills.length, 'skills and traits tracked'],
      ]
    : null

  return (
    <main>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="glow-top pointer-events-none absolute inset-0" aria-hidden="true" />
        <div className="grid-lines pointer-events-none absolute inset-0" aria-hidden="true" />
        <div className="relative mx-auto grid max-w-6xl items-center gap-10 px-4 pb-16 pt-14 sm:px-6 sm:pt-20 lg:grid-cols-[1.1fr_1fr] lg:gap-14 lg:pb-24">
          <div>
            <span className="section-tag">
              <span className="h-1.5 w-1.5 rounded-full bg-brand-light" aria-hidden="true" />
              AI career matching{careerCount ? ` across ${careerCount} roles` : ''}
            </span>
            <h1 className="mt-5 text-[2.6rem] font-extrabold leading-[1.05] tracking-tight sm:text-6xl">
              Find the career your skills <Accent>already point to</Accent>
            </h1>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-fog/70 sm:text-lg">
              Enter what you know and what you enjoy. Waypoint ranks the five closest careers, shows the skills
              you are missing for each and links you to ways to learn them.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <button type="button" className="btn-primary px-7 py-3 text-base" onClick={onStart}>
                {returning ? 'View my results' : 'Build my profile'}
              </button>
              <button type="button" className="btn-quiet px-6 py-3 text-base" onClick={() => onSection('how')}>
                See how it works
              </button>
            </div>
            {stats && (
              <dl className="mt-10 flex flex-wrap gap-x-10 gap-y-4">
                {stats.map(([value, label]) => (
                  <div key={label}>
                    <dt className="sr-only">{label}</dt>
                    <dd className="font-display text-3xl font-extrabold tabular-nums">{value}</dd>
                    <dd className="text-sm text-fog/55">{label}</dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
          <LiveExample />
        </div>
      </section>

      {/* Features */}
      <section id="features" className="scroll-mt-20 border-t border-edge/60 py-16 sm:py-24">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="mx-auto max-w-2xl text-center">
            <span className="section-tag">Features</span>
            <h2 className="section-title">
              What makes <Accent>Waypoint</Accent> different
            </h2>
            <p className="section-lead">
              A ranked list alone does not tell you what to do next. Each recommendation explains itself and
              comes with a plan.
            </p>
          </div>
          <ul className="mt-10 grid gap-4 md:grid-cols-3">
            {FEATURES.map((feature) => (
              <li key={feature.title} className="card p-6">
                <Icon name={feature.icon} />
                <h3 className="mt-5 text-lg font-bold">{feature.title}</h3>
                <p className="mt-2 text-[15px] leading-relaxed text-fog/65">{feature.body}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="scroll-mt-20 border-t border-edge/60 py-16 sm:py-24">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 sm:px-6 lg:grid-cols-[1fr_1.2fr] lg:gap-16">
          <div>
            <span className="section-tag">How it works</span>
            <h2 className="section-title">
              Four steps to a <Accent>ranked shortlist</Accent>
            </h2>
            <p className="section-lead">
              The form takes a few minutes. Only one skill, interest or a short bio is required; the more you
              add, the sharper the ranking.
            </p>
            <button type="button" className="btn-primary mt-7 px-7 py-3" onClick={onStart}>
              Start step one
            </button>
          </div>
          <ol className="space-y-3">
            {STEPS.map(([title, body], index) => (
              <li key={title} className="card grid grid-cols-[2.75rem_1fr] items-start gap-4 p-5">
                <span className="grid h-11 w-11 place-items-center rounded-xl bg-brand font-display text-lg font-extrabold">
                  {index + 1}
                </span>
                <div>
                  <h3 className="text-base font-bold">{title}</h3>
                  <p className="mt-1 text-[15px] leading-relaxed text-fog/65">{body}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <CareerExplorer onStart={onStart} />

      {/* FAQ */}
      <section id="faq" className="scroll-mt-20 border-t border-edge/60 py-16 sm:py-24">
        <div className="mx-auto max-w-3xl px-4 sm:px-6">
          <div className="text-center">
            <span className="section-tag">FAQ</span>
            <h2 className="section-title">
              Answers to <Accent>common questions</Accent>
            </h2>
          </div>
          <ul className="mt-10 space-y-3">
            {FAQS.map(([question, answer], index) => {
              const open = openFaq === index
              return (
                <li key={question} className={`card overflow-hidden ${open ? 'border-brand/50' : ''}`}>
                  <h3>
                    <button
                      type="button"
                      aria-expanded={open}
                      aria-controls={`faq-${index}`}
                      onClick={() => setOpenFaq(open ? -1 : index)}
                      className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left text-base font-semibold"
                    >
                      {question}
                      <svg viewBox="0 0 20 20" className={`h-5 w-5 shrink-0 text-brand-light transition-transform ${open ? 'rotate-45' : ''}`} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                        <path d="M10 4v12M4 10h12" />
                      </svg>
                    </button>
                  </h3>
                  {open && (
                    <p id={`faq-${index}`} className="px-5 pb-5 text-[15px] leading-relaxed text-fog/70">
                      {answer}
                    </p>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      </section>

      {/* Closing call to action */}
      <section className="px-4 pb-16 sm:px-6 sm:pb-24">
        <div className="relative mx-auto max-w-6xl overflow-hidden rounded-3xl border border-brand/40 bg-panel px-6 py-14 text-center sm:py-20">
          <div className="glow-center pointer-events-none absolute inset-0" aria-hidden="true" />
          <div className="relative mx-auto max-w-2xl">
            <h2 className="text-3xl font-extrabold tracking-tight sm:text-5xl sm:leading-[1.08]">
              See where your skills can <Accent>take you next</Accent>
            </h2>
            <p className="mt-4 text-base leading-relaxed text-fog/70">
              Build your profile once. Edit it and rerun the match whenever you learn something new.
            </p>
            <button type="button" className="btn-primary mt-8 px-8 py-3 text-base" onClick={onStart}>
              {returning ? 'View my results' : 'Build my profile'}
            </button>
          </div>
        </div>
      </section>
    </main>
  )
}
