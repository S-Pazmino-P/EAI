# ADNI Terminology Mapping

Generated: 2026-08-17T18:27:40.420116Z

This document contains the complete terminology mapping for ADNI schema columns to standard LOINC/SNOMED codes and ADNI custom codes.

---

## Fields with Standard LOINC Codes

| Column | Description | System | Code | Display |
|--------|-------------|--------|------|---------|
| **ABETA** | Cerebrospinal Fluid Amyloid Beta 1-42 - Concentration of Aβ1-42 in CSF | LOINC | 106057-3 | Beta-Amyloid 1-42 and 1-40 panel - Cerebral spinal fluid |
| **CDRSB** | Clinical Dementia Rating Sum of Boxes - Global dementia severity measure | LOINC | 72088-8 | Clinical Dementia Rating scale [CDR] |
| **EcogPtDivatt** | Everyday Cognition - Participant Divided Attention - Self-rating for divided attention | LOINC | 89285-1 | Executive functioning: divided attention panel [ECog] |
| **EcogPtLang** | Everyday Cognition - Participant Language - Self-rating for language tasks | LOINC | 89287-7 | Language panel [ECog] |
| **EcogPtMem** | Everyday Cognition - Participant Memory - Self-rating for memory tasks | LOINC | 89286-9 | Memory panel [ECog] |
| **EcogPtOrgan** | Everyday Cognition - Participant Organization - Self-rating for organizational tasks | LOINC | 89290-1 | Executive functioning: organization panel [ECog] |
| **EcogPtPlan** | Everyday Cognition - Participant Planning - Self-rating for planning tasks | LOINC | 89289-3 | Executive functioning: planning panel [ECog] |
| **EcogPtTotal** | Everyday Cognition - Participant Total Score - Sum of all participant-rated ECog domains | LOINC | 89133-3 | Everyday Cognition - Participant Self Report Form [ECog] |
| **EcogPtVisspat** | Everyday Cognition - Participant Visuospatial - Self-rating for visuospatial tasks | LOINC | 89288-5 | Visual-spatial and perceptual abilities panel [ECog] |
| **EcogSPDivatt** | Everyday Cognition - Study Partner Divided Attention - Informant rating of divided attention | LOINC | 89298-4 | Executive functioning: divided attention panel [ECog.Partner] |
| **EcogSPLang** | Everyday Cognition - Study Partner Language - Informant rating of participant language | LOINC | 89296-8 | Language panel [ECog.Partner] |
| **EcogSPMem** | Everyday Cognition - Study Partner Memory - Informant rating of participant memory | LOINC | 89297-6 | Memory panel [ECog.Partner] |
| **EcogSPOrgan** | Everyday Cognition - Study Partner Organization - Informant rating of participant organization | LOINC | 89293-5 | Executive functioning: organization panel [ECog.Partner] |
| **EcogSPPlan** | Everyday Cognition - Study Partner Planning - Informant rating of participant planning | LOINC | 89294-3 | Executive functioning: planning panel [ECog.Partner] |
| **EcogSPTotal** | Everyday Cognition - Study Partner Total Score - Sum of all study partner-rated ECog domains | LOINC | 89090-5 | Everyday Cognition - Study Partner Report Form [ECog.Partner] |
| **EcogSPVisspat** | Everyday Cognition - Study Partner Visuospatial - Informant rating of participant visuospatial | LOINC | 89295-0 | Visual-spatial and perceptual abilities panel [ECog.Partner] |
| **FAQ** | Functional Activities Questionnaire - 10-item informant-based functional assessment | LOINC | 95028-7 | FASI v1.0 - Instrumental Activities of Daily Living [CMS Assessment] |
| **FBB** | Florbetaben PET SUVr - Amyloid plaque binding measurement using Florbetaben tracer | LOINC | LP428286-1 | Amyloid plaques probability score |
| **MMSE** | Mini-Mental State Examination - Brief 30-point cognitive screening test | LOINC | 72107-6 | Mini-Mental State Examination [MMSE] |
| **MOCA** | Montreal Cognitive Assessment - Brief 30-point MCI screening test | LOINC | 66610-7 | Cognitive impairment [Reported] |
| **PIB** | Pittsburgh Compound B (PIB) PET SUVr - Amyloid plaque binding measurement using PIB tracer | LOINC | LP428286-1 | Amyloid plaques probability score |
| **TAU** | Cerebrospinal Fluid Total Tau - Concentration of total tau protein in CSF | LOINC | 30160-6 | Tau protein [Mass/volume] in Cerebral spinal fluid |

---

## Fields with SNOMED Matches Found

| Column | Description | System | Code | Display |
|--------|-------------|--------|------|---------|
| **ADAS11** | ADAS-Cog 11-item | SNOMED | 714360001 | Alzheimer's Disease Assessment Scale score |
| **ADAS13** | ADAS-Cog 13-item | SNOMED | 714360001 | Alzheimer's Disease Assessment Scale score |
| **ADASQ4** | ADAS Delayed Word Recall | SNOMED | 714360001 | Alzheimer's Disease Assessment Scale score |
| **LDELTOTAL** | Logical Memory Delayed Recall | SNOMED | 273921009 | Wechsler memory scale |
| **DIGITSCOR** | Digit Symbol Substitution | SNOMED | 273857000 | Symbol digit modalities test |
| **TRABSCOR** | Trail Making Test Part B | SNOMED | 273882000 | Trail making test |
---


