# Scheme Alias Completeness Audit — entity-registry-v3.2
Corpus-only audit. QA, qrels, graph paths, rankings, traces, and metrics were not inputs.
- Schemes audited: 22
- Accepted additions: 5
- Rejected candidates: 6

## Accepted additions
- `AB PM-JAY` → `Ayushman Bharat - Pradhan Mantri Jan Arogya Yojana` (explicit_official_short_title_in_corpus)
- `PM-KISAN` → `PM-KISAN Operational Guidelines` (repeated_official_short_title)
- `PMGKAY` → `Pradhan Mantri Garib Kalyan Anna Yojana` (title_followed_by_acronym)
- `PMUY 2.0` → `Pradhan Mantri Ujjwala Yojana 2.0` (official_numbered_phase_name)
- `Ujjwala 2.0` → `Pradhan Mantri Ujjwala Yojana 2.0` (official_numbered_phase_name)

## Rejected candidates
- `PM-JAY` → `Ayushman Bharat - Pradhan Mantri Jan Arogya Yojana`: alias already owned by separate accepted controlled entity; activation would map one alias to multiple canonical entity IDs
- `PMAY` → `Pradhan Mantri Awaas Yojana - Gramin`: ambiguous across PMAY-Gramin and PMAY-Urban variants
- `PMKVY 4.0` → `Pradhan Mantri Kaushal Vikas Yojana 4.0 - Recognition Of Prior Learning`: ambiguous across three PMKVY 4.0 pathways
- `RPL` → `Pradhan Mantri Kaushal Vikas Yojana 4.0 - Recognition Of Prior Learning`: component acronym already belongs to separate controlled entity and is not unique scheme identity
- `PM-KMY` → `Pradhan Mantri Kisan Maan Dhan Yojana Operational Guidelines`: alias already owned by separate accepted controlled entity; no entity-identity repair authorized in v3.2
- `PMUY` → `Pradhan Mantri Ujjwala Yojana 2.0`: ambiguous across predecessor PMUY scheme and numbered phase 2.0

## All 22 schemes

### Atal Pension Yojana
- Existing aliases: APY
- Accepted additions: none
- Rejected: none

### Ayushman Bharat - Pradhan Mantri Jan Arogya Yojana
- Existing aliases: AB-PMJAY
- Accepted additions: AB PM-JAY
- Rejected: PM-JAY

### Mahatma Gandhi National Rural Employment Guarantee Act
- Existing aliases: MGNREGA
- Accepted additions: none
- Rejected: none

### PM Janjati Adivasi Nyaya Maha Abhiyan
- Existing aliases: PM Janjati Adivasi Nyaya Maha Abhiyan (PM JANMAN), PM JANMAN, PM-JANMAN
- Accepted additions: none
- Rejected: none

### PM POSHAN - Prime Minister's Overarching Scheme For Holistic Nourishment
- Existing aliases: PM POSHAN
- Accepted additions: none
- Rejected: none

### PM Street Vendor’s AtmaNirbhar Nidhi
- Existing aliases: PM Street Vendor’s AtmaNirbhar Nidhi (PM SVANidhi), PM SVANIDHI, PM SVANidhi
- Accepted additions: none
- Rejected: none

### PM-KISAN Operational Guidelines
- Existing aliases: none
- Accepted additions: PM-KISAN
- Rejected: none

### Pradhan Mantri Awaas Yojana - Gramin
- Existing aliases: PMAY - G
- Accepted additions: none
- Rejected: PMAY

### Pradhan Mantri Awas Yojana - Urban
- Existing aliases: PMAY - U
- Accepted additions: none
- Rejected: none

### Pradhan Mantri Fasal Bima Yojna
- Existing aliases: PMFBY, Pradhan Mantri Fasal Bima Yojna (PMFBY)
- Accepted additions: none
- Rejected: none

### Pradhan Mantri Garib Kalyan Anna Yojana
- Existing aliases: PM-GKAY
- Accepted additions: PMGKAY
- Rejected: none

### Pradhan Mantri Jan Dhan Yojana
- Existing aliases: PMJDY
- Accepted additions: none
- Rejected: none

### Pradhan Mantri Jeevan Jyoti Bima Yojana
- Existing aliases: PMJJBY
- Accepted additions: none
- Rejected: none

### Pradhan Mantri Kaushal Vikas Yojana 4.0 - Recognition Of Prior Learning
- Existing aliases: PMKVY - RPL
- Accepted additions: none
- Rejected: PMKVY 4.0, RPL

### Pradhan Mantri Kaushal Vikas Yojana 4.0 - Short-Term Training
- Existing aliases: PMKVY -STT
- Accepted additions: none
- Rejected: none

### Pradhan Mantri Kaushal Vikas Yojana 4.0- Special Projects
- Existing aliases: PMKVY - SP
- Accepted additions: none
- Rejected: none

### Pradhan Mantri Kisan Maan Dhan Yojana Operational Guidelines
- Existing aliases: none
- Accepted additions: none
- Rejected: PM-KMY

### Pradhan Mantri Mudra Yojana
- Existing aliases: PMMY
- Accepted additions: none
- Rejected: none

### Pradhan Mantri Suraksha Bima Yojana
- Existing aliases: PMSBY
- Accepted additions: none
- Rejected: none

### Pradhan Mantri Ujjwala Yojana
- Existing aliases: PMUY
- Accepted additions: none
- Rejected: none

### Pradhan Mantri Ujjwala Yojana 2.0
- Existing aliases: PMUY2
- Accepted additions: PMUY 2.0, Ujjwala 2.0
- Rejected: PMUY

### Prime Minister's Employment Generation Programme
- Existing aliases: PMEGP
- Accepted additions: none
- Rejected: none
