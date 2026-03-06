# 21-DAY AGENTIC AI IMPLEMENTATION PLAN
## Synthesized from 12 Books on AI Agents, LLMs, RAG, MCP, and Enterprise AI
### Josef Hofman — March 4–25, 2026

> Cíl: Za 21 dní vybudovat produkční-ready agentic AI infrastrukturu across Clawdia, EchoDialer, CRM_CLEAN a JI.
> Každý den = konkrétní deliverable. Žádné teorie bez kódu.

---

## KNOWLEDGE BASE (What the Books Taught Us)

### Core Architecture Insight
**LLM je stateless. Framework je stateful.** (Sayfan, "Design Multi-Agent AI Systems")
- Agent loop: Sense → Think → Act → Observe → Loop
- LLM nedrží stav mezi iteracemi — tvůj kód spravuje memory, tools, a context
- Framework rozhoduje CO dostane LLM na vstup v každém kroku

### 5 Orchestration Patterns (Sayfan)
1. **Sequential** — agenti řetězí výstupy: A → B → C
2. **Parallel** — nezávislé tasky běží současně, výsledky se mergují
3. **Hierarchical** — supervisor deleguje sub-agentům
4. **Collaborative** — agenti spolu komunikují peer-to-peer
5. **Competitive** — více agentů řeší stejný problém, vybere se nejlepší výsledek

### The Memory Trinity (Taulli, "Building Generative AI Agents")
1. **Episodic** — konkrétní minulé eventy s timestampem
2. **Semantic** — fakta, znalosti, vztahy
3. **Procedural** — naučené postupy a strategie

---

## WEEK 1: FOUNDATIONS (Days 1–7)
### Téma: Agent Loop, Memory, Tool Infrastructure

---

### DAY 1 — Agent Core Loop + State Machine
**Deliverable:** Univerzální agent runtime pro všechny projekty

**Co implementovat:**
- Sense-Think-Act-Observe loop jako TypeScript class
- State machine: `idle → sensing → thinking → acting → observing → idle`
- Conversation history manager (sliding window + summarization)
- Tool registry pattern — agenti registrují tools dynamicky

**Architektura (z Biswas/Talukdar "Building Agentic AI Systems"):**
```
┌─────────────────────────────────┐
│         Agent Runtime           │
├─────────────────────────────────┤
│  State: { conversation, memory, │
│          tools, config }        │
│                                 │
│  loop():                        │
│    input = sense()              │
│    context = buildContext()     │
│    decision = think(context)    │
│    if decision.type == 'tool':  │
│      result = act(decision)     │
│      observe(result)            │
│      loop() // continue         │
│    else:                        │
│      return decision.response   │
└─────────────────────────────────┘
```

**Klíčový insight:** LLM vrací buď text response (task complete) nebo tool call v strukturovaném formátu. Framework parsuje a routuje.

**Proč:** Bez tohohle každý projekt staví agenty jinak. Jeden runtime = konzistence + rychlost iterace.

---

### DAY 2 — Memory Architecture (3-Layer System)
**Deliverable:** Supabase-backed memory system pro agenty

**Co implementovat:**
- **Episodic Memory**: `agent_episodes` tabulka — timestamped interactions
  - Columns: `id, agent_id, user_id, event_type, content, embedding, metadata, created_at`
  - Vector search přes pgvector pro "co se stalo naposledy, když..."
- **Semantic Memory**: `agent_knowledge` tabulka — fakta a znalosti
  - Columns: `id, agent_id, domain, fact, embedding, confidence, source, updated_at`
  - Agent může přidávat nové fakta z interakcí
- **Procedural Memory**: `agent_procedures` tabulka — naučené postupy
  - Columns: `id, agent_id, task_type, procedure, success_rate, usage_count, last_used`
  - Trackuje co funguje a co ne

**Z Baker ("Agentic AI For Dummies") — Memory Sharing:**
- Policy updates: agent updatuje pravidla a sdílí s ostatními
- Embedding sharing: kompaktní vektory zachycující naučené znalosti
- Memory synchronization: periodické syncy do shared store

**Proč pro tvoje projekty:**
- **EchoDialer:** Episodic = každý call. Semantic = product knowledge. Procedural = nejlepší skripty.
- **JI:** Episodic = student sessions. Semantic = gramatická pravidla. Procedural = optimální teaching strategie per student type.
- **Clawdia:** Long-term user preferences, past decisions, learned patterns.

---

### DAY 3 — Tool System + MCP Integration
**Deliverable:** MCP-compatible tool infrastructure

**Co implementovat:**
- Tool interface: `{ name, description, parameters, execute() }`
- MCP server pro vlastní tools (JSON-RPC protocol)
- MCP client pro připojení k externím službám
- Tool selection logic — agent rozhoduje kdy použít jaký tool

