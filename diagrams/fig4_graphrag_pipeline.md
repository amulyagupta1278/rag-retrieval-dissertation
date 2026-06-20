# Figure 4: GraphRAG Entity-Aware Retrieval Pipeline

```mermaid
graph TD
    A["Document Chunks"] -->|spaCy NER<br/>PERSON, ORG, GPE, MONEY, DATE, LAW| B["Standard Entities"]
    A -->|Regex Patterns<br/>SCHEME_NAME, AMOUNT, BENEFICIARY, ELIGIBILITY, DOCUMENT| C["Domain Entities"]
    
    B -->|Combine| D["All Entities"]
    C -->|Combine| D
    
    D -->|Create Entity Nodes<br/>Link MENTIONED_IN chunks| E["Knowledge Graph<br/>(NetworkX DiGraph)"]
    
    D -->|Co-occurrence<br/>CO_OCCURS_WITH edges| E
    
    E -->|Persist| F["Graph Files<br/>(graph.json<br/>chunk_lookup.json)"]
    
    F -->|Load| G["Query<br/>(text)"]
    
    G -->|spaCy NER + Regex| H["Query Entities<br/>(Seed nodes)"]
    
    H -->|Find matching nodes<br/>in graph| I["Seed Nodes"]
    
    I -->|2-hop traversal<br/>Collect referenced chunks| E
    
    E -->|Score chunks<br/>+1.0 direct hit<br/>+0.5 2-hop| J["Scored Results<br/>(ranked by score)"]
```

**Graph Structure:**
- **Entity Nodes:** text, type, chunk_ids
- **Chunk Nodes:** text, doc_id
- **Edges:** MENTIONED_IN (entity → chunk), CO_OCCURS_WITH (entity ↔ entity)

**Entity Types (12 total):**
- Standard: PERSON, ORG, GPE, MONEY, DATE, LAW (spaCy)
- Domain: SCHEME_NAME, AMOUNT, BENEFICIARY, ELIGIBILITY, DOCUMENT (regex)

**Query latency:** ~2-11ms

