import React from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { useCompleteStep, useOnboarding } from '../api/financialState';
import { ProfileStep } from '../features/financial-state/ProfileStep';
import { ITEM_STEPS } from '../features/financial-state/steps';

const ORDER = [
  { step: 'profile', path: 'profile', title: 'About you' },
  ...ITEM_STEPS.map(({ step, path, title }) => ({ step, path, title })),
] as const;

export const OnboardingPage: React.FC = () => {
  const { step: pathParam } = useParams();
  const navigate = useNavigate();
  const status = useOnboarding();
  const complete = useCompleteStep();

  const index = ORDER.findIndex((s) => s.path === pathParam);
  if (index < 0) return <Navigate to="/setup/profile" replace />;

  const current = ORDER[index];
  const itemStep = ITEM_STEPS.find((s) => s.path === current.path);
  const done = new Map((status.data?.steps ?? []).map((s) => [s.step, s]));
  const count = done.get(current.step)?.item_count ?? 0;
  const next = () => navigate(index + 1 < ORDER.length ? `/setup/${ORDER[index + 1].path}` : '/overview');

  const finishStep = async () => {
    if (itemStep) await complete.mutateAsync(itemStep.step);
    next();
  };

  return (
    <div className="page-container onboarding">
      <header className="page-header-row">
        <div>
          <h1 className="page-title">Set up your financial picture</h1>
          <p className="page-subtitle">Six short steps. Estimates are fine — you can change anything later.</p>
        </div>
      </header>

      <ol className="stepper" aria-label="Setup progress">
        {ORDER.map((s, i) => {
          const isDone = done.get(s.step)?.completed;
          return (
            <li key={s.path} className={`stepper__item ${i === index ? 'stepper__item--current' : ''} ${isDone ? 'stepper__item--done' : ''}`}>
              <button type="button" onClick={() => navigate(`/setup/${s.path}`)} aria-current={i === index ? 'step' : undefined}>
                <span className="stepper__dot">{isDone ? '✓' : i + 1}</span>
                <span className="stepper__label">{s.title}</span>
              </button>
            </li>
          );
        })}
      </ol>

      <section className="card onboarding__panel">
        <h2 className="card__title">{itemStep ? itemStep.title : 'About you'}</h2>
        <p className="card__subtitle">{itemStep ? itemStep.intro : 'Your age and retirement age set the planning horizon.'}</p>
        {/* key: each step gets fresh form state instead of reusing the previous step's */}
        <React.Fragment key={current.path}>{itemStep ? itemStep.body : <ProfileStep onSaved={next} />}</React.Fragment>
      </section>

      <div className="onboarding__nav">
        <button type="button" className="btn btn--outline" disabled={index === 0} onClick={() => navigate(`/setup/${ORDER[index - 1].path}`)}>Back</button>
        {itemStep && (
          <button type="button" className="btn btn--primary" disabled={complete.isPending} onClick={finishStep}>
            {count === 0 && itemStep.noneLabel ? `${itemStep.noneLabel} — continue` : index + 1 < ORDER.length ? 'Done — next step' : 'Finish setup'}
          </button>
        )}
      </div>
      {complete.isError && <div className="form-alert form-alert--error">{(complete.error as Error).message}</div>}
    </div>
  );
};