## Diagnosis Values (SNOMED)

| Column | Value | System | Code | Display |
|--------|-------|--------|------|---------|
| **DX** | CN | SNOMED | 449888003 | Normal cognition |
| **DX** | AD | SNOMED | 26929004 | Alzheimer's disease |
| **DX** | EMCI | SNOMED | 386805003 | Mild neurocognitive disorder |
| **DX** | LMCI | SNOMED | 386805003 | Mild neurocognitive disorder |
| **DX** | SMC | SNOMED | 27350009 | Subjective memory complaint |

---

## Fields with ADNI Custom Codes

| Column | Description | ADNI Code | Display |
|--------|-------------|-----------|---------|
| **AGE** | Age - The participant's age in years at the time of the specific examination visit | AGE | Participant age at visit |
| **APOE4** | APOE E4 Allele Count - The number of Apolipoprotein E (APOE) ε4 alleles carried by the participant | APOE4 | APOE epsilon 4 allele count (genetic risk factor for AD) |
| **AV45** | Florbetapir (AV45) PET SUVr - Amyloid plaque binding measurement using AV45 tracer | AV45 | Amyloid beta plaque deposition measured by Florbetapir PET |
| **COLPROT** | Collection Protocol - The ADNI study phase under which the specific data point was collected | COLPROT | ADNI study phase of data collection |
| **EXAMDATE** | Examination Date - The calendar date on which the participant's examination visit occurred | EXAMDATE | Date of examination |
| **Entorhinal** | Entorhinal Cortex Volume (UCSF) - Volume of entorhinal cortex from MRI | Entorhinal | Entorhinal cortical volume - early AD atrophy region |
| **FDG** | FDG-PET Standardized Uptake Value Ratio - Cerebral glucose metabolism from Fluorodeoxyglucose PET | FDG | Brain glucose metabolism measured by FDG-PET |
| **FLDSTRENG** | MRI Field Strength - The magnetic field strength of the MRI scanner | FLDSTRENG | MRI scanner field strength (Tesla) |
| **FSVERSION** | FreeSurfer Version - The version of FreeSurfer used to process MRI images | FSVERSION | FreeSurfer software version |
| **Fusiform** | Fusiform Gyrus Volume (UCSF) - Volume of fusiform gyrus from MRI | Fusiform | Fusiform gyrus volume |
| **Hippocampus** | Hippocampus Volume (UCSF) - Volume of hippocampus from MRI | Hippocampus | Hippocampal volume - key AD atrophy marker |
| **ICV** | Intracranial Volume - Total volume of intracranial cavity | ICV | Total intracranial volume for normalization |
| **IMAGEUID** | Image Unique Identifier - Unique identifier for each MRI or PET image | IMAGEUID | Image database identifier |
| **MidTemp** | Middle Temporal Gyrus Volume (UCSF) - Volume of middle temporal gyrus from MRI | MidTemp | Middle temporal gyrus volume |
| **ORIGPROT** | Original Protocol - The initial ADNI study phase in which the participant was originally enrolled | ORIGPROT | Initial ADNI enrollment phase |
| **PTAU** | Cerebrospinal Fluid Phosphorylated Tau - Concentration of p-tau181 in CSF | PTAU | CSF phosphorylated tau at threonine 181 - AD-specific tau pathology |
| **PTEDUCAT** | Participant Education - The number of years of formal education completed by the participant | PTEDUCAT | Years of formal education |
| **PTETHCAT** | Participant Ethnicity - A classification of whether the participant identifies as Hispanic or Latino/Latina | PTETHCAT | Ethnicity classification |
| **PTGENDER** | Participant Gender - The biological sex of the participant at birth | PTGENDER | Biological sex |
| **PTID** | Participant ID - The original participant identifier as assigned by the ADNI clinical site | PTID | Original site-assigned participant identifier |
| **PTMARRY** | Participant Marital Status - The participant's current marital status | PTMARRY | Marital status |
| **PTRACCAT** | Participant Race - A classification of the participant's racial background | PTRACCAT | Racial classification |
| **RAVLT_forgetting** | Rey Auditory Verbal Learning Test Forgetting - Difference between Trial 5 and delayed recall | RAVLT_forgetting | Retroactive interference - retention over delay |
| **RAVLT_learning** | Rey Auditory Verbal Learning Test Learning - Difference between Trial 5 and Trial 1 | RAVLT_learning | Learning slope across repeated trials |
| **RAVLT_perc_forgetting** | Rey Auditory Verbal Learning Test Percent Forgetting - Percentage forgotten after delay | RAVLT_perc_forgetting | Proportional forgetting rate |
| **RID** | Participant Roster ID - A unique numerical identifier assigned to each participant upon enrollment in ADNI | RID | Unique participant identifier |
| **SITE** | Site ID - The numerical identifier for the ADNI collection site | SITE | Clinical site number |
| **VISCODE** | Visit Code - A standardized code indicating the specific visit timepoint | VISCODE | Visit timepoint identifier |
| **Ventricles** | Ventricles Volume (UCSF) - Volume of cerebral ventricles from MRI | Ventricles | Cerebral ventricular volume |
| **WholeBrain** | Whole Brain Volume (UCSF) - Total brain volume from MRI | WholeBrain | Total brain volume |
| **mPACCtrailsB** | Modified Preclinical Alzheimer's Cognitive Composite with Trails B | mPACCtrailsB | Preclinical AD cognitive composite score using Trail Making B |
| **mPACCdigit** | Modified PACC (Digit Symbol) | mPACCdigit | Modified PACC with Digit Symbol |
| **RAVLT_immediate** | Rey Auditory Verbal Learning Test Immediate Recall - Sum across 5 trials | RAVLT_immediate | Verbal memory count |


