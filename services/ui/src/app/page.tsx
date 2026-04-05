"use client";

import { useEffect, useMemo, useState } from 'react';

type Recommendation =
  | string
  | {
      priority?: string;
      action?: string;
      rationale?: string;
      expected_outcome?: string;
    };

type AgentResponse = {
  analysis?: string | string[];
  recommendations?: Recommendation[];
  warnings?: string[];
  iterations?: number;
  total_tokens?: number;
  execution_time_seconds?: number;
  task?: string;
  query?: string;
  request_id?: string;
  timestamp?: string;
  status?: string;
};

type ProductOption = {
  name: string;
  category: string;
};

type FormOptions = {
  origins: string[];
  destinations: string[];
  products: ProductOption[];
  transport_modes: string[];
};

type QueryContext = {
  origin: string;
  destination: string;
  product: string;
  transportMode: string;
  objective: string;
  budget: string;
  constraints: string;
};

const EMPTY_OPTION_LABEL = '—';

const PROBLEM_DEFINITION =
  'Rank these three supplier orders by expected utility. Spencer-Lee Carroll, ' +
  'Sullivan and Bass Lawson, Morris and Ramos.';

const DEFAULT_CONTEXT: QueryContext = {
  origin: '',
  destination: '',
  product: '',
  transportMode: '',
  objective: '',
  budget: '',
  constraints: '',
};

const buildQuery = (context: QueryContext, problemDef: string = PROBLEM_DEFINITION) =>
  `${problemDef} Origin: ${context.origin}, Destination: ${context.destination}. ` +
  `Product: ${context.product}. Transport Mode: ${context.transportMode}. ` +
  `Objective: ${context.objective}. Budget: ${context.budget}. Constraints: ${context.constraints}.`;

const normalizeText = (value: unknown) => {
  if (!value) return [] as string[];
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item).trim())
      .filter(Boolean);
  }
  if (typeof value === 'string') {
    return value
      .split(/\n\n+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [String(value)];
};

const formatTimestamp = (value?: string) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('uk-UA', { dateStyle: 'short', timeStyle: 'short' });
};