**Z Baker — MCP Protocol:**
- Client-server model přes JSON-RPC
- AI agent = client, data source/service = server
- "USB-C pro AI" — univerzální adapter
- Microsoft adoptoval pro Copilot Studio

**Z Sayfan — Tool Call Flow:**
```json
{
  "tool_calls": [{
    "id": "call_123",
    "type": "function",
    "function": {
      "name": "search_crm",
      "arguments": "{\"query\": \"deals closing this month\"}"
    }
  }]
}
```
Framework executuje tool → result appendne do conversation history → pošle zpět LLMku.

**Konkrétní tools pro Day 3:**
1. `supabase_query` — dotazy do DB
2. `send_email` — Resend integration
3. `search_knowledge` — vector search v semantic memory
4. `web_scrape` — získání dat z webu

---

### DAY 4 — RAG Pipeline v1 (Vector Search + Retrieval)
**Deliverable:** Funkční RAG systém s Supabase pgvector

**5-Step Pipeline (z Ozdemir "Building Agentic AI Workflows"):**

1. **Indexing:** Embed dokumenty → uložit do pgvector s metadaty
2. **State Management:** LangGraph-style state objekt pro každý query
3. **Retrieval:** Cosine similarity search — embed query stejným embedderem jako dokumenty
4. **Generation:** LLM dostane: user query + retrieved chunks + instructions
5. **Assembly:** Conditional routing — pokud confidence < threshold → request more context

**Similarity Metrics (z Ozdemir):**
| Metric | Speed | Best For |
|--------|-------|----------|
| Cosine Similarity | Medium | Normalized text embeddings |
| Dot Product | Fast | When vectors have magnitude 1 |
| Euclidean (L2) | Slow | Dense, low-dimensional vectors |
| Manhattan (L1) | Fast | Sparse high-dimensional data |

**Klíčový insight:** Když všechny vektory mají magnitude 1 (většina embedding modelů), dot product a cosine similarity dávají identické výsledky. Dot product je rychlejší.

**Proč:**
- **EchoDialer:** RAG přes product docs, competitor intel, successful pitch scripts
- **JI:** RAG přes grammar rules, vocabulary, exercise templates
- **CRM:** RAG přes contact notes, email history, call transcripts

---

### DAY 5 — Semantic Few-Shot Learning Engine
**Deliverable:** Embedding-based example selection pro všechny LLM cally

**Co implementovat (z Ozdemir):**
Místo random few-shot examples → vybírej příklady, které jsou sémanticky nejpodobnější current query.

```typescript
async function getSemanticExamples(query: string, examplePool: Example[], k: number = 3) {
  const queryEmbedding = await embed(query);
  const scored = examplePool.map(ex => ({
    ...ex,
    similarity: cosineSimilarity(queryEmbedding, ex.embedding)
  }));
  return scored.sort((a, b) => b.similarity - a.similarity).slice(0, k);
}
```

**Pool příkladů per projekt:**
- **EchoDialer:** Past successful call transcripts → embed → store. Při novém callu vybereš nejpodobnější minulé cally jako examples.
- **JI:** Příklady správných/špatných odpovědí per grammar topic → embed → select nejrelevantnější pro aktuální otázku studenta.
- **CRM:** Past successful outreach emails → select nejpodobnější pro current prospect profile.

**Proč je to game-changer:** Ozdemir ukazuje měřitelně lepší výsledky vs. random examples. Minimální implementační effort, maximální ROI.

---

### DAY 6 — Context Engineering Framework
**Deliverable:** 5-layer context builder pro agenty

**5 vrstev (z Baker "Agentic AI For Dummies"):**

1. **Core Knowledge Layer (RAG):**
   - Retreived dokumenty z Day 4 pipeline
   - Dynamicky vybrané na základě query relevance

2. **Memory Layer:**
   - Episodic: "Minule jste řešili X"
   - Semantic: "Fakt Y je důležitý pro tento kontext"
   - Procedural: "Nejlepší postup pro tenhle typ úlohy je Z"

3. **Tool Orchestration Layer:**
   - Jaké tools jsou dostupné
   - Pravidla pro kdy použít jaký tool
   - Decision policies

4. **Dynamic Context Selection:**
   - Algoritmus, který vybere NEJRELEVANTNĚJŠÍ info pro danou interakci
   - Prevence information overload (context window limit)
   - Scoring: relevance × recency × importance

5. **Error Learning Layer:**
   - Feedback z minulých chyb
   - Adaptive instructions basované na failure patterns

**Context Window Budget:**
```
System prompt:     ~500 tokens (identity, rules)
Memory context:    ~1000 tokens (relevant episodes + facts)
RAG context:       ~2000 tokens (retrieved documents)
Few-shot examples: ~1000 tokens (semantic selection)
Tool descriptions: ~500 tokens (available capabilities)
Conversation:      ~2000 tokens (recent messages)
─────────────────────────────────
Total budget:      ~7000 tokens per agent call
```

