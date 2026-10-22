import { useState } from 'react'
import CareerCard, { formatSalary } from './CareerCard.jsx'
import CareerDetail from './CareerDetail.jsx'

const ENGINE_NAMES = {
  'sentence-transformers': 'sentence embeddings',
  tfidf: 'TF-IDF text matching',
}

/** Salary and growth for all five matches on shared scales, so they can be compared at a glance. */
function MarketComparison({ recommendations, selectedId, onSelect }) {
  const low = Math.min(...recommendations.map((r) => r.career.salary.min))
  const high = Math.max(...recommendations.map((r) => r.career.salary.max))
  const span = Math.max(1, high - low)
  const maxGrowth = Math.max(1, ...recommendations.map((r) => r.career.growth.pct))
  const currency = recommendations[0]?.career.salary.currency

  return (
    <section className="rounded-3xl border border-edge bg-panel p-5 sm:p-8">
      <h2 className="text-xl font-bold">How your five matches compare</h2>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[36rem] border-collapse text-[15px]">
          <thead>
            <tr className="text-left text-sm text-fog/60">
              <th scope="col" className="pb-2 pr-4 font-medium">Career</th>
              <th scope="col" className="pb-2 pr-4 font-medium">
                Salary, {formatSalary(low, currency)} to {formatSalary(high, currency)}
              </th>
              <th scope="col" className="pb-2 font-medium">Ten-year growth</th>
            </tr>
          </thead>
          <tbody>
            {recommendations.map((r) => {
              const { career } = r
              const active = career.id === selectedId
              return (
                <tr
                  key={career.id}
                  onClick={() => onSelect(career.id)}
                  className={`cursor-pointer border-t border-edge ${active ? 'bg-panel2' : 'hover:bg-white/5'}`}
                >
                  <th scope="row" className={`py-3 pl-2 pr-4 text-left ${active ? 'font-semibold' : 'font-medium'}`}>
                    {career.title}
                  </th>
                  <td className="w-[38%] py-3 pr-4">
                    <div className="relative h-2.5 rounded-full bg-white/10">
                      <span
                        className={`absolute inset-y-0 rounded-full ${active ? 'bg-brand' : 'bg-brand/40'}`}
                        style={{
                          left: `${((career.salary.min - low) / span) * 100}%`,
                          width: `${((career.salary.max - career.salary.min) / span) * 100}%`,
                        }}
                      />
                    </div>
                    <span className="mt-1 block text-sm tabular-nums text-fog/60">
                      {formatSalary(career.salary.min, career.salary.currency)} to{' '}
                      {formatSalary(career.salary.max, career.salary.currency)}
                    </span>
                  </td>
                  <td className="w-[26%] py-3 pr-2">
                    <div className="flex items-center gap-2">
                      <div className="h-2.5 flex-1 rounded-full bg-white/10">
                        <span
                          className={`block h-full rounded-full ${active ? 'bg-mint' : 'bg-mint/45'}`}
                          style={{ width: `${Math.max(3, (career.growth.pct / maxGrowth) * 100)}%` }}
                        />
                      </div>
                      <span className="w-10 text-right text-sm tabular-nums">{career.growth.pct}%</span>
                    </div>
                    <span className="mt-1 block text-sm text-fog/60">{career.growth.outlook}</span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default function Dashboard({ results, salaryNote }) {
  const { recommendations, engine, detected_skills: detected } = results
  const [selectedId, setSelectedId] = useState(recommendations[0]?.career.id)
  const selected = recommendations.find((r) => r.career.id === selectedId) || recommendations[0]

  if (!recommendations.length) {
    return <p className="text-[15px] text-fog/70">No careers were returned. Edit your profile and try again.</p>
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">Your five closest <span className="text-brand-light">careers</span></h1>
        <p className="mt-3 max-w-3xl text-[15px] leading-relaxed text-fog/70">
          Ranked from {engine.careers_indexed} career paths using {ENGINE_NAMES[engine.backend] || engine.backend}
          {engine.classifier ? ` and a trained ${engine.classifier.name} classifier` : ''}.
          Select a card to see the skill gap, a learning roadmap and market data for that role.
        </p>
        {detected.length > 0 && (
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-fog/60">
            Also counted from your bio: {detected.join(', ')}.
          </p>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {recommendations.map((recommendation) => (
          <CareerCard
            key={recommendation.career.id}
            recommendation={recommendation}
            selected={recommendation.career.id === selected.career.id}
            onSelect={() => setSelectedId(recommendation.career.id)}
          />
        ))}
      </div>

      <CareerDetail recommendation={selected} />

      <MarketComparison recommendations={recommendations} selectedId={selected.career.id} onSelect={setSelectedId} />

      <p className="max-w-3xl text-sm leading-relaxed text-fog/55">
        {salaryNote ||
          'Salary bands and growth figures come from the bundled demo dataset. They are illustrative estimates, not live labour-market data.'}{' '}
        Match scores describe how closely your profile text and skills resemble each career profile; they are not a
        prediction of hiring outcomes.
        {engine.classifier &&
          ` The ${engine.classifier.name} classifier was trained on ${engine.classifier.training_samples.toLocaleString('en-IN')} profiles generated from the career dataset and identifies the right career for ${Math.round(engine.classifier.accuracy * 100)}% of held-out generated profiles (${Math.round(engine.classifier.top3_accuracy * 100)}% within its top three). That measures how well it learned the dataset, not accuracy for real people.`}
      </p>
    </div>
  )
}