export default function Home() {
  const [problemDefinitionDisplay, setProblemDefinitionDisplay] = useState(PROBLEM_DEFINITION);
  const [submittedProblemDef, setSubmittedProblemDef] = useState(PROBLEM_DEFINITION);
  const [origin, setOrigin] = useState(DEFAULT_CONTEXT.origin);
  const [destination, setDestination] = useState(DEFAULT_CONTEXT.destination);
  const [transportMode, setTransportMode] = useState(DEFAULT_CONTEXT.transportMode);
  const [objective, setObjective] = useState(DEFAULT_CONTEXT.objective);
  const [budget, setBudget] = useState(DEFAULT_CONTEXT.budget);
  const [constraints, setConstraints] = useState(DEFAULT_CONTEXT.constraints);
  const [productIndex, setProductIndex] = useState<number | null>(null);
  const [isOriginOpen, setIsOriginOpen] = useState(false);
  const [isDestinationOpen, setIsDestinationOpen] = useState(false);
  const [isProductOpen, setIsProductOpen] = useState(false);
  const [isTransportOpen, setIsTransportOpen] = useState(false);
  const [isObjectiveOpen, setIsObjectiveOpen] = useState(false);

  const [formOptions, setFormOptions] = useState<FormOptions | null>(null);
  const [optionsError, setOptionsError] = useState<string | null>(null);
  const [isOptionsLoading, setIsOptionsLoading] = useState(false);

  const [submitted, setSubmitted] = useState<QueryContext>(DEFAULT_CONTEXT);
  const [response, setResponse] = useState<AgentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isQueryOpen, setIsQueryOpen] = useState(false);
  const [isAgentOpen, setIsAgentOpen] = useState(false);

  const selectedProductValue =
    productIndex === null ? '' : formOptions?.products[productIndex]?.category ?? '';

  useEffect(() => {
    let isActive = true;

    const loadOptions = async () => {
      setIsOptionsLoading(true);
      setOptionsError(null);

      try {
        const resp = await fetch('/api/form-options');
        if (!resp.ok) {
          setOptionsError(`Options error ${resp.status}: ${await resp.text()}`);
          return;
        }

        const data = (await resp.json()) as FormOptions;
        if (!isActive) return;

        setFormOptions(data);
        setProductIndex(null);
        setSubmitted(DEFAULT_CONTEXT);
      } catch (fetchError) {
        if (!isActive) return;
        setOptionsError('Unable to load dropdown options.');
      } finally {
        if (isActive) {
          setIsOptionsLoading(false);
        }
      }
    };

    loadOptions();

    return () => {
      isActive = false;
    };
  }, []);

  const submittedQuery = useMemo(() => buildQuery(submitted, submittedProblemDef), [submitted, submittedProblemDef]);

  const memoTitle = response?.task || response?.query?.slice(0, 60) || '—';
  const memoId = response?.request_id
    ? `#${response.request_id.slice(0, 8).toUpperCase()}`
    : '—';
  const memoTimestamp = response?.timestamp ? formatTimestamp(response.timestamp) : '—';

  const clearForm = () => {
    setProblemDefinitionDisplay(PROBLEM_DEFINITION);
    setSubmittedProblemDef(PROBLEM_DEFINITION);
    setOrigin('');
    setDestination('');
    setTransportMode('');
    setObjective('');
    setBudget('');
    setConstraints('');
    setProductIndex(null);
    setSubmitted(DEFAULT_CONTEXT);
    setResponse(null);
    setError(null);
    setIsQueryOpen(false);
    setIsAgentOpen(false);
    setIsOriginOpen(false);
    setIsDestinationOpen(false);
    setIsProductOpen(false);
    setIsTransportOpen(false);
    setIsObjectiveOpen(false);
  };

  const submitAnalysis = async () => {
    if (!origin || !destination || !selectedProductValue || !transportMode) {
      setError('Select origin, destination, product, and transport mode.');
      return;
    }

    const nextContext: QueryContext = {
      origin: origin.trim(),
      destination: destination.trim(),
      product: selectedProductValue,
      transportMode: transportMode.trim(),
      objective: objective.trim(),
      budget: budget.trim(),
      constraints: constraints.trim(),
    };

    const query = buildQuery(nextContext, problemDefinitionDisplay);
    if (query.length < 10 || query.length > 1000) {
      setError('Final query must be between 10 and 1000 characters.');
      return;
    }

    setError(null);
    setIsLoading(true);
    setResponse(null);
    setSubmitted(nextContext);
    setSubmittedProblemDef(problemDefinitionDisplay);

    const body = {
      query,
      context: {},
    };

    try {
      const resp = await fetch('http://localhost:8003/api/v1/agent/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        setError(`Error ${resp.status}: ${await resp.text()}`);
        return;
      }

      const data = (await resp.json()) as AgentResponse;
    setResponse(data);
    setIsQueryOpen(true);
    setIsAgentOpen(true);
    setIsOriginOpen(false);
    setIsDestinationOpen(false);
    setIsProductOpen(false);
    setIsTransportOpen(false);
    setIsObjectiveOpen(false);
    } catch (fetchError) {
      setError('Network error — agent-service unavailable');
    } finally {
      setIsLoading(false);
    }
  };

  const isSubmitDisabled = isLoading || isOptionsLoading || !formOptions;

  return (
    <>
      <header className="header">
        <div className="header-brand">
          <div className="brand-icon">
            <svg viewBox="0 0 24 24">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
            </svg>
          </div>
          <span className="brand-name">BeliefCraft</span>
        </div>

        <div className="search-container">
          <div className="search-wrapper">
            <svg
              className="search-icon-svg"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input type="text" className="search-input" placeholder="Search chats..." />
            <ul className="search-dropdown">
              <li className="new-chat">
                <span className="icon-new">+</span>
                Create New Chat
              </li>
              <li>
                <span className="chat-icon">
                  <svg viewBox="0 0 24 24">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  </svg>
                </span>
                Berlin Warehouse EOQ Analysis
              </li>
              <li>
                <span className="chat-icon">
                  <svg viewBox="0 0 24 24">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  </svg>
                </span>
                Kyiv Fleet Optimization
              </li>
              <li>
                <span className="chat-icon">
                  <svg viewBox="0 0 24 24">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  </svg>
                </span>
                Supply Chain Scenario Planning
              </li>
            </ul>
          </div>
        </div>

        <div className="header-right">
          <div className="status-pill">
            <div className="dots-group">
              <span className="status-dot"></span>
              <span className="status-dot"></span>
              <span className="status-dot"></span>
            </div>
            LIVE
          </div>
        </div>
      </header>

      <main className="main-layout">
        <section className="canvas-section">
          <div className="memo-card">
            <div className="memo-topbar">
              <div>
                <div className="memo-label">Analysis Memorandum</div>
                <div id="memo-title" className="memo-title">
                  {memoTitle}
                </div>
              </div>
              <div className="memo-meta">
                <div id="memo-ts" className="memo-timestamp">
                  {memoTimestamp}
                </div>
                <div id="memo-id" className="memo-id">
                  {memoId}
                </div>
              </div>
            </div>

            <div className="thread">
              <div className="query-block">
                <div
                  className={`query-toggle ${isQueryOpen ? 'open' : ''}`}
                  onClick={() => setIsQueryOpen((prev) => !prev)}
                >
                  <div className="toggle-avatar">
                    <svg viewBox="0 0 24 24">
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                      <circle cx="12" cy="7" r="4" />
                    </svg>
                  </div>
                  <span className="toggle-label">User Query</span>
                  <div className="toggle-chevron">
                    <svg viewBox="0 0 24 24">
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                  </div>
                </div>

                <div className={`query-body ${isQueryOpen ? 'open' : ''}`}>
                  <div className="query-inner">
                    <p id="query-text">{submittedQuery}</p>
                    <div className="query-params">
                      <div className="param-chip">
                        Origin: <span>{submitted.origin}</span>
                      </div>
                      <div className="param-chip">
                        Destination: <span>{submitted.destination}</span>
                      </div>
                      <div className="param-chip">
                        Product: <span>{submitted.product}</span>
                      </div>
                      <div className="param-chip">
                        Transport: <span>{submitted.transportMode}</span>
                      </div>
                      <div className="param-chip">
                        Objective: <span>{submitted.objective}</span>
                      </div>
                      <div className="param-chip">
                        Budget: <span>{submitted.budget}</span>
                      </div>
                      <div className="param-chip">
                        Constraint: <span>{submitted.constraints}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="thread-connector"></div>

              <div className="agent-block">
                <div
                  className={`agent-toggle ${isAgentOpen ? 'open' : ''}`}
                  onClick={() => setIsAgentOpen((prev) => !prev)}
                >
                  <div className="agent-avatar">
                    <svg viewBox="0 0 24 24">
                      <path d="M12 2a4 4 0 0 1 4 4v1h1a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2h-1v1a4 4 0 0 1-4 4 4 4 0 0 1-4-4v-1H7a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h1V6a4 4 0 0 1 4-4z" />
                      <circle cx="9" cy="10" r="1" />
                      <circle cx="15" cy="10" r="1" />
                    </svg>
                  </div>
                  <span className="toggle-label">Agent</span>
                  <div className="toggle-chevron">
                    <svg viewBox="0 0 24 24">
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                  </div>
                </div>

                <div className={`agent-body ${isAgentOpen ? 'open' : ''}`}>
                  <div className="agent-inner">
                    <div className="agent-step">
                      <div className="agent-step-num">1</div>
                      <div className="agent-step-text">
                        <strong>Query prepared.</strong> Sent structured context to agent-service
                        for analysis.
                      </div>
                    </div>
                    <div className="agent-step">
                      <div className="agent-step-num">2</div>
                      <div className="agent-step-text">
                        <strong>
                          {isLoading
                            ? 'Awaiting response.'
                            : response
                              ? 'Response received.'
                              : 'Ready for analysis.'}
                        </strong>{' '}
                        {response?.status ? `Status: ${response.status}.` : ''}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="thread-connector"></div>

              <div className="responses-block" id="thread-root">
                {isLoading && (
                  <div
                    style={{
                      padding: '24px 32px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '14px',
                    }}
                  >
                    <div className="skeleton-line" style={{ width: '80%' }}></div>
                    <div className="skeleton-line" style={{ width: '60%' }}></div>
                    <div className="skeleton-line" style={{ width: '72%' }}></div>
                  </div>
                )}

                {error && !isLoading && (
                  <div className="resp-panels" style={{ borderRadius: 'var(--radius-lg)' }}>
                    <div className="resp-panel active" style={{ padding: '24px' }}>
                      <p className="rec-text">{error}</p>
                    </div>
                  </div>
                )}

                {response && !isLoading && <ResponsePanel response={response} />}
              </div>
            </div>
          </div>
        </section>

        <section className="panel-section">
          <div className="panel-card">
            <div className="panel-head">
              <div className="panel-pretitle">Input</div>
              <div className="panel-title">Define Strategic Problem</div>
            </div>

            <div className="form-group">
              <label className="form-label">Problem Definition</label>
              <textarea
                id="field-problem"
                className="form-control"
                rows={3}
                value={problemDefinitionDisplay}
                placeholder={EMPTY_OPTION_LABEL}
                onChange={(e) => setProblemDefinitionDisplay(e.target.value)}
              />
            </div>

            {isOptionsLoading && <div className="rec-text">Loading dropdown options…</div>}
            {optionsError && <div className="field-error">{optionsError}</div>}

            <div className="input-grid">
              <div className="form-group">
                <label className="form-label">Origin</label>
                <select
                  id="field-origin"
                  className="form-control"
                  value={origin}
                  size={isOriginOpen ? 5 : 1}
                  onFocus={() => setIsOriginOpen(true)}
                  onBlur={() => setIsOriginOpen(false)}
                  onChange={(event) => {
                    setOrigin(event.target.value);
                    setIsOriginOpen(false);
                  }}
                  disabled={!formOptions}
                >
                  <option value="">{EMPTY_OPTION_LABEL}</option>
                  {formOptions?.origins.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Destination</label>
                <select
                  id="field-destination"
                  className="form-control"
                  value={destination}
                  size={isDestinationOpen ? 5 : 1}
                  onFocus={() => setIsDestinationOpen(true)}
                  onBlur={() => setIsDestinationOpen(false)}
                  onChange={(event) => {
                    setDestination(event.target.value);
                    setIsDestinationOpen(false);
                  }}
                  disabled={!formOptions}
                >
                  <option value="">{EMPTY_OPTION_LABEL}</option>
                  {formOptions?.destinations.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="input-grid">
              <div className="form-group">
                <label className="form-label">Product</label>
                <select
                  id="field-product"
                  className="form-control"
                  value={productIndex === null ? '' : String(productIndex)}
                  size={isProductOpen ? 5 : 1}
                  onFocus={() => setIsProductOpen(true)}
                  onBlur={() => setIsProductOpen(false)}
                  onChange={(event) => {
                    const nextValue = event.target.value;
                    setProductIndex(nextValue ? Number(nextValue) : null);
                    setIsProductOpen(false);
                  }}
                  disabled={!formOptions}
                >
                  <option value="">{EMPTY_OPTION_LABEL}</option>
                  {formOptions?.products.map((product, index) => (
                    <option
                      key={`${product.name}-${product.category}-${index}`}
                      value={index}
                    >
                      {product.name} · {product.category}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Transport Mode</label>
                <select
                  id="field-transport"
                  className="form-control"
                  value={transportMode}
                  size={isTransportOpen ? 5 : 1}
                  onFocus={() => setIsTransportOpen(true)}
                  onBlur={() => setIsTransportOpen(false)}
                  onChange={(event) => {
                    setTransportMode(event.target.value);
                    setIsTransportOpen(false);
                  }}
                  disabled={!formOptions}
                >
                  <option value="">{EMPTY_OPTION_LABEL}</option>
                  {formOptions?.transport_modes.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="input-grid">
              <div className="form-group">
                <label className="form-label">Objective</label>
                <select
                  id="field-objective"
                  className="form-control"
                  value={objective}
                  size={isObjectiveOpen ? 5 : 1}
                  onFocus={() => setIsObjectiveOpen(true)}
                  onBlur={() => setIsObjectiveOpen(false)}
                  onChange={(event) => {
                    setObjective(event.target.value);
                    setIsObjectiveOpen(false);
                  }}
                >
                  <option value="">{EMPTY_OPTION_LABEL}</option>
                  <option>Minimize Cost &amp; Time</option>
                  <option>Minimize Cost</option>
                  <option>Minimize Time</option>
                  <option>Maximize Reliability</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Budget</label>
                <input
                  id="field-budget"
                  type="text"
                  className="form-control"
                  value={budget}
                  placeholder={EMPTY_OPTION_LABEL}
                  onChange={(event) => setBudget(event.target.value)}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Constraints</label>
              <textarea
                id="field-constraints"
                className="form-control"
                rows={2}
                placeholder={EMPTY_OPTION_LABEL}
                value={constraints}
                onChange={(event) => setConstraints(event.target.value)}
              />
            </div>

            <div className="button-group">
              <button className="btn-primary" onClick={submitAnalysis} disabled={isSubmitDisabled}>
                {isLoading ? 'Analyzing…' : 'Analyze Scenarios'}
              </button>
              <button className="btn-secondary" onClick={clearForm}>
                Clear
              </button>
            </div>
          </div>
        </section>
      </main>
    </>
  );
}

function ResponsePanel({ response }: { response: AgentResponse }) {
  const analysis = normalizeText(
    response.analysis ?? response.recommendations ?? response.query ?? response.task
  );
  const recommendations = response.recommendations ?? [];
  const warnings = response.warnings ?? [];

  return (
    <div className="resp-panels" style={{ borderRadius: 'var(--radius-lg)' }}>
      <div className="resp-panel active" style={{ padding: '28px 28px 24px' }}>
        {analysis.length > 0 ? (
          analysis.map((line) => (
            <p key={line} className="rec-text" style={{ marginTop: '14px' }}>
              {line}
            </p>
          ))
        ) : (
          <p className="rec-text">No analysis content returned.</p>
        )}

        {recommendations.length > 0 && (
          <div style={{ marginTop: '18px' }}>
            <div className="panel-label">Recommendations</div>
            {recommendations.map((item, index) => {
              if (typeof item === 'string') {
                return (
                  <p
                    key={`${item}-${index}`}
                    className="rec-text"
                    style={{ marginTop: '10px' }}
                  >
                    {item}
                  </p>
                );
              }

              return (
                <div
                  key={`${item.action}-${index}`}
                  className="rec-panel"
                  style={{ marginTop: '12px' }}
                >
                  <div className="rec-label">
                    <span className="rec-dot"></span>
                    {item.priority ? `${item.priority} priority` : 'Recommendation'}
                  </div>
                  {item.action && <p className="rec-text">{item.action}</p>}
                  {item.rationale && (
                    <p className="rec-text" style={{ marginTop: '8px' }}>
                      {item.rationale}
                    </p>
                  )}
                  {item.expected_outcome && (
                    <p className="rec-text" style={{ marginTop: '8px' }}>
                      {item.expected_outcome}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {warnings.length > 0 && (
          <div style={{ marginTop: '18px' }}>
            <div className="panel-label">Warnings</div>
            {warnings.map((warn) => (
              <p key={warn} className="rec-text" style={{ marginTop: '10px' }}>
                {warn}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