**Proč:** Baker zdůrazňuje — context engineering ≠ prompt engineering. Prompt = jedna instrukce. Context = celé prostředí, ve kterém agent operuje. Obojí potřebuješ.

---

### DAY 7 — Agent Evaluation & Testing Framework
**Deliverable:** Automated eval pipeline pro měření kvality agentů

**Z Ozdemir — Evaluation Methodology:**

Tři typy evaluace:
1. **Reference-based:** Porovnání s ground truth (SQA — SQL Query Accuracy)
2. **Rubric-based:** Heuristiky a pravidla (je odpověď helpful? accurate? harmless?)
3. **Threshold-based:** Cílová metrika (response time < 2s, accuracy > 80%)

**Implementace:**
```typescript
interface EvalResult {
  accuracy: number;      // vs ground truth
  relevance: number;     // rubric score 0-1
  latency_ms: number;    // response time
  cost_usd: number;      // API cost
  tool_usage: string[];  // which tools were called
  memory_hits: number;   // how many memory lookups
}

async function evaluateAgent(testCases: TestCase[]): Promise<EvalResult[]> {
  return Promise.all(testCases.map(async tc => {
    const start = Date.now();
    const result = await agent.run(tc.input);
    return {
      accuracy: compareWithGroundTruth(result, tc.expected),
      relevance: await rubricScore(result, tc.criteria),
      latency_ms: Date.now() - start,
      cost_usd: result.usage.total_cost,
      tool_usage: result.tools_called,
      memory_hits: result.memory_queries
    };
  }));
}
```

**Z Ozdemir — Model Comparison Insight:**
| Model | Accuracy | Cost | Latency |
|-------|----------|------|---------|
| GPT-4o-Mini | ~45% | $ | Fast |
| Claude Sonnet | ~50% | $$ | Medium |
| Gemini 2.5 Pro | ~57% | $$$$$ (28x) | Slow |
| Mistral 7b | ~19% | ¢ | Very Fast |

**Takeaway:** Best accuracy ≠ best choice. Balance accuracy/cost/latency per use case.

---

## WEEK 2: MULTI-AGENT SYSTEMS (Days 8–14)
### Téma: Orchestration, Communication, Specialized Agents

---

### DAY 8 — Multi-Agent Orchestrator (Hierarchical Pattern)
**Deliverable:** Supervisor agent, který deleguje sub-agentům

**Z Sayfan — Hierarchical Orchestration:**
```
┌──────────────────────┐
│   Supervisor Agent    │
│  (task decomposition) │
└──────────┬───────────┘
     ┌─────┼─────┐
     ▼     ▼     ▼
  Agent   Agent  Agent
  (CRM)   (RAG)  (Email)
```

**Supervisor logic:**
1. Receive task from user
2. Decompose into subtasks
3. Route each subtask to best-fit agent
4. Collect results
5. Synthesize final response
6. If quality < threshold → re-delegate with feedback

**Z Biswas/Talukdar — Hybrid Architecture:**
- **Reactive layer** (bottom): rychlé, low-level response na real-time eventy
- **Deliberative layer** (top): high-level reasoning, planning, strategy
- Reactive dává feedback deliberative; deliberative guiduje reactive

**Implementace:**
```typescript
class SupervisorAgent extends Agent {
  private subAgents: Map<string, Agent>;

  async decompose(task: string): Promise<SubTask[]> {
    // LLM decides how to split the task
    return this.think({
      instruction: "Decompose this task into subtasks and assign to agents",
      availableAgents: Array.from(this.subAgents.keys()),
      task
    });
  }

  async orchestrate(task: string): Promise<Result> {
    const subtasks = await this.decompose(task);

    // Parallel execution for independent tasks
    const independent = subtasks.filter(st => !st.dependsOn.length);
    const dependent = subtasks.filter(st => st.dependsOn.length > 0);

    const parallelResults = await Promise.all(
      independent.map(st => this.subAgents.get(st.agent)!.run(st))
    );

    // Sequential for dependent tasks
    for (const st of dependent) {
      const agentResult = await this.subAgents.get(st.agent)!.run(st);
      // Feed result to next dependent task
    }

    return this.synthesize(parallelResults);
  }
}
```

---

### DAY 9 — Sales Agent Team (CrewAI Pattern)
**Deliverable:** 3-agent sales team pro EchoDialer/ai-sales-monster

**Z Lanham ("AI Agents in Action") — CrewAI Pattern:**
Role-based agent teams. Každý agent má definovanou roli a spolupracuje přes natural language.

**Team:**
1. **Researcher Agent:**
   - Role: Najít info o prospectu (LinkedIn, web, CRM history)
   - Tools: `web_scrape`, `search_crm`, `linkedin_lookup`
   - Output: Prospect brief (company info, decision makers, pain points)

2. **Strategist Agent:**
   - Role: Vytvořit approach strategy na základě researche
   - Tools: `search_knowledge` (past successful approaches), `semantic_examples`
   - Input: Prospect brief from Researcher
   - Output: Call script, key talking points, objection responses

