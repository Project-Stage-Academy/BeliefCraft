"use client";

import { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkMath from 'remark-math';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { CustomSelect } from '../components/CustomSelect';

type Recommendation =
  | string
  | {
      priority?: string;
      action?: string;
      rationale?: string;
      expected_outcome?: string;
    };

type Citation =
  | string
  | {
      id?: string;
      label?: string;
      source?: string;
      title?: string;
    };

type CodeSnippet =
  | string
  | {
      title?: string;
      label?: string;
      language?: string;
      code?: string;
      snippet?: string;
      content?: string;
    };

type ReasoningAction = {
  tool?: string;
  arguments?: Record<string, unknown>;
  observation?: string;
  obs?: string;
  result?: string;
};

type ReasoningIteration = {
  iteration?: number;
  title?: string;
  summary?: string;
  thought?: string;
  tools?: string[];
  actions?: ReasoningAction[];
};

type AgentResponse = {
  final_answer?: string;
  analysis?: string | string[];
  recommendations?: Recommendation[];
  reasoning_trace?: ReasoningIteration[];
  code_snippets?: CodeSnippet[];
  citations?: Citation[];
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

type NormalizedRecommendation = {
  id: string;
  sortIndex: number;
  priority: 'high' | 'medium' | 'low';
  action: string;
  rationale: string;
  outcome: string;
};

type NormalizedCodeSnippet = {
  id: string;
  title: string;
  language: string;
  code: string;
};

type NormalizedReasoningAction = {
  tool: string;
  observation: string;
};

type NormalizedReasoningIteration = {
  id: string;
  index: number;
  title: string;
  thought: string;
  tools: string[];
  actions: NormalizedReasoningAction[];
};



const EMPTY_OPTION_LABEL = '—';

const PROBLEM_DEFINITION =
  'Rank these three supplier orders by expected utility. Spencer-Lee Carroll, ' +
  'Sullivan and Bass Lawson, Morris and Ramos.';
const USE_MOCK_RESPONSE = false;

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

const normalizeMathDelimiters = (value: string) =>
  value
    .replace(/&lt;&lt;\s*\$\$/g, '$$')
    .replace(/\$\$\s*&gt;&gt;/g, '$$')
    .replace(/&lt;&lt;\s*\$/g, '$')
    .replace(/\$\s*&gt;&gt;/g, '$')
    .replace(/<<\s*\$\$/g, '$$')
    .replace(/\$\$\s*>>/g, '$$')
    .replace(/<<\s*\$/g, '$')
    .replace(/\$\s*>>/g, '$');

const getAnalysisMarkdown = (response: AgentResponse) => {
  if (typeof response.final_answer === 'string' && response.final_answer.trim()) {
    return normalizeMathDelimiters(response.final_answer.trim());
  }

  const analysisFallback = normalizeText(response.analysis);
  if (analysisFallback.length > 0) {
    return normalizeMathDelimiters(analysisFallback.join('\n\n'));
  }

  return '';
};

const parsePriority = (value?: string): NormalizedRecommendation['priority'] => {
  const normalized = value?.trim().toLowerCase();
  if (normalized === 'high') return 'high';
  if (normalized === 'low') return 'low';
  return 'medium';
};

const normalizeRecommendations = (
  value: Recommendation[] | undefined
): NormalizedRecommendation[] => {
  if (!value) return [];

  const priorityWeight: Record<NormalizedRecommendation['priority'], number> = {
    high: 0,
    medium: 1,
    low: 2,
  };

  return value
    .map<NormalizedRecommendation>((item, index) => {
      if (typeof item === 'string') {
        return {
          id: `rec-${index + 1}`,
          sortIndex: index,
          priority: 'medium',
          action: item.trim() || 'Recommendation',
          rationale: '',
          outcome: '',
        };
      }

      return {
        id: `rec-${index + 1}`,
        sortIndex: index,
        priority: parsePriority(item.priority),
        action: item.action?.trim() || 'Recommendation',
        rationale: item.rationale?.trim() || '',
        outcome: item.expected_outcome?.trim() || '',
      };
    })
    .sort((left, right) => {
      const priorityDiff = priorityWeight[left.priority] - priorityWeight[right.priority];
      if (priorityDiff !== 0) return priorityDiff;
      return left.sortIndex - right.sortIndex;
    });
};

const parseCodeSnippet = (value: string) => {
  const fencedMatch = value.trim().match(/^```([a-zA-Z0-9_-]+)?\n([\s\S]*?)```$/);
  if (!fencedMatch) {
    return {
      language: 'text',
      code: value.trim(),
    };
  }

  return {
    language: fencedMatch[1]?.trim() || 'text',
    code: fencedMatch[2].trim(),
  };
};

const normalizeCodeSnippets = (value: CodeSnippet[] | undefined): NormalizedCodeSnippet[] => {
  if (!value) return [];

  return value
    .map((item, index) => {
      if (typeof item === 'string') {
        const parsed = parseCodeSnippet(item);
        return {
          id: `snippet-${index + 1}`,
          title: `Snippet ${index + 1}`,
          language: parsed.language,
          code: parsed.code,
        };
      }

      const rawCode = item.code ?? item.snippet ?? item.content ?? '';
      const parsed = parseCodeSnippet(rawCode);
      return {
        id: `snippet-${index + 1}`,
        title: item.title?.trim() || item.label?.trim() || `Snippet ${index + 1}`,
        language: item.language?.trim() || parsed.language,
        code: parsed.code,
      };
    })
    .filter((snippet) => snippet.code.length > 0);
};

const summarizeThought = (thought: string, fallbackIndex: number) => {
  const firstMeaningfulLine = thought
    .split('\n')
    .map((line) => line.replace(/^[*-]\s*/, '').trim())
    .find(Boolean);

  if (!firstMeaningfulLine) {
    return `Iteration ${fallbackIndex}`;
  }

  return firstMeaningfulLine.length > 100
    ? `${firstMeaningfulLine.slice(0, 100)}…`
    : firstMeaningfulLine;
};

const normalizeReasoningTrace = (
  value: ReasoningIteration[] | undefined
): NormalizedReasoningIteration[] => {
  if (!value) return [];

  return value.map((iteration, index) => {
    const parsedActions: NormalizedReasoningAction[] = (iteration.actions ?? []).map((action) => ({
      tool: action.tool?.trim() || 'tool',
      observation:
        action.observation?.trim() ||
        action.obs?.trim() ||
        action.result?.trim() ||
        'No observation provided.',
    }));

    const tools = Array.from(
      new Set([
        ...(iteration.tools?.map((tool) => tool.trim()).filter(Boolean) ?? []),
        ...parsedActions.map((action) => action.tool),
      ])
    );
    const thought = iteration.thought?.trim() || 'No thought provided.';
    const indexNumber = iteration.iteration ?? index + 1;

    return {
      id: `iter-${indexNumber}-${index + 1}`,
      index: indexNumber,
      title:
        iteration.title?.trim() ||
        iteration.summary?.trim() ||
        summarizeThought(thought, indexNumber),
      thought,
      tools,
      actions: parsedActions,
    };
  });
};

const normalizeCitations = (value: Citation[] | undefined) => {
  if (!value) return [];

  return value
    .map((citation, index) => {
      if (typeof citation === 'string') {
        return citation.trim();
      }

      return (
        citation.label?.trim() ||
        citation.title?.trim() ||
        citation.source?.trim() ||
        citation.id?.trim() ||
        `Citation ${index + 1}`
      );
    })
    .filter(Boolean);
};




const toPlainText = (value: string) =>
  value
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[(.*?)\]\((.*?)\)/g, '$1')
    .replace(/^\s*[-*]\s+/gm, '')
    .trim();


const priorityClassByLevel: Record<NormalizedRecommendation['priority'], string> = {
  high: 'prio-badge prio-high',
  medium: 'prio-badge prio-med',
  low: 'prio-badge prio-low',
};

type RecBlock = {
  id: string;
  title: string;
  type: 'executive' | 'risk-averse' | 'caution' | 'lean' | 'neutral';
  body: string;
};

const parseRecommendationBlocks = (markdown: string): RecBlock[] => {
  const recMatch = markdown.match(/## Recommendations\s*([\s\S]*)/);
  if (!recMatch) return [];

  const recRaw = recMatch[1];
  const blocks = recRaw.split(/(?:^|\n)###\s+/).filter(Boolean);
  const parsed: RecBlock[] = [];

  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i];
    const lines = block.split('\n');
    const title = lines[0].trim();
    
    let type: RecBlock['type'] = 'neutral';
    const typeMatch = block.match(/\*\*Type\*\*:\s*(executive|risk-averse|caution|lean|neutral)/i);
    if (typeMatch) {
      type = typeMatch[1].toLowerCase() as RecBlock['type'];
    }

    const bodyStr = block.slice(title.length).replace(/\*\*Type\*\*:\s*.*(?:\n|$)/i, '').trim();

    parsed.push({
      id: `rec-block-${i}`,
      title,
      type,
      body: bodyStr
    });
  }

  return parsed;
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
  const [isPanelCollapsed, setIsPanelCollapsed] = useState(false);

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

  const titleStr = response?.task || response?.query || 'Untitled Analysis';
  const titleWords = titleStr.trim().split(/\s+/);
  const memoTitle = titleWords.length > 6 ? titleWords.slice(0, 6).join(' ') + '…' : titleStr;

  const memoId = response?.request_id
    ? `#${response.request_id.slice(0, 8).toUpperCase()}`
    : '—';
  const memoTimestamp = response?.timestamp ? formatTimestamp(response.timestamp) : '—';

  const [serviceStatus] = useState({
    agent: 'operational',
    rag: 'operational',
    env: 'operational'
  });

  const statuses: Record<string, { class: string; text: string }> = {
    'operational': { class: 'green', text: 'Operational' },
    'degraded': { class: 'amber', text: 'Degraded' },
    'down': { class: 'red', text: 'Unavailable' }
  };

  const allGreen = Object.values(serviceStatus).every((s) => s === 'operational');

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
      const resp = await fetch(
        USE_MOCK_RESPONSE ? '/api/mock-response' : 'http://localhost:8003/api/v1/agent/analyze',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }
      );

      if (!resp.ok) {
        setError(`Error ${resp.status}: ${await resp.text()}`);
        return;
      }

      const data = (await resp.json()) as AgentResponse;
      setResponse(data);
      setIsQueryOpen(false);
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
              <div className="status-dot-wrapper">
                <span className={`status-dot ${statuses[serviceStatus.agent].class}`}></span>
                <span className="tooltip">AGENT: {statuses[serviceStatus.agent].text}</span>
              </div>
              <div className="status-dot-wrapper">
                <span className={`status-dot ${statuses[serviceStatus.rag].class}`}></span>
                <span className="tooltip">RAG: {statuses[serviceStatus.rag].text}</span>
              </div>
              <div className="status-dot-wrapper">
                <span className={`status-dot ${statuses[serviceStatus.env].class}`}></span>
                <span className="tooltip">ENV: {statuses[serviceStatus.env].text}</span>
              </div>
            </div>
            <span style={{ color: allGreen ? '#0eaa6e' : 'var(--warn)' }}>
              {allGreen ? 'LIVE' : 'DEGRADED'}
            </span>
          </div>
        </div>
      </header>

      <main className="main-layout" style={{ gridTemplateColumns: isPanelCollapsed ? '1fr 18px' : '1fr 340px' }}>
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
              {USE_MOCK_RESPONSE && (
                <div style={{ background: 'var(--warn)', color: '#fff', padding: '10px 14px', textAlign: 'center', fontWeight: 500, borderRadius: '8px', marginBottom: '16px', fontSize: '13px' }}>
                  Preview mode — displaying example response. Live agent not called.
                </div>
              )}

              {(response || isLoading) && (
                <>
                  <div className="query-block">
                    <div className="query-card">
                      <button
                        type="button"
                        className={`card-head query-card-head ${isQueryOpen ? 'open' : ''}`}
                        onClick={() => setIsQueryOpen((prev) => !prev)}
                      >
                        <div className="answer-agent-avatar query-user-avatar">
                          <svg viewBox="0 0 24 24">
                            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                            <circle cx="12" cy="7" r="4" />
                          </svg>
                        </div>
                        <span className="card-label">User Query</span>
                        <div className="toggle-chevron">
                          <svg viewBox="0 0 24 24">
                            <polyline points="6 9 12 15 18 9" />
                          </svg>
                        </div>
                      </button>

                      <div className={`query-card-body ${isQueryOpen ? 'open' : ''}`}>
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
                  </div>

                  <div className="thread-connector"></div>
                </>
              )}

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

                {!response && !isLoading && !error && (
                  <div className="resp-panels" style={{ borderRadius: 'var(--radius-lg)' }}>
                    <div className="resp-panel active landing" style={{ padding: '28px 28px 24px' }}>
                      <h1>How to use this tool</h1>
                      <p>Use this analytic service to request intelligent optimization simulations from the BeliefCraft operations agent.</p>

                      <table className="landing-table">
                        <thead>
                          <tr><th>Input Field</th><th>Purpose</th><th>Example</th></tr>
                        </thead>
                        <tbody>
                          <tr><td>Problem Definition</td><td>Core strategic objective or challenge</td><td>"Optimize regional fleet coverage"</td></tr>
                          <tr><td>Origin &amp; Destination</td><td>Geographical constraints for operations</td><td>"Berlin, DE" / "Kyiv, UA"</td></tr>
                          <tr><td>Product Type</td><td>Category of assets or goods involved</td><td>"Electronics" / "Automotive"</td></tr>
                          <tr><td>Objective</td><td>Primary analytical optimization target</td><td>"Minimize Cost"</td></tr>
                          <tr><td>Budget</td><td>Financial ceiling or constraint</td><td>"€1.2M" / "$2.5M"</td></tr>
                          <tr><td>Constraints</td><td>Timeframes, policies, SLA limitations</td><td>"Max 30 days, no air freight"</td></tr>
                        </tbody>
                      </table>

                      <span className="muted-note">Note: Problem Definition is required and physically limited to a 1000-character description.</span>

                      <p><strong>What to expect from the agent:</strong> The agent leverages predictive models to analyze the defined problem. You will receive an evaluated baseline, risk assessments, and a fully stylized Markdown memorandum as a response.</p>
                    </div>
                  </div>
                )}

                {response && !isLoading && <ResponsePanel response={response} />}
              </div>
            </div>
          </div>
        </section>

        <section className="panel-section">
          <button
            type="button"
            className="panel-collapse-strip"
            onClick={() => setIsPanelCollapsed((prev) => !prev)}
            aria-label={isPanelCollapsed ? 'Expand panel' : 'Collapse panel'}
          >
            {isPanelCollapsed ? '‹' : '›'}
          </button>
          <div className={`panel-card ${isPanelCollapsed ? 'collapsed' : ''}`}>
            <div className="panel-head">
              <div>
                <div className="panel-pretitle">Input</div>
                <div className="panel-title">Define Strategic Problem</div>
              </div>
            </div>

            <div className={`panel-content ${isPanelCollapsed ? 'collapsed' : ''}`}>
              <div className="form-group">
                <label className="form-label">
                  Problem Definition <span className="required-asterisk">*</span>
                </label>
                <div className="textarea-wrapper">
                  <textarea
                    id="field-problem"
                    className={`form-control ${problemDefinitionDisplay.length > 1000 ? 'error-border' : ''}`}
                    rows={3}
                    value={problemDefinitionDisplay}
                    placeholder=""
                    onChange={(e) => setProblemDefinitionDisplay(e.target.value)}
                  />
                  <div className={`char-counter ${problemDefinitionDisplay.length > 1000 ? 'red' : problemDefinitionDisplay.length >= 800 ? 'amber' : ''}`}>
                    {problemDefinitionDisplay.length} / 1000
                  </div>
                </div>
                {problemDefinitionDisplay.length > 1000 && (
                  <div className="textarea-warning" style={{ display: 'block' }}>
                    Request exceeds the 1000-character limit.
                  </div>
                )}
              </div>

              {isOptionsLoading && <div className="rec-text">Loading dropdown options…</div>}
              {optionsError && <div className="field-error">{optionsError}</div>}

              <div className="input-grid">
                <div className="form-group">
                  <label className="form-label">Origin</label>
                  <CustomSelect
                    options={formOptions ? [{ label: EMPTY_OPTION_LABEL, value: '' }, ...formOptions.origins.map(o => ({ label: o, value: o }))] : []}
                    value={origin}
                    onChange={setOrigin}
                    disabled={!formOptions}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Destination</label>
                  <CustomSelect
                    options={formOptions ? [{ label: EMPTY_OPTION_LABEL, value: '' }, ...formOptions.destinations.map(d => ({ label: d, value: d }))] : []}
                    value={destination}
                    onChange={setDestination}
                    disabled={!formOptions}
                  />
                </div>
              </div>

              <div className="input-grid">
                <div className="form-group">
                  <label className="form-label">Product</label>
                  <CustomSelect
                    options={formOptions ? [{ label: EMPTY_OPTION_LABEL, value: '' }, ...formOptions.products.map((p, i) => ({ label: `${p.name} · ${p.category}`, value: String(i) }))] : []}
                    value={productIndex === null ? '' : String(productIndex)}
                    onChange={(val) => setProductIndex(Number(val))}
                    disabled={!formOptions}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Transport Mode</label>
                  <CustomSelect
                    options={formOptions ? [{ label: EMPTY_OPTION_LABEL, value: '' }, ...formOptions.transport_modes.map(m => ({ label: m, value: m }))] : []}
                    value={transportMode}
                    onChange={setTransportMode}
                    disabled={!formOptions}
                  />
                </div>
              </div>

              <div className="input-grid">
                <div className="form-group">
                  <label className="form-label">Objective</label>
                  <CustomSelect
                    options={[
                      { label: EMPTY_OPTION_LABEL, value: '' },
                      { label: 'Minimize Cost & Time', value: 'Minimize Cost & Time' },
                      { label: 'Minimize Cost', value: 'Minimize Cost' },
                      { label: 'Minimize Time', value: 'Minimize Time' },
                      { label: 'Maximize Reliability', value: 'Maximize Reliability' }
                    ]}
                    value={objective}
                    onChange={setObjective}
                  />
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
                  placeholder=""
                  value={constraints}
                  onChange={(event) => setConstraints(event.target.value)}
                />
              </div>

              <div className="button-group">
                <button className="btn-primary" onClick={submitAnalysis} disabled={isSubmitDisabled || problemDefinitionDisplay.length > 1000}>
                  {isLoading ? 'Analyzing…' : 'Analyze Scenarios'}
                </button>
                <button className="btn-secondary" onClick={clearForm}>
                  Clear
                </button>
              </div>
            </div>
          </div>
        </section>
      </main>
    </>
  );
}

