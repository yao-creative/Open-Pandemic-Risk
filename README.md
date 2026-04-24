# AI x Bio Hackathon Notes

## Hackathon

- Event: [AI x Bio Hackathon](https://apartresearch.com/research)
- Dates mentioned in chat: April 24-26, 2026
- Focus: how AI changes biological risk, and what can be built to stay ahead

## Tracks

1. DNA synthesis screening and guardrails for AI-powered bio design tools
2. Pandemic early warning systems: wastewater, metagenomic sequencing, disease intelligence
3. Practitioner tools: dashboards, risk assessment, policy trackers, comms tools for under-resourced institutions
4. Benchtop DNA synthesizer security: phone-home screening, tamper-proof hardware, split-order detection

## Funding angle

- [Coefficient Giving](https://www.coefficientgiving.org/) biosecurity RFP mentioned in chat
- Deadline mentioned in chat: May 11
- Chat claim: possible follow-on 500-word Expression of Interest

## Judge context

- Judges named in chat:
  - Jasper Goetting, SecureBio
  - Jason Hoelscher-Obermaier, Apart Research
- Influential speakers mentioned in chat:
  - Kevin Esvelt
  - Jaime Yassif
  - Conor McGurk
  - Steph Guerra
  - Jonas Sandbrink
- What judges likely reward:
  - Open-source tool
  - Real practitioner gap
  - Technical substance
  - Clear bio-risk reduction story
  - Usable by under-resourced institutions

## Best fit from chat

- Best: Track 3
- Viable: Track 2
- Harder without bio teammate: Track 1, Track 4

## Initial project ideas from chat

- Open-source disease surveillance dashboard pulling WHO, HealthMap, wastewater APIs
- Screening API wrapper that flags suspicious DNA sequences using existing databases
- Risk assessment tool that ingests reports and outputs structured threat summaries with LLMs

## Deduped idea list

1. Bio threat intel aggregator
   - Analogs: Recorded Future, Mandiant, CrowdStrike, HealthMap, ProMED
   - Build: aggregate WHO, ProMED, preprints, news; extract pathogen, location, severity, novelty; feed + map + alerts
   - Chat rank: 1

2. Open-source BlueDot clone
   - Analogs: BlueDot, HealthMap
   - Build: outbreak signal ingestion + spread-risk scoring + country briefings
   - Chat rank: 2

3. Global biosecurity policy tracker
   - Analogs: Quorum, FiscalNote, IBBIS, Primer.ai, Plaza.ai, GovPredict
   - Build: track DNA synthesis rules, pandemic treaty updates, AI bio commitments, lab safety policy
   - Chat rank: 3

4. Wastewater and metagenomic anomaly dashboard
   - Analogs: Biobot Analytics, Metabiomics, IDbyDNA, Microsoft Premonition
   - Build: unify public wastewater and metagenomic data into one alerting dashboard
   - Chat rank: 4

5. Biosafety compliance and risk scoring tool
   - Analogs: Vanta, Drata, ServiceNow Risk, ProcessUnity, LogicManager, Veeva Vault
   - Build: lab checklist, posture monitoring, risk register, vendor risk, procedure risk
   - Chat rank: 5

6. Biosecurity literature synthesizer
   - Analogs: Elicit, Consensus, Scite, Semantic Scholar, Iris.ai
   - Build: research synthesis, Q&A, credibility scoring, literature alerts, research-gap finder
   - Chat rank: 6

7. Country bio-risk index auto-updater
   - Analogs: NTI Global Health Security Index
   - Build: continuously updated country risk scores with LLM summaries
   - Chat rank: 7

8. Bio incident structured database
   - Analogs: Anomali
   - Build: structured historical and ongoing incident database
   - Chat rank: 8

9. Secure practitioner comms layer
   - Analogs: Element/Matrix, Wickr, Keybase
   - Build: secure incident comms and file-sharing setup for practitioners
   - Chat rank: 9

10. LMIC biosecurity data integration layer
    - Analogs: Palantir Foundry, Secureworks Taegis
    - Build: open-source data integration layer for health ministries
    - Chat rank: 10

11. DNA synthesis regulation tracker
    - Analogs: IBBIS
    - Build: global tracker for synthesis-screening laws and norms

12. Bio-AI credentialing and access control
    - Analogs: Sentinel Bio
    - Build: researcher credentialing dashboard and access controls

13. Bio-risk scoring UI from published frameworks
    - Analogs: Active Site / Panoplia Labs
    - Build: practitioner UI based on published bio-risk frameworks

14. Open interface for detection data
    - Analogs: SecureBio
    - Build: practitioner-facing interface for detection outputs

15. Sponsor-aligned biosecurity tooling
    - Analogs: Fourth Eon Bio
    - Build: anything directly aligned with sponsor priorities

16. Outbreak-response gap tracker
    - Analogs: CEPI
    - Build: dashboard for funded response gaps

17. Open biosurveillance reporting tools
    - Analogs: Ginkgo Bioworks biosecurity tooling
    - Build: reporting and monitoring interface

18. Sequence-level risk flagging
    - Analogs: VirusTotal
    - Build: suspicious sequence scanning against open threat databases

19. Grey-literature and forum monitoring
    - Analogs: Flashpoint
    - Build: monitor academic, preprint, and related discussion sources

20. Geospatial bio-risk layer
    - Analogs: Esri ArcGIS Health
    - Build: map-based bio-risk view

21. Dual-use audit trail and lab workflow tooling
    - Analogs: Benchling, TetraScience, LabArchives
    - Build: audit trail, incident data standard, review workflow in lab tools

## Top 3 from chat

### 1. Bio Threat Intel Aggregator

- Positioning: open-source "Recorded Future for biorisks"
- What it does: Google News for outbreaks, but structured for practitioners
- Sources mentioned:
  - ProMED RSS
  - WHO Disease Outbreak News
  - bioRxiv / medRxiv
  - ECDC
  - GDELT or NewsAPI
- Core fields:
  - pathogen
  - location
  - case_count
  - death_count
  - novelty
  - severity
  - credibility
  - summary
- UI:
  - feed
  - map
  - filters
  - alerts
- Stack first proposed:
  - Next.js
  - Supabase
  - cron
  - Gemini Flash Lite
- Stack later chosen with teammate:
  - FastAPI
  - SQLAlchemy
  - SQLite
  - Azure OpenAI
  - Next.js frontend
  - Docker Compose
- FastAPI endpoints mentioned:
  - `GET /signals`
  - `GET /signals/{id}`
  - `GET /signals/map`
  - `POST /ingest/run`
  - `GET /stats`
- Team split mentioned:
  - Yao: backend, scraping, models, extraction endpoint
  - Bryan: frontend, feed view, map, filters

### 2. Open-Source BlueDot Clone

- Positioning: open-source outbreak detection and spread-risk system
- Sources mentioned:
  - OpenFlights
  - WorldPop
  - GLEAM
  - ProMED
  - HealthMap API
- Core objects mentioned:
  - `OutbreakSignal`
  - `CountryRisk`
  - `AirlineRoute`
- MVP logic:
  - airline exposure
  - case trend
  - population density
  - destination-country risk score
- Output:
  - world map
  - country drilldown
  - PDF briefing

### 3. Global Biosecurity Policy Tracker

- Positioning: structured database of global biosecurity policy events
- Sources mentioned:
  - WHO
  - IBBIS
  - Federal Register
  - GOV.UK
  - EUR-Lex
  - NTI GHS Index
- Core fields:
  - jurisdiction
  - jurisdiction_type
  - policy_type
  - status
  - impact_level
  - key_provisions
  - effective_date
  - tags
- UI:
  - Kanban by status
  - world map
  - timeline
  - alert feed
- Seed-data note from chat:
  - manually seed 50-100 real policy events first

## Bottom line from chat

- Best software-only option: Bio Threat Intel Aggregator
- Fastest useful demo: Global Biosecurity Policy Tracker
- Most ambitious: Open-source BlueDot Clone
