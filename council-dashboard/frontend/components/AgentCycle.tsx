'use client';

export type Cycle = {id:string;tick:number;status:string;planning_status?:string;assessments:{role:string;observation_hash:string;request_id:string;assessment:{summary:string;recommended_jobs:string[];missing_information:string[];source_ids:string[]}}[];director?:{summary:string;priority:string[]}};

export default function AgentCycle({cycle}:{cycle?:Cycle|null}) {
  return <section className="receipt-list" aria-label="Observe Think Act Remember">
    <h2 className="section-heading">Observe → Think → Act → Remember</h2>
    {!cycle ? <p>The independent assessment loop has not run for this mission yet. Existing receipts remain available below.</p> : <>
      <p>Step {cycle.tick} · {cycle.status}. Each specialist assessed the same world snapshot before seeing another specialist’s proposal. The director then reconciled their recommendations.</p>
      {cycle.assessments.map(a=><details className="receipt" key={a.role}>
        <summary><strong>{a.role === 'assurance' ? 'Independent evidence review' : a.role+' lead'}</strong><span>Independent assessment</span></summary>
        <p>{a.assessment.summary}</p>
        <p><strong>Recommended work:</strong> {a.assessment.recommended_jobs.join(', ') || 'No work recommended'}</p>
        <h3>Information still needed</h3>
        {a.assessment.missing_information.length ? <ul>{a.assessment.missing_information.map((g,i)=><li key={i}>{g}</li>)}</ul> : <p>No additional gaps reported by this agent. This is not proof of engineering validity.</p>}
        <p><strong>Cited sources:</strong> {a.assessment.source_ids.join(', ')}</p>
        <p>Its assessment, tool results and work outcomes are retained for its next planning cycle. Full history is available in the mission export.</p>
        <details><summary>Inspect record identifiers</summary><p>Request: {a.request_id}</p><p style={{overflowWrap:'anywhere'}}>Shared observation hash: {a.observation_hash}</p></details>
      </details>)}
      {cycle.director&&<article className="receipt"><h3>Director’s decision</h3><p>{cycle.director.summary}</p><p>Work order: {cycle.director.priority.join(' → ')}</p></article>}
      <p>Only validated work orders can execute. Evidence review does not certify physical feasibility; missing measurements remain missing.</p>
    </>}
  </section>;
}