3. **Caller Agent:**
   - Role: Vést call / generovat personalizovaný outreach
   - Tools: `send_email`, `create_task`, `update_crm`
   - Input: Strategy from Strategist
   - Output: Call notes, next steps, CRM updates

**Sequential flow:** Research → Strategy → Execution

**Z Biswas/Talukdar — Theory of Mind Modeling:**
Každý agent udržuje model toho, co vědí ostatní agenti. Strategist ví, že Researcher už našel pricing info → nebude to hledat znovu.

---

### DAY 10 — A2A Protocol Implementation
**Deliverable:** Agent-to-agent communication layer

**Z Baker — A2A Protocol:**
- Capability discovery — agenti se ptají "co umíš?"
- Task orchestration — delegace a koordinace
- State updates — "dokončil jsem krok 3"
- Multimodal content exchange

**Z Sayfan — Practical A2A Implementation:**
```typescript
interface AgentMessage {
  from: string;          // agent_id
  to: string;            // agent_id or "broadcast"
  type: 'task' | 'result' | 'status' | 'query' | 'capability';
  conversationId: string;
  content: any;
  metadata: {
    timestamp: number;
    priority: 'low' | 'medium' | 'high';
    requiresResponse: boolean;
  };
}

class AgentCommunicationBus {
  private agents: Map<string, Agent>;
  private messageQueue: AgentMessage[];

  async send(msg: AgentMessage): Promise<void> {
    if (msg.to === 'broadcast') {
      for (const [id, agent] of this.agents) {
        if (id !== msg.from) await agent.receive(msg);
      }
    } else {
      await this.agents.get(msg.to)!.receive(msg);
    }
  }

  async discoverCapabilities(agentId: string): Promise<string[]> {
    const agent = this.agents.get(agentId)!;
    return agent.getCapabilities(); // tools + skills list
  }
}
```

---

### DAY 11 — Self-Correcting Agent Loop (AutoGen Pattern)
**Deliverable:** Proxy evaluation pattern pro quality assurance

**Z Lanham — AutoGen Proxy Pattern:**
- UserProxy agent = evaluátor
- AssistantAgent = worker
- Proxy reviewuje, hodnotí, dává feedback v iteration loop
- Loop pokračuje dokud proxy není spokojený

**Implementace:**
```typescript
class ProxyEvaluator extends Agent {
  maxIterations = 3;
  qualityThreshold = 0.8;

  async evaluateAndRefine(task: string, workerAgent: Agent): Promise<Result> {
    let result = await workerAgent.run(task);
    let iteration = 0;

    while (iteration < this.maxIterations) {
      const evaluation = await this.evaluate(result);

      if (evaluation.score >= this.qualityThreshold) {
        return result; // Good enough
      }

      // Generate specific feedback
      const feedback = await this.generateFeedback(result, evaluation);
      result = await workerAgent.run({
        originalTask: task,
        previousAttempt: result,
        feedback: feedback
      });

      iteration++;
    }

    return result; // Best effort after max iterations
  }
}
```

**Z Baker — Self-Correcting Continuous Improvement:**
- Failure sharing přes shared memory
- Meta-reasoning — agenti přemýšlejí o tom, JAK přemýšlejí
- Policy updates po failures

**Proč:** Bez tohohle agenti opakují stejné chyby. S tímhle se zlepšují s každou interakcí.

---

### DAY 12 — Knowledge Graph Construction
**Deliverable:** Graph-based knowledge layer v Supabase

**Z Raieli ("Building AI Agents with LLMs, RAG, and Knowledge Graphs"):**

**Graph Structure:**
- **Nodes:** Entities (customers, products, features, problems)
- **Edges:** Relationships (bought, reported, solved, likes)
- **Properties:** Metadata on nodes and edges

**Supabase Implementation:**
```sql
-- Nodes table
CREATE TABLE kg_nodes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type TEXT NOT NULL, -- 'customer', 'product', 'feature', 'problem'
  name TEXT NOT NULL,
  properties JSONB DEFAULT '{}',
  embedding VECTOR(1536),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Edges table
CREATE TABLE kg_edges (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID REFERENCES kg_nodes(id),
  target_id UUID REFERENCES kg_nodes(id),
  relationship TEXT NOT NULL, -- 'bought', 'reported', 'solved'
  properties JSONB DEFAULT '{}',
  weight FLOAT DEFAULT 1.0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Graph traversal function
CREATE OR REPLACE FUNCTION traverse_graph(
  start_node UUID,
  max_depth INT DEFAULT 3,
  relationship_filter TEXT[] DEFAULT NULL
) RETURNS TABLE(node_id UUID, depth INT, path UUID[]) AS $$
  WITH RECURSIVE graph AS (
    SELECT target_id AS node_id, 1 AS depth, ARRAY[source_id, target_id] AS path
    FROM kg_edges WHERE source_id = start_node
    AND (relationship_filter IS NULL OR relationship = ANY(relationship_filter))

    UNION ALL

    SELECT e.target_id, g.depth + 1, g.path || e.target_id
    FROM kg_edges e JOIN graph g ON e.source_id = g.node_id
    WHERE g.depth < max_depth
    AND NOT e.target_id = ANY(g.path) -- prevent cycles
    AND (relationship_filter IS NULL OR e.relationship = ANY(relationship_filter))
  )
  SELECT * FROM graph;
$$ LANGUAGE SQL;
```

