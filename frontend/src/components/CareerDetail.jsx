import { formatSalary } from './CareerCard.jsx'

const RESOURCE_KIND = { course: 'Course', docs: 'Guide', book: 'Book', search: 'Search' }

function ScoreBar({ label, value, weight }) {
  const pct = Math.round(value * 100)
  return (
    <div>
      <div className="flex items-baseline justify-between text-sm">
        <span className="text-fog/75">{label}</span>
        <span className="font-semibold tabular-nums">{pct}%</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-brand" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-0.5 text-xs text-fog/50">{Math.round(weight * 100)}% of the score</p>
    </div>
  )
}

function SkillGroup({ title, skills, variant, empty }) {
  return (
    <div>
      <h4 className="text-sm font-semibold text-fog/70">{title}</h4>
      {skills.length ? (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {skills.map((skill) => (
            <li key={skill} className={variant}>{skill}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-fog/50">{empty}</p>
      )}
    </div>
  )
}

export default function CareerDetail({ recommendation }) {
  const r = recommendation
  const { career } = r
  const { weights } = r.score_breakdown
  const core = r.learning_plan.filter((step) => step.priority === 'core')
  const bonus = r.learning_plan.filter((step) => step.priority === 'bonus')

  return (
    <article className="rounded-3xl border border-edge bg-panel shadow-lift" aria-live="polite">
      <header className="grid gap-6 border-b border-edge p-5 sm:p-8 lg:grid-cols-[1fr_17rem]">
        <div>
          <p className="text-sm font-medium text-fog/60">{career.industry}</p>
          <h2 className="mt-1 text-3xl font-bold tracking-tight sm:text-4xl">{career.title}</h2>
          <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-fog/75">{career.description}</p>
        </div>
        <div className="rounded-2xl bg-panel2 p-4">
          <div className="flex items-baseline justify-between">
            <span className="font-display text-4xl font-bold tabular-nums">{r.match_score.toFixed(1)}%</span>
            <span className="rounded-full bg-brand/20 px-2.5 py-1 text-sm font-semibold text-brand-light">{r.confidence}</span>
          </div>
          <div className="mt-4 space-y-3">
            <ScoreBar label="Profile similarity" value={r.score_breakdown.semantic_fit} weight={weights.semantic_fit} />
            <ScoreBar label="Skill coverage" value={r.score_breakdown.skill_fit} weight={weights.skill_fit} />
            {r.score_breakdown.model_fit != null && (
              <ScoreBar label="ML model confidence" value={r.score_breakdown.model_fit} weight={weights.model_fit} />
            )}
            <ScoreBar label="Experience and education" value={r.score_breakdown.readiness} weight={weights.readiness} />
          </div>
        </div>
      </header>

      <section className="grid gap-8 border-b border-edge p-5 sm:p-8 lg:grid-cols-2">
        <div>
          <h3 className="text-xl font-bold">Why this fits</h3>
          <p className="mt-2 text-[15px] leading-relaxed text-fog/80">{r.why}</p>
          {r.readiness_notes.length > 0 && (
            <ul className="mt-3 space-y-2">
              {r.readiness_notes.map((note) => (
                <li key={note} className="rounded-xl bg-amber/10 px-3.5 py-2.5 text-sm leading-relaxed text-amber">
                  {note}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-4 text-sm text-fog/60">
            Typical entry: {career.education_label.toLowerCase()},{' '}
            {career.min_experience_years > 0 ? `${career.min_experience_years}+ years of experience` : 'no prior experience required'}.
          </p>
        </div>

        <div className="space-y-5">
          <SkillGroup title="Core skills you have" skills={r.matched_skills} variant="chip-have" empty="None of the core skills yet." />
          <SkillGroup title="Core skills to build" skills={r.missing_skills} variant="chip-build" empty="Nothing missing. You cover every core skill." />
          {(r.matched_preferred.length > 0 || r.matched_traits.length > 0) && (
            <SkillGroup
              title="Also in your favour"
              skills={[...r.matched_preferred, ...r.matched_traits]}
              variant="chip-plain"
              empty=""
            />
          )}
        </div>
      </section>

      <section className="grid gap-8 border-b border-edge p-5 sm:p-8 lg:grid-cols-[1.4fr_1fr]">
        <div>
          <h3 className="text-xl font-bold">Learning roadmap</h3>
          {core.length === 0 && bonus.length === 0 ? (
            <p className="mt-2 text-[15px] text-fog/70">No gaps to close. A certification below can help you prove what you know.</p>
          ) : (
            <ol className="mt-4 space-y-4">
              {[...core, ...bonus].map((step, index) => (
                <li key={step.skill} className="grid grid-cols-[1.75rem_1fr] gap-3">
                  <span className="mt-0.5 grid h-7 w-7 place-items-center rounded-full bg-amber/15 text-sm font-semibold text-amber">
                    {index + 1}
                  </span>
                  <div>
                    <p className="text-[15px] font-semibold">
                      {step.skill}
                      {step.priority === 'bonus' && <span className="ml-2 text-sm font-normal text-fog/50">nice to have</span>}
                    </p>
                    <ul className="mt-1 space-y-1">
                      {step.resources.map((resource) => (
                        <li key={resource.url} className="text-sm leading-relaxed">
                          <a
                            href={resource.url}
                            target="_blank"
                            rel="noreferrer noopener"
                            className="font-medium text-brand-light underline decoration-brand-light/30 underline-offset-2 hover:decoration-brand-light"
                          >
                            {resource.title}
                          </a>
                          <span className="text-fog/55">
                            {' '}
                            ({RESOURCE_KIND[resource.type] || 'Resource'}, {resource.provider})
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>

        <div>
          <h3 className="text-xl font-bold">Certifications to consider</h3>
          {career.certifications.length ? (
            <ul className="mt-4 space-y-2">
              {career.certifications.map((certification) => (
                <li key={certification} className="rounded-xl border border-edge px-3.5 py-2.5 text-[15px]">
                  {certification}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-[15px] leading-relaxed text-fog/70">
              No standard certification for this role. Published work, a portfolio or research output carries more weight.
            </p>
          )}
        </div>
      </section>

      <section className="grid gap-6 p-5 sm:grid-cols-2 sm:p-8">
        <div>
          <h3 className="text-sm font-semibold text-fog/70">Salary range</h3>
          <p className="mt-1 font-display text-2xl font-bold">
            {formatSalary(career.salary.min, career.salary.currency)} to {formatSalary(career.salary.max, career.salary.currency)}
            <span className="ml-2 font-sans text-sm font-normal text-fog/55">per year</span>
          </p>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-fog/70">Growth outlook</h3>
          <p className="mt-1 font-display text-2xl font-bold">
            {career.growth.pct > 0 ? '+' : ''}
            {career.growth.pct}%
            <span className="ml-2 font-sans text-sm font-normal text-fog/55">projected over ten years</span>
          </p>
          <p className="mt-1 text-[15px] text-fog/75">
            {career.growth.outlook}. {career.growth.note}
          </p>
        </div>
      </section>
    </article>
  )
}