function ResponsePanel({ response }: { response: AgentResponse }) {
  const analysisMarkdown = getAnalysisMarkdown(response);
  const recommendations = normalizeRecommendations(response.recommendations);
  const warnings = normalizeText(response.warnings);
  const citations = normalizeCitations(response.citations);
  const codeSnippets = normalizeCodeSnippets(response.code_snippets);
  const reasoningTrace = normalizeReasoningTrace(response.reasoning_trace);
  const [isTraceOpen, setIsTraceOpen] = useState(false);
  const [openIterations, setOpenIterations] = useState<Record<string, boolean>>({});

  const recBlocks = useMemo(() => parseRecommendationBlocks(analysisMarkdown), [analysisMarkdown]);
  // Remove ## Recommendations block from markdown before rendering so we can render it custom
  const markdownWithoutRecs = analysisMarkdown.replace(/## Recommendations\s*([\s\S]*)/, '').trim();

  const traceIterationCount = response.iterations ?? reasoningTrace.length;
  const traceTokenCount = response.total_tokens;
  const traceExecutionSeconds = response.execution_time_seconds;
  const traceToolCount = useMemo(
    () => new Set(reasoningTrace.flatMap((iteration) => iteration.tools)).size,
    [reasoningTrace]
  );

  const toggleIteration = (iterationId: string) => {
    setOpenIterations((previous) => ({
      ...previous,
      [iterationId]: !previous[iterationId],
    }));
  };

  return (
    <div className="answer-wrapper">
      <div className="answer-card">
        <div className="card-head">
          <div className="answer-agent-avatar">
            <svg viewBox="0 0 24 24">
              <path d="M12 2a4 4 0 0 1 4 4v1h1a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2h-1v1a4 4 0 0 1-4 4 4 4 0 0 1-4-4v-1H7a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h1V6a4 4 0 0 1 4-4z" />
              <circle cx="9" cy="10" r="1" fill="currentColor" stroke="none" />
              <circle cx="15" cy="10" r="1" fill="currentColor" stroke="none" />
            </svg>
          </div>
          <span className="card-label">Agent</span>
          {reasoningTrace.length > 0 && (
            <button
              type="button"
              className={`card-head-toggle ${isTraceOpen ? 'open' : ''}`}
              onClick={() => setIsTraceOpen((prev) => !prev)}
            >
              <span className="card-head-toggle-label">
                Reasoning trace ({reasoningTrace.length})
              </span>
              <div className="toggle-chevron">
                <svg viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
              </div>
            </button>
          )}
        </div>

        {reasoningTrace.length > 0 && (
          <div className={`trace-panel trace-panel-top ${isTraceOpen ? 'open' : ''}`}>
            <div className="trace-meta">
              <span className="trace-stat">
                iterations <span className="trace-stat-val">{traceIterationCount}</span>
              </span>
              {typeof traceTokenCount === 'number' && (
                <span className="trace-stat">
                  tokens <span className="trace-stat-val">{traceTokenCount.toLocaleString()}</span>
                </span>
              )}
              {typeof traceExecutionSeconds === 'number' && (
                <span className="trace-stat">
                  time <span className="trace-stat-val">{traceExecutionSeconds.toFixed(1)} s</span>
                </span>
              )}
              <span className="trace-stat">
                tools <span className="trace-stat-val">{traceToolCount}</span>
              </span>
            </div>
            <div className="iter-list">
              {reasoningTrace.map((iteration) => {
                const isIterationOpen = Boolean(openIterations[iteration.id]);
                const allActionsFailed =
                  iteration.actions.length > 0 &&
                  iteration.actions.every((action) => /error|runtimeerror/i.test(action.observation));
                return (
                  <div key={iteration.id} className="iter-row">
                    <button
                      type="button"
                      className="iter-head"
                      onClick={() => toggleIteration(iteration.id)}
                    >
                      <div className={`iter-n ${allActionsFailed ? 'iter-n-failed' : ''}`}>{iteration.index}</div>
                      <div className="iter-summary">
                        <div className="iter-title-text">{iteration.title}</div>
                        {iteration.tools.length > 0 && (
                          <div className="iter-tools-row">
                            {iteration.tools.map((tool) => (
                              <span key={`${iteration.id}-${tool}`} className="iter-tool-pill">
                                {tool}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className={`iter-chev ${isIterationOpen ? 'open' : ''}`}>
                        <svg viewBox="0 0 24 24">
                          <polyline points="6 9 12 15 18 9" />
                        </svg>
                      </div>
                    </button>

                    <div className={`iter-detail ${isIterationOpen ? 'open' : ''}`}>
                      <div className="thought-bubble">{iteration.thought}</div>

                      {iteration.actions.length > 0 ? (
                        <>
                          <div className="tool-calls-label">Tool calls</div>
                          {iteration.actions.map((action, actionIndex) => (
                            (() => {
                              const isError = /error|runtimeerror/i.test(action.observation);
                              const isSuccess = /success/i.test(action.observation);
                              const observationClass = isError
                                ? 'tc-obs tc-obs-error'
                                : isSuccess
                                  ? 'tc-obs tc-obs-success'
                                  : 'tc-obs';
                              return (
                            <div
                              key={`${iteration.id}-action-${action.tool}-${actionIndex + 1}`}
                              className="tool-call-row"
                            >
                              <span className="tc-name">{action.tool}</span>
                              <span className={observationClass}>{action.observation}</span>
                            </div>
                              );
                            })()
                          ))}
                        </>
                      ) : (
                        <div className="tool-calls-label">No tool calls recorded.</div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div className="answer-content">
          <div className="md-body">
            <ReactMarkdown
              remarkPlugins={[remarkMath]}
              rehypePlugins={[rehypeKatex]}
              components={{
                h2: ({ children }) => (
                  <div className="answer-section-label">
                    <span className="answer-section-label-text">{children}</span>
                  </div>
                ),
                h3: ({ children }) => (
                  <div className="answer-rec-title">{children}</div>
                ),
              }}
            >
              {markdownWithoutRecs}
            </ReactMarkdown>
          </div>

          {recBlocks.length > 0 && (
            <div className="answer-rec-section">
              <div className="answer-section-label">Recommendations</div>
              {recBlocks.map((block) => (
                <div key={block.id} className={`answer-rec-block answer-rec-${block.type}`}>
                  <div className="answer-rec-header">
                    <span className="answer-rec-dot" />
                    <span className="answer-rec-title">{block.title}</span>
                  </div>
                  <div className="answer-rec-body">
                    <ReactMarkdown>{block.body}</ReactMarkdown>
                  </div>
                </div>
              ))}
            </div>
          )}

          {citations.length > 0 && (
            <div className="citation-tags" style={{ marginTop: '2rem' }}>
              {citations.map((citation, index) => (
                <span key={`${citation}-${index + 1}`} className="tag tag-info">
                  {citation}
                </span>
              ))}
            </div>
          )}
        </div>



        {codeSnippets.length > 0 && (
          <div className="card-section">
            <div className="section-head">
              <div className="section-icon si-tech">
                <svg viewBox="0 0 24 24">
                  <polyline points="16 18 22 12 16 6" />
                  <polyline points="8 6 2 12 8 18" />
                </svg>
              </div>
              <span className="section-title">Technical Blocks</span>
            </div>
            <div className="code-snippets-body">
              {codeSnippets.map((snippet) => (
                <div key={snippet.id} className="code-snippet-card">
                  <div className="code-snippet-title">{snippet.title}</div>
                  <SyntaxHighlighter
                    style={oneLight}
                    language={snippet.language}
                    PreTag="div"
                    customStyle={{ margin: 0, padding: '14px 16px', borderRadius: '8px' }}
                  >
                    {snippet.code}
                  </SyntaxHighlighter>
                </div>
              ))}
            </div>
          </div>
        )}

        {warnings.length > 0 && (
          <div className="card-section">
            <div className="section-head">
              <div className="section-icon si-recs">
                <svg viewBox="0 0 24 24">
                  <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                  <line x1="12" y1="9" x2="12" y2="13" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
              </div>
              <span className="section-title">Warnings</span>
            </div>
            <div className="recs-body">
              <div className="recs-list">
                {warnings.map((warning, index) => (
                  <div key={`${warning}-${index + 1}`} className="rec-card">
                    <div className="rec-body-col">
                      <div className="rec-rationale">{warning}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