**Z Raieli — GraphRAG:**
Kombinace graph traversal + vector search. Query embeddings najdou relevantní nodes, graph traversal expanduje kontext přes relationships.

**Proč:**
- **CRM:** "Kteří zákazníci, co koupili produkt X, měli taky problém Y?" → Graph traversal.
- **EchoDialer:** "Jaké obejekce vznesli podobní zákazníci?" → Graph search přes customer-objection edges.
- **JI:** "Studenti, kteří měli problém s dativem, měli taky problém s..." → Learning path optimization.

---

### DAY 13 — Advanced RAG: HyDE + Hybrid Search
**Deliverable:** Production-grade retrieval pipeline

**Z Raieli — HyDE (Hypothetical Document Embeddings):**
Místo přímého embeddingu query → nech LLM vygenerovat hypotetickou odpověď → embed TU → hledej podobné dokumenty.

```typescript
async function hydeRetrieval(query: string): Promise<Document[]> {
  // Step 1: Generate hypothetical answer
  const hypothetical = await llm.generate({
    prompt: `Answer this question as if you had perfect knowledge: ${query}`,
    temperature: 0.7
  });

  // Step 2: Embed the hypothetical answer (not the original query!)
  const embedding = await embed(hypothetical);

  // Step 3: Search for real documents similar to the hypothetical answer
  return vectorSearch(embedding, topK: 5);
}
```

**Proč HyDE funguje:** Hypotetická odpověď je sémanticky bližší relevantním dokumentům než původní otázka.

**Z Raieli — Propositions-Based Chunking:**
Místo fixních chunk sizes → rozlož dokument na atomické propozice (single-fact statements). Každá propozice = jeden embedding.

**Hybrid Search (BM25 + Semantic):**
```typescript
async function hybridSearch(query: string, alpha: number = 0.7): Promise<Document[]> {
  const [semanticResults, keywordResults] = await Promise.all([
    vectorSearch(await embed(query), topK: 20),
    bm25Search(query, topK: 20)
  ]);

  // Reciprocal Rank Fusion
  const scores = new Map<string, number>();
  semanticResults.forEach((doc, i) => {
    scores.set(doc.id, (scores.get(doc.id) || 0) + alpha / (i + 60));
  });
  keywordResults.forEach((doc, i) => {
    scores.set(doc.id, (scores.get(doc.id) || 0) + (1 - alpha) / (i + 60));
  });

  return Array.from(scores.entries())
    .sort(([, a], [, b]) => b - a)
    .slice(0, 10)
    .map(([id]) => allDocs.get(id)!);
}
```

**Query Routing (z Raieli):**
- Structured queries ("deals closing this month") → SQL
- Semantic queries ("what concerns did the prospect raise") → Vector search
- Factual queries ("what's our pricing for X") → Knowledge graph
- Hybrid queries → BM25 + Semantic + Reranking

---

### DAY 14 — Competitive Agent Pattern + Mid-Sprint Review
**Deliverable:** Competitive evaluation pro lepší output quality + Week 2 retrospective