---


## ADNI Custom CodeSystem Definition

```json
{
  "resourceType": "CodeSystem",
  "id": "adni-terms",
  "meta": {
    "source": "ADNI",
    "date": "2026-08-17T18:27:40.420110Z"
  },
  "url": "http://adni.example.org/fhir/CodeSystem/adni-terms",
  "version": "1.0.0",
  "name": "ADNI_Terms",
  "title": "ADNI Terminology Codes",
  "status": "active",
  "content": "complete",
  "concept": [
    {
      "code": "ADAS11",
      "display": "Cognitive assessment score - 11-item version"
    },
    {
      "code": "AGE",
      "display": "Participant age at visit"
    },
    {
      "code": "APOE4",
      "display": "APOE epsilon 4 allele count (genetic risk factor for AD)"
    },
    {
      "code": "AV45",
      "display": "Amyloid beta plaque deposition measured by Florbetapir PET"
    },
    {
      "code": "COLPROT",
      "display": "ADNI study phase of data collection"
    },
    {
      "code": "DIGITSCOR",
      "display": "Processing speed, attention, and executive function"
    },
    {
      "code": "EXAMDATE",
      "display": "Date of examination"
    },
    {
      "code": "Entorhinal",
      "display": "Entorhinal cortical volume - early AD atrophy region"
    },
    {
      "code": "FDG",
      "display": "Brain glucose metabolism measured by FDG-PET"
    },
    {
      "code": "FLDSTRENG",
      "display": "MRI scanner field strength (Tesla)"
    },
    {
      "code": "FSVERSION",
      "display": "FreeSurfer software version"
    },
    {
      "code": "Fusiform",
      "display": "Fusiform gyrus volume"
    },
    {
      "code": "Hippocampus",
      "display": "Hippocampal volume - key AD atrophy marker"
    },
    {
      "code": "ICV",
      "display": "Total intracranial volume for normalization"
    },
    {
      "code": "IMAGEUID",
      "display": "Image database identifier"
    },
    {
      "code": "MidTemp",
      "display": "Middle temporal gyrus volume"
    },
    {
      "code": "ORIGPROT",
      "display": "Initial ADNI enrollment phase"
    },
    {
      "code": "PTAU",
      "display": "CSF phosphorylated tau at threonine 181 - AD-specific tau pathology"
    },
    {
      "code": "PTEDUCAT",
      "display": "Years of formal education"
    },
    {
      "code": "PTETHCAT",
      "display": "Ethnicity classification"
    },
    {
      "code": "PTGENDER",
      "display": "Biological sex"
    },
    {
      "code": "PTID",
      "display": "Original site-assigned participant identifier"
    },
    {
      "code": "PTMARRY",
      "display": "Marital status"
    },
    {
      "code": "PTRACCAT",
      "display": "Racial classification"
    },
    {
      "code": "RAVLT_forgetting",
      "display": "Retroactive interference - retention over delay"
    },
    {
      "code": "RAVLT_learning",
      "display": "Learning slope across repeated trials"
    },
    {
      "code": "RAVLT_perc_forgetting",
      "display": "Proportional forgetting rate"
    },
    {
      "code": "RID",
      "display": "Unique participant identifier"
    },
    {
      "code": "SITE",
      "display": "Clinical site number"
    },
    {
      "code": "TRABSCOR",
      "display": "Executive function and mental flexibility"
    },
    {
      "code": "VISCODE",
      "display": "Visit timepoint identifier"
    },
    {
      "code": "Ventricles",
      "display": "Cerebral ventricular volume"
    },
    {
      "code": "WholeBrain",
      "display": "Total brain volume"
    },
    {"code": "mPACCdigit", "display": "Modified PACC with Digit Symbol"},
    {
      "code": "mPACCtrailsB",
      "display": "Preclinical AD cognitive composite score using Trail Making B"
    }
  ]
}
```

## Summary

| Category | Count |
|----------|-------|
| Standard LOINC/SNOMED codes | 35 |
| ADNI custom codes | 27 |