**Z Sayfan — Competitive Orchestration (Pattern #5):**
Víc agentů řeší stejný problém → vyber nejlepší výsledek.

```typescript
async function competitiveGeneration(task: string): Promise<Result> {
  // Run 3 different approaches in parallel
  const results = await Promise.all([
    agent1.run(task), // e.g., structured approach
    agent2.run(task), // e.g., creative approach
    agent3.run(task)  // e.g., data-driven approach
  ]);

  // Judge selects the best
  const evaluation = await judgeAgent.evaluate(results, task);
  return results[evaluation.bestIndex];
}
```

**Proč:** Pro high-stakes tasky (sales pitch, marketing copy) → competitive generation dává measurably better results.

**Mid-Sprint Review:**
- [ ] Agent runtime funguje?
- [ ] Memory system ukládá a retrievuje?
- [ ] RAG pipeline vrací relevantní výsledky?
- [ ] Multi-agent orchestrace komunikuje?
- [ ] Eval pipeline měří kvalitu?
- Run full eval suite, identifikuj weak points pro Week 3.

---

## WEEK 3: PRODUCTION & OPTIMIZATION (Days 15–21)
### Téma: Fine-tuning, Security, Deploy, Scale

---

### DAY 15 — Stateful Conversations (LangGraph MemorySaver)
**Deliverable:** Persistent conversation state across sessions

**Z Ozdemir — LangGraph Pattern:**
- MemorySaver checkpoint: serializuje/deserializuje threads
- Interrupt function pro human-in-the-loop
- Conditional edges pro dynamic routing

**Implementace pro Supabase:**
```typescript
class ConversationManager {
  async saveState(threadId: string, state: AgentState): Promise<void> {
    await supabase.from('conversation_states').upsert({
      thread_id: threadId,
      state: JSON.stringify(state),
      updated_at: new Date()
    });
  }

  async resumeConversation(threadId: string): Promise<AgentState> {
    const { data } = await supabase
      .from('conversation_states')
      .select('state')
      .eq('thread_id', threadId)
      .single();
    return JSON.parse(data.state);
  }

  // Human-in-the-loop interrupt
  async interrupt(threadId: string, question: string): Promise<string> {
    await this.saveState(threadId, { ...currentState, waiting_for_human: true });
    // State is persisted — can resume hours/days later
    return question; // Sent to user
  }
}
```

**Proč:**
- **JI:** Student starts lesson → leaves → comes back 2 days later → picks up exactly where they left off
- **EchoDialer:** Multi-call deal cycle → agent remembers everything from previous calls
- **Clawdia:** Persistent assistant that actually knows your history

---

### DAY 16 — Security & Governance (OWASP for AI)
**Deliverable:** Security hardening pro všechny AI agenty

**Z Enterprise knihy — OWASP Top 10 for Agentic AI:**

| # | Threat | Mitigation |
|---|--------|------------|
| 1 | Memory Poisoning | Input validation, anomaly detection na memory writes |
| 2 | Tool Misuse | Whitelist povolených actions, confirmation pro destructive ops |
| 3 | Privilege Compromise | RBAC per agent, least privilege principle |
| 4 | Resource Overload | Rate limiting na agent spawning, max iterations |
| 5 | Cascading Hallucinations | Fact-checking pipeline, confidence scoring |
| 6 | Goal Manipulation | Immutable system prompts, goal validation per step |
| 7 | Deceptive Behaviors | Output auditing, behavioral monitoring |
| 8 | Untraceability | Full audit log — every decision, every tool call |
| 9 | Identity Spoofing | Agent authentication, signed messages |
| 10 | HITL Overflow | Prioritized review queue, auto-escalation thresholds |

**3Lock Governance (z Enterprise knihy):**
```typescript
class GovernanceLayer {
  // Ethical Lock — bias audit
  async ethicalCheck(action: AgentAction): Promise<boolean> {
    return !containsBias(action) && isCompliant(action);
  }

  // Operational Lock — rollback capability
  async operationalCheck(action: AgentAction): Promise<boolean> {
    if (action.isDestructive) {
      await this.createSnapshot(); // Can always rollback
      return await this.requestHumanApproval(action);
    }
    return true;
  }

  // Strategic Lock — alignment check
  async strategicCheck(action: AgentAction): Promise<boolean> {
    return alignsWithBusinessGoals(action, this.currentObjectives);
  }
}
```

**Audit Logging:**
```sql
CREATE TABLE agent_audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id TEXT NOT NULL,
  action_type TEXT NOT NULL,
  input JSONB,
  output JSONB,
  tools_called TEXT[],
  decision_reasoning TEXT,
  confidence FLOAT,
  latency_ms INT,
  cost_usd FLOAT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

### DAY 17 — Domain-Specific LoRA Fine-Tuning Strategy
**Deliverable:** Fine-tuning pipeline design + dataset preparation

**Z Raieli — LoRA (Low-Rank Adaptation):**
- `W' = W + BA` kde B a A jsou low-rank matice
- Pro 175B model: trénuješ jen ~17.5M parametrů (0.01%)
- Žádné zvýšení inference cost — merged back při deployment
- Můžeš mít multiple adapters pro různé tasky

**Fine-tuning Datasets per Project:**

**EchoDialer/Sales:**
```jsonl
{"messages": [
  {"role": "system", "content": "You are a senior B2B sales rep..."},
  {"role": "user", "content": "The prospect says: 'Your pricing is too high'"},
  {"role": "assistant", "content": "I understand budget is a concern..."}
]}
```
- Zdroj: Best performing call transcripts
- Volume: 500-1000 examples
- Focus: Objection handling, qualification, closing

**JI/Language Learning:**
```jsonl
{"messages": [
  {"role": "system", "content": "You are a Czech language tutor..."},
  {"role": "user", "content": "Jak se řekne 'I would like' v češtině?"},
  {"role": "assistant", "content": "Chtěl/chtěla bych. Používáme podmínkový způsob..."}
]}
```
- Zdroj: Expert tutor transcripts
- Volume: 1000+ examples
- Focus: Grammar explanations, error correction, natural conversation

**Z Raieli — DPO (Direct Preference Optimization):**
Jednodušší alternativa k RLHF. Preference pairs:
```jsonl
{
  "prompt": "Prospect asks about pricing",
  "chosen": "Great question. Let me share the value you'd get...",
  "rejected": "Our pricing is $X per month..."
}
```

**Z Raieli — Knowledge Distillation:**
Claude Opus (teacher) → smaller model (student). Opus generuje soft targets, menší model se učí matchovat. Výsledek: rychlý, levný model s capabilities blízko Opusu.

---

### DAY 18 — Edge Function Agents (Serverless Deployment)
**Deliverable:** Supabase Edge Functions pro agent endpoints

**Architecture:**
```
Client → Supabase Edge Function → Agent Runtime → Claude API
                                      ↓
                                 Supabase DB
                                 (memory, knowledge, audit)
```

**Edge Function Template:**
```typescript
// supabase/functions/agent-sales/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

serve(async (req) => {
  const { task, context, threadId } = await req.json();

  const agent = new SalesAgent({
    memory: new SupabaseMemory(supabaseClient),
    tools: [crmTool, emailTool, knowledgeTool],
    evaluator: new ProxyEvaluator()
  });

  // Resume or start new conversation
  const state = threadId
    ? await agent.resume(threadId)
    : agent.newConversation();

  const result = await agent.run(task, state);

  // Audit log
  await supabaseClient.from('agent_audit_log').insert({
    agent_id: 'sales-agent-v1',
    action_type: 'task_execution',
    input: { task, context },
    output: result,
    tools_called: result.toolsCalled,
    latency_ms: result.latencyMs,
    cost_usd: result.costUsd
  });

  return new Response(JSON.stringify(result), {
    headers: { "Content-Type": "application/json" }
  });
});
```

**Scaling Pattern (z Enterprise knihy):**
- Edge Functions = horizontální scaling automaticky
- Každý agent type = vlastní Edge Function
- Supabase Realtime pro streaming responses
- Rate limiting per user/organization

---

### DAY 19 — Workflow Automation: Apps-to-Agents Migration
**Deliverable:** Automated workflow agenti pro repetitivní business procesy

**Z Baker — The Apps-to-Agents Shift:**
Tradiční apps čekají na user input. Agenti jsou goal-oriented — dostanou high-level task a autonomně řeší.

**5 Workflow Agents to Build:**

1. **Lead Qualification Agent:**
   - Trigger: New lead in CRM
   - Actions: Enrich data (web scrape, LinkedIn), score lead, route to right rep, draft initial outreach
   - Cadence: Real-time

2. **Follow-Up Agent:**
   - Trigger: No response after 3 days
   - Actions: Check CRM history, generate personalized follow-up, schedule send, update CRM
   - Cadence: Daily batch

3. **Meeting Prep Agent:**
   - Trigger: Calendar event in 1 hour
   - Actions: Pull prospect info, recent interactions, prep talking points, generate brief
   - Cadence: 1 hour before every meeting

4. **Student Progress Agent (JI):**
   - Trigger: Student completes lesson
   - Actions: Analyze performance, update learning path, generate personalized homework, send progress report
   - Cadence: After each session

5. **Report Generation Agent:**
   - Trigger: Weekly (Monday 8am)
   - Actions: Pull KPIs, generate insights, identify trends, create executive summary
   - Cadence: Weekly

**Make.com Integration (z Dantas "Power Platform Playbook"):**
Pro workflows, které sahají mimo tvůj stack → Make.com scenarios:
- Webhook trigger → Edge Function → Agent → Action
- Native integrations: Gmail, Slack, HubSpot, Stripe

---

### DAY 20 — Personalization Engine + Role-Based Adaptation
**Deliverable:** Agent personalization system

**Z Baker — Workflow Personalization:**
Agent se učí z interakcí:
- Preferovaný tón a styl
- Často používané formáty
- Engagement patterns
- Pracovní návyky

**Z Baker — Role-Based Adaptation:**
Stejná data, jiný kognitivní workflow:

| Role | Sees | Focus |
|------|------|-------|
| Sales Rep | Pipeline actions, next best action | Closing deals |
| Manager | Team forecasts, coaching opportunities | Team performance |
| CEO | Strategic trends, market position | Big picture |
| Student (JI) | Next lesson, progress bar, achievements | Learning |
| Teacher (JI) | Class overview, struggling students, content gaps | Teaching |

**Implementation:**
```typescript
class PersonalizationEngine {
  async getPersonalizedContext(userId: string, role: string): Promise<Context> {
    // Get user preferences from memory
    const prefs = await this.memory.getUserPreferences(userId);

    // Get role-specific view
    const roleConfig = this.roleConfigs.get(role);

    // Get behavioral patterns
    const patterns = await this.memory.getBehavioralPatterns(userId);

    return {
      tone: prefs.preferredTone || roleConfig.defaultTone,
      detailLevel: prefs.detailLevel || roleConfig.defaultDetail,
      focusAreas: roleConfig.focusAreas,
      recentPatterns: patterns,
      adaptations: this.calculateAdaptations(prefs, patterns)
    };
  }

  private calculateAdaptations(prefs: Prefs, patterns: Patterns): Adaptation[] {
    // If user always skips detailed explanations → shorter responses
    // If user frequently asks follow-ups about X → proactively include X
    // If user prefers bullet points → format accordingly
    return [];
  }
}
```

---

### DAY 21 — Full Integration Test + Production Deploy
**Deliverable:** Everything connected, tested, deployed

**Integration Checklist:**

**Core Infrastructure:**
- [ ] Agent Runtime — Sense-Think-Act loop works end-to-end
- [ ] Memory System — Episodic/Semantic/Procedural reads and writes
- [ ] Tool System — MCP tools execute correctly
- [ ] RAG Pipeline — Relevant retrieval with HyDE + hybrid search
- [ ] Knowledge Graph — Graph traversal returns connected insights

**Multi-Agent:**
- [ ] Orchestrator — Task decomposition and delegation works
- [ ] A2A Communication — Agents exchange messages
- [ ] Self-Correction — Proxy evaluation improves output quality
- [ ] Competitive Generation — Best-of-N selection works

**Production:**
- [ ] Edge Functions deployed to Supabase
- [ ] Audit logging captures every agent decision
- [ ] Security — OWASP mitigations in place
- [ ] Rate limiting — Per-user and per-agent limits
- [ ] Error handling — Graceful degradation
- [ ] Monitoring — Latency, cost, accuracy dashboards

**Workflow Agents:**
- [ ] Lead Qualification — triggers on new CRM entry
- [ ] Follow-Up — runs daily batch
- [ ] Meeting Prep — fires 1h before meetings
- [ ] Student Progress (JI) — activates after lessons
- [ ] Weekly Reports — generates Monday 8am

**Eval Results:**
- [ ] Sales Agent accuracy > 80% on test cases
- [ ] RAG retrieval precision > 75%
- [ ] Average latency < 3 seconds
- [ ] Cost per interaction < $0.05
- [ ] Zero critical security issues

---

## QUICK REFERENCE: Key Patterns from All 12 Books

### Architecture Decision Matrix
| Use Case | Pattern | Framework |
|----------|---------|-----------|
| Single task, fast response | Single Agent + Tools | Direct Claude API |
| Multi-step workflow | Sequential Orchestration | LangGraph |
| Independent parallel tasks | Parallel Orchestration | Promise.all |
| Complex delegation | Hierarchical Orchestration | Custom Supervisor |
| Team collaboration | Role-based Agents | CrewAI pattern |
| Quality-critical output | Competitive + Proxy Eval | AutoGen pattern |
| Real-time + Strategic | Hybrid Architecture | Reactive + Deliberative |

### Protocol Selection
| Need | Protocol | Status |
|------|----------|--------|
| Connect to tools/data | MCP | Production-ready |
| Agent-to-agent tasks | A2A | Emerging |
| Cross-org agent network | ANP | Early stage |
| Enterprise governance | ACP | Enterprise-ready |

### RAG Technique Selection
| Query Type | Best Technique |
|------------|---------------|
| Semantic/fuzzy | Vector search (cosine similarity) |
| Exact keyword | BM25 |
| Complex/mixed | Hybrid (BM25 + Vector + Reranking) |
| Low-quality queries | HyDE (generate hypothetical answer first) |
| Relationship queries | GraphRAG (knowledge graph + vector) |
| Multi-hop reasoning | Propositions-based chunking + Graph traversal |

### Memory Selection
| Duration | Type | Storage |
|----------|------|---------|
| Single conversation | Working memory | In-process state |
| Across sessions | Episodic | Supabase + pgvector |
| Permanent knowledge | Semantic | Supabase + pgvector |
| Learned procedures | Procedural | Supabase JSON |
| Multi-agent shared | Shared memory | Supabase Realtime |

---

## SOURCES

1. Biswas & Talukdar — *Building Agentic AI Systems* (Packt, 2025)
2. Baker — *Agentic AI For Dummies* (2025)
3. Ozdemir — *Building Agentic AI Workflows* (2025)
4. Lanham — *AI Agents in Action* (2025)
5. Ranjan et al. — *Agentic AI in Enterprise* (2025)
6. Raieli & Iuculano — *Building AI Agents with LLMs, RAG, and Knowledge Graphs* (Packt, 2025)
7. Taulli & Deshmukh — *Building Generative AI Agents* (Apress, 2025)
8. Sayfan — *Design Multi-Agent AI Systems Using MCP and A2A* (2025)
9. Raff et al. — *How Large Language Models Work* (2025)
10. Dantas & Huntingford — *The Power Platform Playbook for Digital Transformation* (Packt, 2025)
